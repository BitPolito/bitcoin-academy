# Agent Harness & Persistent Memory — Piano Implementativo (v2)

**Vincoli architetturali**
- Modelli locali open-source, nessuna API esterna (privacy, costo)
- Famiglia unica: **Qwen3** — stessa tokenizzazione e stile su tutta la scala 0.6B → 32B
- QVAC SDK come unico layer LLM, **sia su server che su PC studente** (`/generate_json`, `/generate`)
- Infrastruttura esistente: FastAPI + SQLAlchemy + ARQ + Redis + QVAC

**Novità v2 rispetto a v1**

| # | Cambiamento | Perché |
|---|---|---|
| 1 | Famiglia Qwen2.5 → **Qwen3** (incl. MoE 30B-A3B, 4B-2507, embedding/reranker 0.6B) | modelli piccoli molto più capaci; MoE = qualità 30B a velocità 3B attivi |
| 2 | **Inference ladder**: ogni feature usa il gradino più economico possibile | il grosso delle feature di studio non richiede inferenza on-device |
| 3 | **Tier hardware espliciti** con degradazione controllata | "PC normale" non è una specifica; molti studenti non hanno GPU |
| 4 | Tutor **a due percorsi**: fast path (1 chiamata, streaming) + agent path (escalation) | agent loop su ogni turno = 10–30 s di latenza su un 7B, UX inaccettabile |
| 5 | **Precompute pipeline**: quiz pool, FAQ, flashcard, summary generati a build time sul server | sposta l'inferenza dal device dello studente al build batch |
| 6 | Course builder: pipeline = happy path, **agent = escalation** (non sostituzione) | pipeline deterministica è più economica e prevedibile; l'agente interviene sui fallimenti |
| 7 | **Speculative decoding** con draft Qwen3-0.6B (stessa famiglia = stesso vocabolario) | 1.5–2.5× throughput; l'output JSON a bassa temperatura ha alta acceptance rate |
| 8 | Cost control sull'agent loop: thought cap, troncamento tool result, history compressa | il contesto crescente satura la KV cache dei device piccoli |
| 9 | **Consolidamento memoria** periodico + budget di retrieval | i fatti studente crescono senza limite e degradano il retrieval |
| 10 | Fase finale di **benchmark con target di latenza** per feature/tier | senza target misurabili l'ottimizzazione è cieca |

## Implementation status

This document is the design reference for the inference ladder and the
student-memory pipeline. The repository currently implements only the first
slice of Phase 0:

| Ladder rung | Current status | Repository evidence |
|---|---|---|
| 0 — DB / precomputed assets | Partial | DB-backed lesson quizzes and chapter tests are available; the full precompute asset pipeline is planned in Phase 3. |
| 1 — Semantic cache | Planned | No semantic-cache lookup or invalidation service is implemented yet. |
| 2 — Local fast path | Partial | QVAC structured generation and hardware-aware routing exist; the dedicated streaming tutor fast path is planned in Phase 6. |
| 3 — Local agent path | Planned | The routing label exists, but the generic agent runner and tutor tools are planned in Phases 1 and 6. |
| 4 — Server batch inference | Partial | The course-builder map/reduce and groundedness-judge calls exist; the complete server precompute and escalation workflow is planned in Phases 2 and 3. |

Phase 0 capabilities already present are hardware-tier detection with an
optional `HARDWARE_TIER` override, `QVAC_LOCAL_URL`/`QVAC_SERVER_URL`
configuration, task-type routing, and structured-generation support for the
resolved route. There is currently one QVAC deployment, so local and server
URLs resolve to the same worker unless configured otherwise.

---

## Principio guida: inference ladder

Ogni richiesta viene servita dal gradino più basso che può soddisfarla.
Salire un gradino costa un ordine di grandezza in latenza/risorse.

```
gradino 0   DB / asset precomputati        <200 ms    quiz, flashcard, glossario, summary
gradino 1   semantic cache (embedding)     <400 ms    domande frequenti già risposte
gradino 2   singola chiamata LLM locale    1–5 s      chat fast path (RAG + streaming)
gradino 3   agent loop locale              10–20 s    ragionamento multi-step (raro)
gradino 4   server GPU                     batch      course builder, distillazione pesante
```

