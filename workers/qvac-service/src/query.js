import { readFileSync, existsSync } from "fs";
import path from "path";
import { ragSearch } from "@qvac/sdk";
import { getEmbeddingModelId, getLlmModelId } from "./models.js";
import { withLlmLock, withLlmLockGen } from "./llm-queue.js";

const INGEST_DIR = process.env.QVAC_INGEST_DIR ?? "/qvac_ingest";

function loadMeta(workspace) {
  const p = path.join(INGEST_DIR, `${workspace}_meta.json`);
  if (!existsSync(p)) return {};
  try {
    return JSON.parse(readFileSync(p, "utf-8"));
  } catch {
    return {};
  }
}

/**
 * Dense retrieval only — no LLM generation.
 * Returns raw chunks with full citation metadata for Python-side hybrid search + reranking.
 *
 * @param {string} question   student's question
 * @param {string} workspace  QVAC workspace name
 * @param {number} topK       chunks to retrieve
 * @returns {{ chunks: { id, chunk_id, content, score, label, page, slide, section, doc_id, parent_id }[] }}
 */
export async function retrieveChunks(question, workspace, topK = 20) {
  const embModelId = getEmbeddingModelId();
  if (!embModelId) throw new Error("Embedding model not loaded — call initModels() first.");

  const results = await ragSearch({ modelId: embModelId, workspace, query: question, topK });

  if (results.length === 0) return { chunks: [] };

  const meta = loadMeta(workspace);
  const chunks = results.map((r) => {
    const m = meta[r.id] ?? {};
    return {
      id: r.id,                      // QVAC-assigned ID
      chunk_id: m.chunk_id ?? "",    // original pipeline chunk ID (BM25 key)
      content: r.content,
      score: r.score,
      label: m.label ?? "",
      page: m.page ?? 0,
      slide: m.slide ?? 0,
      section: m.section ?? "",
      doc_id: m.doc_id ?? "",
      parent_id: m.parent_id ?? "",
    };
  });

  return { chunks };
}


function _stripMarkdown(text) {
  return text
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/\*{1,3}([^*\n]+)\*{1,3}/g, "$1")
    .replace(/_{1,3}([^_\n]+)_{1,3}/g, "$1")
    .replace(/^\|[\s|:-]+\|\s*$/gm, "")
    .replace(/\n{3,}/g, "\n\n")
    .replace(/(===+|---+)\s*$/g, "")
    .trim();
}

// Strip <think>...</think> blocks produced by reasoning models like Qwen3.
function _stripThinking(text) {
  return text.replace(/<think>[\s\S]*?<\/think>\s*/gi, "").trim();
}

const DEFAULT_SYSTEM_PROMPT =
  "Sei un assistente educativo per BitPolito Academy. " +
  "Rispondi SOLO usando il contesto fornito. " +
  "Scrivi in testo semplice senza markdown (no **, no #, no trattini come elenchi puntati). " +
  "Sintetizza tutto il contesto in UNA SOLA risposta coerente, non una risposta per fonte. " +
  "Cita la fonte tra parentesi (es. 'p. 7', 'Slide 3') quando ti riferisci a contenuti specifici. " +
  "Se la risposta non è nel contesto, dillo esplicitamente. " +
  "Sii conciso: massimo 4 frasi salvo complessità eccezionale della domanda.";

/**
 * LLM generation from pre-built context — no retrieval.
 * Used by the Python service after hybrid search + reranking + parent lookup.
 *
 * @param {string} question        student's question
 * @param {{ label: string, text: string }[]} contextBlocks  pre-selected parent chunks
 * @param {string|null} [systemPrompt]  optional override; falls back to DEFAULT_SYSTEM_PROMPT
 * @param {{ preserveMarkdown?: boolean, enableThinking?: boolean }} [opts]
 *   preserveMarkdown: skip _stripMarkdown (use for structured study action output)
 *   enableThinking: omit /nothink suffix (use for DERIVE to leverage Qwen3 reasoning)
 * @returns {{ answer: string }}
 */
export async function generateFromContext(question, contextBlocks, systemPrompt = null, opts = {}) {
  const { preserveMarkdown = false, enableThinking = false } = opts;
  const llmId = getLlmModelId();

  if (!llmId) {
    const raw = contextBlocks[0]?.text ?? "";
    const snippet = raw.length > 600 ? raw.slice(0, 600).trimEnd() + "…" : raw;
    return {
      answer: raw
        ? "Generazione LLM disabilitata. Passaggio più rilevante trovato:\n\n" + snippet
        : "Nessun contesto disponibile.",
    };
  }

  const { completion } = await import("@qvac/sdk");

  const contextStr = contextBlocks
    .map((b, i) => {
      const label = b.label ? ` [${b.label}]` : "";
      return `[${i + 1}]${label}\n${b.text}`;
    })
    .join("\n\n---\n\n");

  const thinkSuffix = enableThinking ? "" : " /nothink";
  const userContent = contextStr
    ? `Contesto:\n${contextStr}\n\nDomanda: ${question}${thinkSuffix}`
    : `Domanda: ${question}${thinkSuffix}`;

  const history = [
    {
      role: "system",
      content: systemPrompt || DEFAULT_SYSTEM_PROMPT,
    },
    {
      role: "user",
      content: userContent,
    },
  ];

  // stream: false → answer is in result.text (Promise), tokenStream is empty.
  // Serialised through the LLM queue: one completion at a time on the model.
  const rawAnswer = await withLlmLock(async () => {
    const result = completion({ modelId: llmId, history, stream: false });
    return await result.text;
  });

  const cleaned = _stripThinking(rawAnswer || "");
  return { answer: preserveMarkdown ? cleaned : _stripMarkdown(cleaned) };
}


