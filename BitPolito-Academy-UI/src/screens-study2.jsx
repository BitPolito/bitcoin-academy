// Study workspace — split-pane source/output + evidence drawer.

const { useState: _u3, useEffect: _e3, useRef: _r3 } = React;

function StudyScreen({ layoutVariant = "split" }) {
  const D = window.ACADEMY_DATA;
  const [action, setAction] = _u3("explain");
  const [query, setQuery] = _u3(D.generated.query);
  const [running, setRunning] = _u3(false);
  const [hovered, setHovered] = _u3(null);
  const [activeEv, setActiveEv] = _u3("ev-1");
  const [showInspect, setShowInspect] = _u3(false);
  const [evDrawer, setEvDrawer] = _u3(true);

  const runStudy = () => {
    setRunning(true);
    setTimeout(() => setRunning(false), 1400);
  };

  // Power layout swaps source (right) and output (left)
  const sourceLeft = layoutVariant !== "power";

  return (
    <div className="page-fade max-w-[1480px] mx-auto px-6 py-5">
      {/* Action bar */}
      <div className="b-hard rounded-lg bg-white dark:bg-blue-dark/30 mb-4">
        <div className="flex items-stretch">
          {/* Action selector */}
          <div className="flex-1 p-4 b-thin-r">
            <SectionHead left="Study action" right="press to switch · ⌘E/S/R/O/Q/L/D/C" />
            <div className="grid grid-cols-4 gap-2">
              {D.studyActions.map(a => (
                <button key={a.id} onClick={() => setAction(a.id)}
                  className={"text-left p-2.5 rounded-md b-thin-1 transition-all " +
                    (action === a.id
                      ? "bg-blue-dark text-white dark:bg-white dark:text-blue-dark"
                      : "hover:bg-blue-dark/5 dark:hover:bg-white/10")}
                  style={{border:"1px solid currentColor"}}>
                  <div className="flex items-center gap-2">
                    <span className="mono text-base leading-none w-5">{a.glyph}</span>
                    <span className="text-[12.5px] font-medium leading-tight">{a.label}</span>
                    <span className="ml-auto mono text-[9px] opacity-60">⌘{a.shortcut}</span>
                  </div>
                  <div className="font-mono text-[10px] opacity-70 mt-1.5 leading-snug">{a.sub}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Query + scope */}
          <div className="w-[460px] p-4 flex flex-col">
            <SectionHead left={"Query · " + (D.studyActions.find(a=>a.id===action)?.label || "")}
                         right={running ? "running…" : "ready"} />
            <textarea value={query} onChange={e => setQuery(e.target.value)}
              className="flex-1 w-full b-thin-1 rounded-md p-3 bg-transparent outline-none resize-none text-[13.5px] leading-relaxed"
              style={{border:"1px solid currentColor", minHeight: 110}}
              placeholder="Ask the source. e.g. 'Explain why R < H(X) is unachievable…'" />
            <div className="flex items-center gap-2 mt-3">
              <span className="chip" style={{border:"1px solid currentColor"}}>
                ⌖ scope · L05 + L06 + Cover&Thomas
              </span>
              <span className="chip" style={{border:"1px solid currentColor"}}>k=8 · rerank</span>
              <button onClick={runStudy} disabled={running} className="btn-primary ml-auto">
                {running ? "Generating…" : "Run study →"}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Split workspace */}
      <div className="grid grid-cols-12 gap-4">
        {sourceLeft ? <SourcePane onAnchor={(id) => setActiveEv(id)} hoveredCite={hovered} /> : <OutputPane data={D.generated} hovered={hovered} setHovered={setHovered} setActiveEv={setActiveEv} running={running} />}
        {sourceLeft ? <OutputPane data={D.generated} hovered={hovered} setHovered={setHovered} setActiveEv={setActiveEv} running={running} /> : <SourcePane onAnchor={(id) => setActiveEv(id)} hoveredCite={hovered} />}
      </div>

      {/* Evidence + Inspect drawers */}
      <div className="mt-4">
        <div className="flex items-center gap-2 mb-2">
          <button onClick={() => setEvDrawer(v => !v)}
            className={"font-mono text-[11px] tracking-[0.18em] uppercase px-3 h-8 rounded-md b-thin " + (evDrawer ? "bg-blue-dark text-white dark:bg-white dark:text-blue-dark" : "")}>
            {evDrawer ? "▾" : "▸"} Evidence pack · {D.evidence.length}
          </button>
          <button onClick={() => setShowInspect(v => !v)}
            className={"font-mono text-[11px] tracking-[0.18em] uppercase px-3 h-8 rounded-md b-thin " + (showInspect ? "bg-blue-dark text-white dark:bg-white dark:text-blue-dark" : "")}>
            {showInspect ? "▾" : "▸"} Inspect · retrieval & parser
          </button>
          <span className="ml-auto font-mono text-[11px] opacity-60">
            {D.generated.tokensIn} ctx · {D.generated.tokensOut} out · {D.generated.model}
          </span>
        </div>

        {evDrawer ? (
          <EvidenceDrawer items={D.evidence} active={activeEv} setActive={setActiveEv}
                          hovered={hovered} setHovered={setHovered} />
        ) : null}

        {showInspect ? <InspectDrawer /> : null}
      </div>
    </div>
  );
}

// ---------- Source pane (left) ----------
function SourcePane({ onAnchor, hoveredCite }) {
  const D = window.ACADEMY_DATA;
  const doc = D.openDoc;
  return (
    <section className="col-span-12 lg:col-span-6 b-hard rounded-lg bg-white dark:bg-blue-dark/30 flex flex-col"
             style={{minHeight: 580}}>
      <div className="px-5 py-3 b-thin-b flex items-center gap-3">
        <span className="mono text-[10px] tracking-[0.22em] uppercase opacity-70">Source</span>
        <span className="font-medium text-sm truncate">{doc.name}</span>
        <span className="ml-auto mono text-[11px] opacity-70">page 17 / 42 · §4</span>
      </div>
      <div className="p-5 ws-scroll overflow-auto flex-1">
        <div className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70 mb-1">Slide 17</div>
        <h3 className="text-xl font-medium mb-4">{doc.parsed.title}</h3>

        <ul className="space-y-3 mb-5">
          {doc.parsed.bullets.map((b, i) => (
            <li key={i}
                className={"text-[13.5px] leading-relaxed flex gap-3 px-2 py-1.5 rounded-sm " +
                  (hoveredCite && (
                    (hoveredCite === "ev-1" && (i === 1)) ||
                    (hoveredCite === "ev-3" && (i === 2))
                  ) ? "cite-hl" : "")}>
              <span className="mono opacity-60 mt-0.5">▸</span>
              <span>{b}</span>
            </li>
          ))}
        </ul>

        <div className="font-mono text-[14px] b-thin-1 rounded-sm px-3 py-2 inline-block mb-5"
             style={{border:"1px solid currentColor"}}>
          {doc.parsed.formula}
        </div>

        <div className="b-thin-1 stripes rounded-md mb-2 flex items-center justify-center"
             style={{border:"1px solid currentColor", aspectRatio: "16/8"}}>
          <span className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70">Fig 5.4 · figure placeholder</span>
        </div>
        <div className="font-mono text-[10px] opacity-60">{doc.parsed.cap}</div>

        <div className="mt-6 b-thin-t pt-4">
          <div className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70 mb-2">
            Adjacent passages · auto-pulled
          </div>
          <div className="space-y-2">
            <MiniPassage anchor="p.18 · §4" text="…the bound is tight up to a single bit per source symbol because only one extra bit is needed for prefix-free indexing of |T_ε^(n)|…" />
            <MiniPassage anchor="C&T · p.62" text="…H(X) ≤ L < H(X) + 1 — with the upper bound achieved by Shannon-Fano and the lower bound by Kraft's inequality applied to optimal codes…" />
          </div>
        </div>
      </div>

      <div className="px-5 py-3 b-thin-t flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button className="btn-ghost">‹ p.16</button>
          <button className="btn-ghost">p.18 ›</button>
        </div>
        <span className="mono text-[11px] opacity-70">scroll-locked to citation</span>
      </div>
    </section>
  );
}

function MiniPassage({ anchor, text }) {
  return (
    <div className="b-thin rounded-md p-3">
      <div className="font-mono text-[10px] tracking-[0.18em] uppercase opacity-70">{anchor}</div>
      <div className="text-[12.5px] leading-snug opacity-90 mt-1">{text}</div>
    </div>
  );
}

// ---------- Output pane (right) ----------
function OutputPane({ data, hovered, setHovered, setActiveEv, running }) {
  return (
    <section className="col-span-12 lg:col-span-6 b-hard rounded-lg bg-white dark:bg-blue-dark/30 flex flex-col"
             style={{minHeight: 580}}>
      <div className="px-5 py-3 b-thin-b flex items-center gap-3">
        <span className="mono text-[10px] tracking-[0.22em] uppercase opacity-70">Generated · explain</span>
        <span className="font-medium text-sm truncate">Source Coding Theorem</span>
        <span className="ml-auto mono text-[11px] opacity-70">{data.timestamp} · 5 sources</span>
      </div>

      <div className="p-5 ws-scroll overflow-auto flex-1 relative">
        {running ? (
          <div className="absolute inset-0 bg-white/70 dark:bg-blue-dark/70 z-10 flex flex-col items-center justify-center">
            <div className="mono text-[11px] tracking-[0.22em] uppercase mb-3 opacity-80">retrieving · reranking · generating</div>
            <div className="w-64 h-1.5 bar-stripes" style={{background:"#001CE0"}}/>
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2 mb-4">
          {data.flags.map((f, i) => (
            <span key={i} className="chip"
                  style={{border:"1px solid", color: f.kind === "ok" ? "#1a7f3a" : "#a55a00", borderColor: f.kind === "ok" ? "#1a7f3a" : "#a55a00"}}>
              {f.kind === "ok" ? "✓" : "!"} {f.label}
            </span>
          ))}
        </div>

        {data.body.map((sec, si) => (
          <div key={si} className="mb-5">
            <div className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70 mb-2">{sec.h}</div>
            <p className="text-[13.5px] leading-relaxed">
              {sec.p.map((seg, i) => {
                const content = seg.code
                  ? <span className="mono text-[12.5px] b-thin-1 rounded-sm px-1.5 py-0.5 mx-0.5 inline-block"
                          style={{border:"1px solid currentColor"}}>{seg.t}</span>
                  : seg.t;
                if (seg.c) {
                  return <Cite key={i} id={seg.c} active={hovered === seg.c}
                               onHover={(id) => { setHovered(id); if (id) setActiveEv(id); }}
                               onClick={(id) => setActiveEv(id)}>{content}</Cite>;
                }
                return <React.Fragment key={i}>{content}</React.Fragment>;
              })}
            </p>
          </div>
        ))}

        <div className="b-thin-t pt-4 mt-4">
          <div className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70 mb-2">Suggested next actions</div>
          <div className="flex flex-wrap gap-2">
            <button className="btn-ghost">∂  Derive achievability</button>
            <button className="btn-ghost">▢  Quiz me on this section</button>
            <button className="btn-ghost">◉  Oral-exam follow-ups</button>
          </div>
        </div>
      </div>

      <div className="px-5 py-3 b-thin-t flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button className="btn-ghost">↺ Re-run</button>
          <button className="btn-ghost">＋ Add to notebook</button>
        </div>
        <span className="mono text-[11px] opacity-70">grounded · {data.tokensOut} tokens</span>
      </div>
    </section>
  );
}

// ---------- Evidence drawer ----------
function EvidenceDrawer({ items, active, setActive, hovered, setHovered }) {
  return (
    <div className="b-hard rounded-lg bg-white dark:bg-blue-dark/30 p-4">
      <div className="flex items-center gap-3 mb-3">
        <SectionHead left="Evidence pack" right={items.length + " passages · k=8 → reranked → 5"} className="flex-1 mb-0" />
      </div>
      <div className="grid grid-cols-12 gap-3">
        <div className="col-span-12 lg:col-span-7 space-y-2">
          {items.map((ev, i) => (
            <div key={ev.id}
                 onClick={() => setActive(ev.id)}
                 onMouseEnter={() => setHovered(ev.id)}
                 onMouseLeave={() => setHovered(null)}
                 className={"b-thin-1 rounded-md p-3 cursor-pointer transition-all " +
                   (active === ev.id ? "bg-blue-dark/8 dark:bg-white/10" : "hover:bg-blue-dark/5 dark:hover:bg-white/5")}
                 style={{border:"1px solid currentColor"}}>
              <div className="flex items-center gap-3 mb-1.5">
                <span className="mono text-[10px] tracking-[0.18em] uppercase opacity-70">[{i+1}]</span>
                <span className="text-[12.5px] font-medium truncate">{ev.docName}</span>
                <span className="ml-auto chip" style={{border:"1px solid currentColor"}}>{ev.kind}</span>
                {ev.lang === "it" ? <span className="chip" style={{border:"1px solid currentColor"}}>IT → EN</span> : null}
              </div>
              <div className="font-mono text-[10px] opacity-70 mb-2">
                {ev.anchor} · score {ev.score.toFixed(3)} · rerank {ev.rerank.toFixed(3)}
              </div>
              <div className="text-[12.5px] leading-snug opacity-95">{ev.preview}</div>
              <div className="flex items-center gap-3 mt-2 b-thin-t pt-2">
                <button className="font-mono text-[10px] tracking-[0.18em] uppercase opacity-80 hover:opacity-100">→ open in viewer</button>
                <button className="font-mono text-[10px] tracking-[0.18em] uppercase opacity-80 hover:opacity-100">⌖ pin</button>
                <button className="font-mono text-[10px] tracking-[0.18em] uppercase opacity-80 hover:opacity-100">⊘ exclude</button>
                <span className="ml-auto mono text-[10px] opacity-60">id · {ev.id}</span>
              </div>
            </div>
          ))}
        </div>
        <div className="col-span-12 lg:col-span-5">
          <div className="b-thin-1 rounded-md p-3 mb-3" style={{border:"1px solid currentColor"}}>
            <div className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70 mb-2">Composition</div>
            <ScoreBars items={items} />
          </div>
          <div className="b-thin-1 rounded-md p-3" style={{border:"1px solid currentColor"}}>
            <div className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70 mb-2">By source</div>
            <ul className="space-y-1.5 text-[12px]">
              <Bar label="L05 — Source Coding Theorem.pdf" pct={42} />
              <Bar label="Cover & Thomas — Ch.7" pct={26} />
              <Bar label="L04 — Entropy & MI"  pct={18} />
              <Bar label="Past exam — 2024-07" pct={14} />
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

function ScoreBars({ items }) {
  return (
    <div className="space-y-1.5">
      {items.map((ev, i) => (
        <div key={ev.id} className="flex items-center gap-2">
          <span className="mono text-[10px] opacity-70 w-5">[{i+1}]</span>
          <div className="flex-1 h-3 b-thin-1" style={{border:"1px solid currentColor", position: "relative"}}>
            <div className="h-full" style={{width: (ev.score * 100) + "%", background: "#001CE0", opacity: 0.4}} />
            <div className="absolute top-0 left-0 h-full" style={{width: (ev.rerank * 100) + "%", background: "#001CE0"}} />
          </div>
          <span className="mono text-[10px] tnum opacity-70 w-16 text-right">{ev.rerank.toFixed(3)}</span>
        </div>
      ))}
      <div className="flex items-center gap-3 pt-2 b-thin-t mt-2 font-mono text-[10px] opacity-70">
        <span><span className="inline-block w-2.5 h-2.5 align-middle mr-1" style={{background:"#001CE0", opacity:0.4}}/>retrieval</span>
        <span><span className="inline-block w-2.5 h-2.5 align-middle mr-1" style={{background:"#001CE0"}}/>rerank</span>
      </div>
    </div>
  );
}

function Bar({ label, pct }) {
  return (
    <li>
      <div className="flex items-center justify-between font-mono text-[11px] mb-0.5">
        <span className="truncate opacity-90">{label}</span>
        <span className="opacity-70 tnum">{pct}%</span>
      </div>
      <div className="h-1.5 b-thin-1" style={{border:"1px solid currentColor"}}>
        <div className="h-full" style={{width: pct + "%", background:"#001CE0"}} />
      </div>
    </li>
  );
}

function InspectDrawer() {
  return (
    <div className="b-hard rounded-lg bg-white dark:bg-blue-dark/30 p-4 mt-2">
      <SectionHead left="Inspect · debug · MVP-only" right="ctrl·⇧·I to toggle" />
      <div className="grid grid-cols-12 gap-3">
        <Pre title="parser.log" lines={[
          "[doc-01] parse … 318 chunks · 12,418 tok · 2.1s",
          "[doc-01] embed (qvac/all-mpnet) · 318 vecs · 1.4s",
          "[doc-01] index · IVF-Flat · nlist=64 · ok",
          "[doc-05] ocr-fallback · tesseract · conf 0.81",
          "[doc-07] FAIL · xref @ byte 184902",
        ]}/>
        <Pre title="retrieval.trace" lines={[
          "query.embed = [0.214, -0.012, 0.318, …]",
          "ann.search(k=24) → 24 candidates · 38ms",
          "filter(course=info-theory) → 21",
          "rerank(cross-encoder) → 8 · 142ms",
          "evidence.pack(top=5, max_tok=4218)",
        ]}/>
        <Pre title="evidence.json" lines={[
          "{",
          "  \"action\": \"explain\",",
          "  \"k\": 5,",
          "  \"sources\": [\"doc-01\", \"doc-03\", \"doc-08\", \"doc-04\"],",
          "  \"diversity\": 0.62,",
          "  \"coverage_§4\": 0.91 ",
          "}",
        ]}/>
      </div>
    </div>
  );
}

function Pre({ title, lines }) {
  return (
    <div className="col-span-12 md:col-span-4 b-thin-1 rounded-md p-0 overflow-hidden" style={{border:"1px solid currentColor"}}>
      <div className="px-3 py-2 b-thin-b font-mono text-[10px] tracking-[0.22em] uppercase opacity-70">{title}</div>
      <pre className="font-mono text-[11px] leading-[1.55] p-3 whitespace-pre-wrap m-0">
        {lines.join("\n")}
      </pre>
    </div>
  );
}

Object.assign(window, { StudyScreen });
