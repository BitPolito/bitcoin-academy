import { readFileSync, existsSync } from "fs";
import path from "path";
import { ragSearch } from "@qvac/sdk";
import { getEmbeddingModelId, getLlmModelId } from "./models.js";

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
 * @returns {{ answer: string }}
 */
export async function generateFromContext(question, contextBlocks, systemPrompt = null) {
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

  const history = [
    {
      role: "system",
      content: systemPrompt || DEFAULT_SYSTEM_PROMPT,
    },
    {
      role: "user",
      content: contextStr
        ? `Contesto:\n${contextStr}\n\nDomanda: ${question}`
        : `Domanda: ${question}`,
    },
  ];

  let answer = "";
  const result = completion({ modelId: llmId, history, stream: false });
  for await (const token of result.tokenStream) {
    answer += token;
  }

  return { answer: _stripMarkdown(answer) };
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