/**
 * Like generateFromContext but yields raw token strings via an async generator.
 * Sends SSE-compatible chunks: each yield is a raw token string.
 * Falls back to yielding the full answer at once when no LLM is loaded.
 *
 * @param {string} question
 * @param {{ label: string, text: string }[]} contextBlocks
 * @param {string|null} [systemPrompt]
 * @param {{ enableThinking?: boolean }} [opts]
 *   enableThinking: omit /nothink suffix (use for DERIVE)
 * @yields {string} individual tokens as they are produced
 */
export async function* streamFromContext(question, contextBlocks, systemPrompt = null, opts = {}) {
  const { enableThinking = false } = opts;
  const llmId = getLlmModelId();

  if (!llmId) {
    const raw = contextBlocks[0]?.text ?? "";
    const snippet = raw.length > 600 ? raw.slice(0, 600).trimEnd() + "…" : raw;
    yield raw
      ? "Generazione LLM disabilitata. Passaggio più rilevante trovato:\n\n" + snippet
      : "Nessun contesto disponibile.";
    return;
  }

  const { completion } = await import("@qvac/sdk");

  const contextStr = contextBlocks
    .map((b, i) => {
      const label = b.label ? ` [${b.label}]` : "";
      return `[${i + 1}]${label}\n${b.text}`;
    })
    .join("\n\n---\n\n");

  const thinkSuffix = enableThinking ? "" : " /nothink";
  const userContent = contextStr
    ? `Contesto:\n${contextStr}\n\nDomanda: ${question}${thinkSuffix}`
    : `Domanda: ${question}${thinkSuffix}`;

  const history = [
    { role: "system", content: systemPrompt || DEFAULT_SYSTEM_PROMPT },
    { role: "user", content: userContent },
  ];

  // Serialised through the LLM queue; the lock is held until the stream ends.
  yield* withLlmLockGen(async function* () {
    const result = completion({ modelId: llmId, history, stream: true });

    // Buffer tokens while inside a <think>...</think> block; only yield post-thinking output.
    let thinking = false;
    let thinkBuf = "";
    for await (const token of result.tokenStream) {
      thinkBuf += token;
      if (!thinking && thinkBuf.includes("<think>")) {
        thinking = true;
      }
      if (thinking) {
        if (thinkBuf.includes("</think>")) {
          thinking = false;
          // Yield any text that came after the closing tag.
          const after = thinkBuf.split("</think>").slice(1).join("</think>").trimStart();
          thinkBuf = "";
          if (after) yield after;
        }
        // Still inside <think> — swallow the token.
        continue;
      }
      // Normal token — flush the buffer and yield.
      if (thinkBuf) {
        yield thinkBuf;
        thinkBuf = "";
      }
    }
    // Flush any remaining buffer (e.g. model ended without </think>).
    if (thinkBuf && !thinking) yield thinkBuf;
  });
}


/**
 * RAG query: semantic search over the workspace, then optionally generate
 * an answer with the LLM.  When no LLM is configured, returns the raw
 * retrieved chunks instead so the pipeline is still usable end-to-end.
 *
 * topK controls how many chunks are retrieved (higher = better recall for reranking).
 * topKGenerate limits how many retrieved chunks are sent to the LLM (context window budget).
 * The Python chat_service retrieves topK=20 and reranks externally; it passes
 * topKGenerate=5 to keep the LLM context within the 4096-token window of Qwen3-4B Q4.
 *
 * @param {string} question      student's question
 * @param {string} workspace     QVAC workspace name (course_id)
 * @param {number} topK          chunks to retrieve from the vector store
 * @param {number} topKGenerate  chunks to pass to the LLM (≤ topK)
 * @returns {{ answer: string, sources: { score, snippet, label, page, slide, section, doc_id }[] }}
 */
export async function queryRag(question, workspace, topK = 5, topKGenerate = 5) {
  // Retrieve dense chunks.
  const { chunks } = await retrieveChunks(question, workspace, topK);

  if (chunks.length === 0) {
    return {
      answer: "Nessun contenuto rilevante trovato per questa domanda nel materiale del corso.",
      sources: [],
    };
  }

  const sources = chunks.map((c) => ({
    score: c.score,
    snippet: c.content.slice(0, 200),
    label: c.label,
    page: c.page,
    slide: c.slide,
    section: c.section,
    doc_id: c.doc_id,
    chunk_id: c.chunk_id,
    parent_id: c.parent_id,
  }));

  const llmId = getLlmModelId();
  if (!llmId) {
    const raw = chunks[0].content;
    const snippet = raw.length > 600 ? raw.slice(0, 600).trimEnd() + "…" : raw;
    return {
      answer: "Generazione LLM disabilitata. Passaggio più rilevante trovato:\n\n" + snippet,
      sources: sources.slice(0, 1),
    };
  }

  // Build context for LLM (capped at topKGenerate chunks).
  const contextBlocks = chunks.slice(0, topKGenerate).map((c) => ({
    label: c.label,
    text: c.content,
  }));

  const { answer } = await generateFromContext(question, contextBlocks);
  return { answer, sources };
}