Mappa feature di studio → gradino:

| Feature | Gradino | Come |
|---|---|---|
| Quiz lezione | 0 | pool precomputato a build time, selezione via query DB |
| Quiz adattivo (rinforzo) | 0 | selezione dal pool filtrata per concept-tag ↔ lacune studente |
| Flashcard | 0 | derivate dal glossario già generato (zero LLM) |
| Summary lezione / ripasso | 0 | precomputato a build time |
| Glossario | 0 | già persistito dalla Fase 3 esistente |
| Domanda fattuale in chat | 1 → 2 | prima semantic cache, poi fast path RAG |
| Spiegazione personalizzata | 2 | fast path + memoria studente iniettata nel contesto |
| Domanda multi-step / confronto concetti | 3 | agent path (escalation dal router) |
| Distillazione sessione | 2 locale / 4 server | opportunistica: server se online, locale altrimenti |
| Generazione corso | 4 | pipeline batch + agent escalation |

---

## Tier hardware e assegnazione modelli

Auto-detection all'avvio (VRAM / RAM / piattaforma), tier persistito in config locale.
Tutti i modelli in quantizzazione **Q4_K_M** salvo diversa indicazione.

| Tier | Hardware tipico | Modello chat | Draft (spec. dec.) | Feature attive localmente |
|---|---|---|---|---|
| **A** | GPU ≥ 12 GB (RTX 4070+) / Apple M-series 32 GB | Qwen3-14B | Qwen3-0.6B | tutte, incluso agent path |
| **B** | GPU 6–8 GB (RTX 3060/4060) / M-series 16 GB | Qwen3-8B | Qwen3-0.6B | tutte, agent path con max_steps ridotto |
| **C** | CPU-only, 8–16 GB RAM | Qwen3-4B-Instruct-2507 | — | fast path + gradini 0–1; agent path e distillazione delegati al server |
| **D** | Hardware insufficiente | — (thin client) | — | solo gradini 0–1 locali; ogni inferenza va al server (coda) |

Modelli di supporto (tutti i tier, girano su CPU):
- **Qwen3-Embedding-0.6B** — embedding locale per semantic cache, retrieval memoria, intent routing (~10 ms/query su CPU)
- **Qwen3-Reranker-0.6B** — opzionale, rerank dei fatti memoria (fallback: scoring pesato cosine + recency + confidence, zero modelli extra)

Server GPU (40–48 GB VRAM):

| Ruolo | Modello | Note |
|---|---|---|
| Primario (map, content gen, quiz pool, FAQ) | **Qwen3-30B-A3B-Instruct-2507** (MoE) | ~18 GB in Q4; 3B parametri attivi = throughput da modello piccolo con qualità da 30B — ideale per il batch del course builder |
| Judge + reduce (qualità critica) | Qwen3-32B dense **oppure** variante Thinking del 30B-A3B | valutare in Fase 8 se il primario basta; un solo modello servito = ops più semplici |

Il vincolo di famiglia unica paga tre volte: (1) tokenizzazione coerente tra contenuto generato dal server e consumato dal locale; (2) speculative decoding possibile (draft e target devono condividere il vocabolario); (3) stile di prompt/output uniforme — un solo set di system prompt da mantenere.

---

## Architettura target

```
┌──────────────────────────────────────────────────────────┐
│  PC Studente (QVAC SDK, modello per tier)                │
│                                                          │
│  richiesta studente                                      │
│      │                                                   │
│      ▼                                                   │
│  Intent Router (embedding 0.6B, no LLM)                  │
│      ├── gradino 0 → DB locale (asset precomputati)      │
│      ├── gradino 1 → semantic cache                      │
│      ├── gradino 2 → Fast Path: 1 chiamata RAG streaming │
│      └── gradino 3 → Agent Path: loop multi-step         │
│                                                          │
│  background: Session Distiller (solo se offline)         │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTP (sync API + job queue)
┌──────────────────────▼───────────────────────────────────┐
│  Server GPU condiviso (QVAC SDK, Qwen3-30B-A3B)          │
│                                                          │
│  Course Builder ── pipeline batch (happy path)           │
│       └── Agent Escalation (judge fail, tree mancante)   │
│  Precompute Pipeline ── quiz pool, FAQ, flashcard, summary│
│  Session Distiller (preferito quando studente online)    │
│  Memory Consolidator (job periodico)                     │
│                                                          │
│  QVAC Vector Store                                       │
│  ├── course_chunks         (esistente)                   │
│  ├── student_memory        (fatti distillati)            │
│  ├── precomputed_qa        (FAQ per semantic cache)      │
│  └── session_summaries                                   │
│                                                          │
│  FastAPI + ARQ + Redis + SQLite/PostgreSQL               │
└──────────────────────────────────────────────────────────┘
```

---

## Ottimizzazioni runtime

Da verificare in Fase 0 quali sono esposte dal runtime QVAC (l'SDK 0.9.1 non ha
constrained decoding; le altre capacità dipendono dal backend di inferenza sottostante).
Per ciascuna è definito il fallback se non disponibile.

| Tecnica | Beneficio | Dove | Fallback se non supportata |
|---|---|---|---|
| **Speculative decoding** (draft 0.6B) | 1.5–2.5× tok/s; eccelle su JSON a bassa temp (token prevedibili → alta acceptance) | Tier A/B locale | nessuno, si rinuncia |
| **Prefix/KV caching** | TTFT quasi azzerato sui turni successivi: system prompt + tool defs statici in testa, history append-only in coda | locale + server | ridurre lunghezza system prompt |
| **KV cache quantization** (q8_0) | −50% memoria KV → contesti più lunghi su VRAM piccola | Tier B/C | ridurre context budget |
| **Streaming** (`/generate`) | latenza percepita: primo token visibile in ~1 s anche se la risposta completa richiede 5 s | fast path chat | nessuno, obbligatorio averlo |
| **Constrained decoding** (JSON schema → grammar) | zero JSON malformato = zero retry sull'agent loop dei modelli piccoli | locale, quando l'SDK lo aggiungerà | retry loop attuale di `/generate_json` + few-shot nel prompt |
| **Continuous batching** | throughput sul course builder: sezioni MAP processate in parallelo | server | parallelismo a livello ARQ (N job concorrenti) |
| **Temperature bassa su JSON** (0.1–0.2) | meno variance = meno retry + migliore acceptance dello spec. decoding | ovunque | già in uso |

Regola di progettazione prompt per il prefix caching: **tutto ciò che è statico va
prima, tutto ciò che cresce va dopo**. Ordine: system prompt → tool definitions →
few-shot → memoria studente → history → turno corrente. La cache resta valida
finché il prefisso non cambia.

---

## Fase 0 — Setup modelli, tier detection, routing (2–3 giorni)

**Obiettivo**: due endpoint QVAC (locale + server) raggiungibili con la stessa API; tier rilevato e persistito.

- [ ] Deploy Qwen3 per tier via QVAC SDK locale; Qwen3-30B-A3B su server *(infra — oggi un solo worker QVAC deployato con Qwen3-4B fisso, vedi `workers/qvac-service/src/models.js`; il routing sotto punta già a `QVAC_LOCAL_URL`/`QVAC_SERVER_URL` pronto per quando il deploy multi-tier esisterà)*
- [ ] **Verifica capability runtime**: streaming, prefix caching, speculative decoding, KV quant, batching — compilare la matrice supportato/fallback *(richiede endpoint reali, non verificabile senza il deploy sopra)*
- [x] `app/services/hardware_tier.py` — detection VRAM/RAM/piattaforma → tier A/B/C/D (nvidia-smi per VRAM, RAM via psutil/os.sysconf, override manuale `HARDWARE_TIER`)
- [x] `app/services/qvac_router.py` — routing per gradino:

```python
LADDER_ROUTING = {
    # gradino: (target, modello)
    "precomputed":  ("db",     None),
    "semantic_hit": ("cache",  None),
    "chat_fast":    ("local",  TIER_MODEL),      # fallback server se tier D
    "chat_agent":   ("local",  TIER_MODEL),      # fallback server se tier C/D
    "distill":      ("server", "qwen3-30b-a3b"), # fallback local se offline
    "map":          ("server", "qwen3-30b-a3b"),
    "reduce":       ("server", "qwen3-30b-a3b"),
    "content_gen":  ("server", "qwen3-30b-a3b"),
    "judge":        ("server", "qwen3-30b-a3b"),
    "precompute":   ("server", "qwen3-30b-a3b"),
}
```

- [x] `qvac_structured.generate_json` accetta `task_type`; il router risolve endpoint+modello
- [x] Config: `QVAC_LOCAL_URL`, `QVAC_SERVER_URL`, `HARDWARE_TIER` (override manuale)
- [x] Test: contratto di risposta identico indipendentemente dal client/base_url risolto (unit, mockato — un vero confronto locale/server richiede il deploy multi-tier di cui sopra)

---

## Fase 1 — Agent loop core con cost control (3–4 giorni)

**Obiettivo**: runner generico, efficiente anche su modelli 4B–8B.

Schema step con vincoli espliciti (i modelli piccoli divagano senza cap):

```python
AGENT_STEP_SCHEMA = {
    "type": "object",
    "required": ["thought", "tool", "args"],
    "properties": {
        "thought": {"type": "string", "maxLength": 300},   # cap anti-divagazione
        "tool":    {"type": "string"},
        "args":    {"type": "object"},
    }
}
```

Cost control integrato nel runner:

| Meccanismo | Regola |
|---|---|
| Troncamento tool result | max ~150 parole nella history; tool `inspect_*` per il testo completo on demand |
| Compressione history | ultimi 4 step completi; step più vecchi ridotti a una riga `step N: tool(args) → esito` |
| Token budget per prompt | Tier B/C: ~3k input / 1k output; Tier A: 6k/1.5k; server: 12k/3k |
| max_steps per tier | locale: 6 (B) / 8 (A); server: 15 |
| Prompt layout | statico prima, history dopo (prefix caching, vedi sopra) |

- [ ] `app/services/agent_runner.py` — loop, dispatch, history compressa, retry JSON
- [ ] `_build_prompt` con layout cache-friendly e budget enforcement
- [ ] `AgentResult` con telemetria: step count, token in/out, tool distribution
- [ ] Unit test: mock `generate_json` — termina su `done`, gestisce tool error, comprime history oltre 4 step, tronca tool result

---

## Fase 2 — Course builder: pipeline + agent escalation (3–4 giorni)

**Obiettivo**: la pipeline deterministica esistente resta l'happy path; l'agente
interviene **solo sui fallimenti**, dove serve davvero capacità di recupero.

```
pipeline batch (esistente, Fasi 2–3 course builder)
    │
    ├── ok ──────────────────────────────→ persist
    │
    └── fallimento → Agent Escalation (server):
          - judge: faithful=false     → revise_lesson con feedback issues (max 2 tentativi)
          - sezione senza chunk       → search_chunks per fonti alternative
          - section tree mancante     → ricostruzione via inspect + search
          - reduce con indici invalidi→ retry mirato col contesto dell'errore
          poi → needs_review se l'escalation fallisce
```

Vantaggi: il 95% dei documenti passa dalla pipeline (costo minimo, comportamento
prevedibile); l'agente lavora su casi piccoli e ben definiti invece di orchestrare
tutto (meno step, meno contesto, meno errori).

- [ ] `app/services/builder_escalation_agent.py` — tool set ristretto: `inspect_chunk`, `search_chunks`, `revise_lesson`, `judge_lesson`, `request_review`, `done`
- [ ] Hook nei punti di fallimento di `outline_service` e `lesson_service`
- [ ] Parallelismo MAP: N job ARQ concorrenti (continuous batching se il runtime lo supporta)
- [ ] Flag `USE_AGENT_ESCALATION` per rollback
- [ ] Test: mock modello — escalation su judge fail produce revise, doppio fallimento produce needs_review

---

## Fase 3 — Precompute pipeline (3–4 giorni)

**Obiettivo**: spostare l'inferenza delle feature di studio dal device al build
batch. Estende la Fase 3 esistente del course builder.

Per ogni lezione, a content generation completata, il server genera e persiste:

| Asset | Quantità | Fonte | Costo runtime studente |
|---|---|---|---|
| Quiz pool | 8–12 domande MCQ taggate per concetto e difficoltà (oggi: 3–4) | chunk sorgente | query DB |
| FAQ anticipate | 5–8 coppie Q&A prevedibili sulla lezione | contenuto lezione | semantic cache hit |
| Flashcard | dal glossario già generato | glossario esistente | zero LLM, solo trasformazione |
| Summary ripasso | 1 per lezione | contenuto lezione | query DB |

- [ ] Migration `0006_precomputed_assets.py` — tabella `lesson_asset` (type, payload_json, content_hash) + tag `concept`/`difficulty` su `question`
- [ ] `app/services/precompute_service.py` — generazione asset, invalidazione via `content_hash` (stesso meccanismo di caching della Fase 3 esistente: sorgenti invariate = niente rigenerazione)
- [ ] FAQ embeddate su QVAC namespace `precomputed_qa`
- [ ] Quiz adattivo: `select_quiz(student_id, lesson_id)` — filtra il pool per concept-tag corrispondenti alle lacune del profilo studente; **zero inferenza**
- [ ] Estendere il job ARQ `generate_course_content` con lo stage `precompute`
- [ ] Test: asset generati e invalidati correttamente al cambio di content_hash

---

## Fase 4 — Memoria episodica (2–3 giorni)

**Obiettivo**: registrare ogni sessione di studio in forma strutturata. (Invariata rispetto a v1, con l'aggiunta dei campi per il consolidamento.)

```sql
CREATE TABLE study_session (
    id           TEXT PRIMARY KEY,
    student_id   TEXT NOT NULL REFERENCES user(id),
    course_id    TEXT NOT NULL REFERENCES course(id),
    started_at   TEXT NOT NULL,
    ended_at     TEXT,
    summary      TEXT,
    duration_sec INTEGER
);

CREATE TABLE session_event (
    id           TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL REFERENCES study_session(id),
    event_type   TEXT NOT NULL,        -- "message" | "quiz_answer" | "lesson_view"
    payload_json TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE TABLE student_fact (
    id           TEXT PRIMARY KEY,
    student_id   TEXT NOT NULL REFERENCES user(id),
    fact         TEXT NOT NULL,        -- "confonde UTXO con account model"
    fact_type    TEXT NOT NULL,        -- "recall_error" | "concept_mastered" | "difficulty"
    concept_tag  TEXT,                 -- collega il fatto ai tag del quiz pool
    confidence   REAL DEFAULT 1.0,     -- decade nel tempo, rinforzata da conferme
    source_session_id TEXT REFERENCES study_session(id),
    created_at   TEXT NOT NULL,
    superseded_by TEXT REFERENCES student_fact(id)   -- consolidamento
);
```

- [ ] Migration `0007_episodic_memory.py`
- [ ] `app/services/session_service.py` — open/close session, append event
- [ ] Hook in `chat_api.py` e `quizzes_api.py`
- [ ] Test: open → events → close, durata calcolata

Il campo `concept_tag` è il collante del sistema: collega gli errori nei quiz
(taggati in Fase 3) ai fatti in memoria, e i fatti alla selezione del quiz adattivo.

---

## Fase 5 — Distillazione + consolidamento memoria (3–4 giorni)

**Obiettivo**: fatti persistenti aggiornati, senza crescita illimitata.

**Distillazione** (post-sessione, routing opportunistico):

```
close_session → ARQ job distill_session
    routing: server online → Qwen3-30B (fatti di qualità, zero carico sul PC)
             offline       → modello locale, tier ≥ B (tier C/D: accodato per il server)
    1. carica eventi sessione
    2. generate_json → {facts: [{fact, fact_type, concept_tag, confidence}]}
    3. persiste student_fact + embed → QVAC student_memory
    4. aggiorna study_session.summary
```

**Consolidamento** (job periodico, ogni N sessioni o settimanale, sempre server):

- fonde duplicati (similarità embedding > 0.9 → merge, confidence rinforzata)
- risolve contraddizioni: `concept_mastered` sostituisce `recall_error` sullo stesso `concept_tag` (via `superseded_by`, mai delete — audit trail)
- decay: confidence × 0.95 per settimana di inattività sul concetto
- cap: max ~200 fatti attivi per studente, eviction per confidence più bassa

**Retrieval budget** (per ogni turno di chat):
- top-8 per similarità embedding dal namespace `student_memory`
- rerank a **top-3** con scoring pesato `0.5·cosine + 0.3·confidence + 0.2·recency` (reranker 0.6B opzionale, solo Tier A/B)
- iniettati nel contesto come blocco compatto (~100 token), non come retrieval separato

- [ ] `app/services/memory_service.py` — distill, embed, upsert, get_student_context
- [ ] `app/services/memory_consolidator.py` + job ARQ periodico
- [ ] Job `distill_session` con routing opportunistico
- [ ] Test: distillazione mock, merge duplicati, supersede su contraddizione, cap enforcement

---

## Fase 6 — Tutor a due percorsi (4–5 giorni)

**Obiettivo**: latenza da chat reale sul 90% dei turni, capacità agentiche solo dove servono.

**Intent Router** — decide il gradino **senza LLM** (~15 ms):

```python
async def route(message: str, session_state: dict) -> str:
    emb = await embed_local(message)                    # Qwen3-Embedding-0.6B

    # gradino 1: semantic cache (FAQ precomputate + risposte recenti)
    hit = await semantic_cache.lookup(emb, scope=session_state["lesson_id"])
    if hit and hit.score > 0.92:
        return "cached"

    # gradino 3: euristiche di complessità (confronti, multi-step, meta-richieste)
    if _is_complex(message, emb):    # similarità con prototipi di intent + euristiche
        return "agent"

    return "fast"                    # gradino 2, default
```

**Fast path** (gradino 2 — il default): una sola chiamata `/generate` in streaming.
Contesto assemblato prima della chiamata, in ordine cache-friendly:

```
[system prompt tutor]                     ← statico, prefix-cached
[memoria studente: top-3 fatti]           ← quasi statico nella sessione
[chunk lezione: top-3 dal retrieval]
[rolling summary conversazione]
[ultimi 4 turni]
[messaggio corrente]
```

**Agent path** (gradino 3 — escalation): `AgentRunner` con tool set tutor:
`search_course`, `search_memory`, `get_progress`, `get_lesson`, `propose_quiz`
(seleziona dal pool precomputato, non genera), `record_concept`, `done`.
Su Tier C/D il gradino 3 viene delegato al server con indicatore di attesa in UI.

**Semantic cache** — scrittura: le risposte del fast path vengono embeddate e
salvate con scope `lesson_id`; invalidazione legata al `content_hash` della lezione
(contenuto rigenerato = cache della lezione svuotata). Le FAQ precomputate (Fase 3)
popolano la cache dal primo giorno — niente cold start.

- [ ] `app/services/intent_router.py` — embedding + prototipi intent + euristiche
- [ ] `app/services/semantic_cache.py` — lookup/store su QVAC `precomputed_qa`, invalidazione per content_hash
- [ ] `app/services/tutor_agent.py` — fast path + agent path
- [ ] `app/services/tutor_tools.py`
- [ ] Aggiornare `chat_api.py` con streaming SSE end-to-end
- [ ] Flag `USE_AGENT_TUTOR`
- [ ] Test: router (cached/fast/agent su casi noti), cache hit/miss/invalidation, memoria iniettata nel contesto

---

## Fase 7 — Context management conversazione (1–2 giorni)

**Obiettivo**: sessioni lunghe senza saturare la KV cache dei device piccoli.

Ibrido **scratchpad strutturato + rolling summary** (più economico della sola
summarization ricorsiva: lo scratchpad si aggiorna con una micro-chiamata o
deterministicamente, il summary si rigenera solo a soglia):

```
scratchpad (JSON, aggiornato ogni turno, ~80 token):
  { "lesson_id": ..., "active_concepts": [...], "open_questions": [...],
    "quiz_in_progress": ..., "student_signals": [...] }

rolling summary (testo, rigenerato ogni 10 turni con LLM locale):
  comprime i turni 1..N-4 preservando fatti salienti

contesto per turno = scratchpad + summary + ultimi 4 turni
```

- [ ] `app/services/context_manager.py` — scratchpad update, compression a soglia
- [ ] Persistenza scratchpad in Redis (working memory), summary su `study_session`
- [ ] Test: compressione a soglia, scratchpad coerente dopo 20+ turni simulati

---

## Fase 8 — Benchmark, eval e rollout (1 settimana)

**Target di latenza** (misurati su Tier B come riferimento; Tier C con tolleranza 2×):

| Operazione | Target | Gradino |
|---|---|---|
| Quiz / flashcard / summary delivery | < 200 ms | 0 |
| Semantic cache hit | < 400 ms | 1 |
| Chat fast path — TTFT | < 1.5 s | 2 |
| Chat fast path — throughput | ≥ 15 tok/s | 2 |
| Agent path — risposta completa | < 20 s con progress in UI | 3 |
| Distillazione sessione (background) | < 30 s server / < 2 min locale | 2/4 |
| Course build, 10 sezioni (batch) | < 10 min | 4 |

**Eval qualità** (il costo hardware si taglia solo se la qualità regge):
- [ ] Set fisso di ~50 domande studente con risposte di riferimento; judge sul server (Qwen3-30B) confronta le risposte del modello di ogni tier
- [ ] Regressione outline/content: stesso documento, confronto pipeline v1 vs v2
- [ ] Verifica JSON compliance dell'agent loop per tier: se il tasso di retry del 4B supera ~10%, il tier C perde l'agent path locale (delega al server)

**Telemetria**:
- [ ] Distribuzione richieste per gradino (obiettivo: ≥ 70% servite dai gradini 0–1)
- [ ] Cache hit rate semantic cache; step count e success rate per agent type
- [ ] Token in/out per turno e per tier

**Rollout**:
- [ ] Feature flag per ogni fase; pipeline v1 attiva fino a stabilizzazione
- [ ] Ordine: precompute (rischio zero) → fast path tutor → memoria → agent escalation → agent path tutor

---

## Roadmap temporale indicativa

```
Settimana 1   Fase 0 (setup, tier, capability matrix) + Fase 1 (agent loop core)
Settimana 2   Fase 2 (builder escalation) + Fase 3 (precompute pipeline)
Settimana 3   Fase 4 (memoria episodica) + Fase 5 (distillazione + consolidamento)
Settimana 4   Fase 6 (tutor due percorsi)
Settimana 5   Fase 7 (context management) + Fase 8 (benchmark, eval, rollout)
```

---

## Note aperte

- **Capability del runtime QVAC**: speculative decoding, prefix caching e KV quant
  dipendono dal backend di inferenza sottostante l'SDK — la matrice di Fase 0 è
  bloccante per stimare le prestazioni reali dei tier. I fallback sono definiti
  per ogni tecnica.
- **Constrained decoding**: quando l'SDK lo esporrà, il retry loop di
  `/generate_json` diventa superfluo sul locale — beneficio maggiore proprio sui
  modelli piccoli (tier C). Da monitorare nelle release dell'SDK.
- **Tier C e agent path**: se l'eval di Fase 8 mostra JSON compliance insufficiente
  sul 4B, il gradino 3 su tier C va sempre delegato al server — il piano lo prevede
  già come degradazione, ma va comunicato in UI ("elaborazione sul server…").
- **Sincronizzazione multi-device**: scratchpad e working memory su Redis server
  (non locale) se lo studente usa più PC; la semantic cache invece può restare
  locale per lezione scaricata.
- **Cold start memoria**: mitigato dalle FAQ precomputate (gradini 0–1 attivi dal
  primo giorno); il tutor degrada a RAG standard finché non esistono fatti distillati.
