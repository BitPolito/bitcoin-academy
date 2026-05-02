import { readFileSync, existsSync } from "fs";
import path from "path";
import { ragSearch } from "@qvac/sdk";
import { getEmbeddingModelId, getLlmModelId } from "./models.js";

const INGEST_DIR = process.env.QVAC_INGEST_DIR ?? "/qvac_ingest";

// Returned when the LLM is not configured.
// FastAPI chat_service.py treats this as a valid answer string.
const LLM_PLACEHOLDER_NOTE =
  "[LLM not configured] Retrieved context shown below. " +
  "Wire up a generation model in src/models.js to get synthesized answers.";

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
 * RAG query: semantic search over the workspace, then optionally generate
 * an answer with the LLM.  When no LLM is configured, returns the raw
 * retrieved chunks instead so the pipeline is still usable end-to-end.
 *
 * topK default of 5 keeps total context well within the 4096-token limit
 * of small quantized models (1500-char chunks × 5 ≈ 1500 tokens).
 *
 * @param {string} question   student's question
 * @param {string} workspace  QVAC workspace name (course_id)
 * @param {number} topK       chunks to retrieve
 * @returns {{ answer: string, sources: { score, snippet, label, page, slide, section, doc_id }[] }}
 */
export async function queryRag(question, workspace, topK = 5) {
  const embModelId = getEmbeddingModelId();
  if (!embModelId) throw new Error("Embedding model not loaded — call initModels() first.");

  const results = await ragSearch({
    modelId: embModelId,
    workspace,
    query: question,
    topK,
  });

  if (results.length === 0) {
    return {
      answer: "No relevant content found for this question in the indexed course material.",
      sources: [],
    };
  }

  const meta = loadMeta(workspace);
  const sources = results.map((r) => {
    const m = meta[r.id] ?? {};
    return {
      score: r.score,
      snippet: r.content.slice(0, 200),
      label: m.label ?? "",
      page: m.page ?? 0,
      slide: m.slide ?? 0,
      section: m.section ?? "",
      doc_id: m.doc_id ?? "",
    };
  });

  const llmId = getLlmModelId();

  if (!llmId) {
    const rawContext = results
      .map((r, i) => `[${i + 1}] ${r.content}`)
      .join("\n\n---\n\n");

    return {
      answer: `${LLM_PLACEHOLDER_NOTE}\n\n${rawContext}`,
      sources,
    };
  }

  const { completion } = await import("@qvac/sdk");

  const history = [
    {
      role: "system",
      content:
        "You are a Bitcoin education assistant for BitPolito Academy. " +
        "Answer the student's question using ONLY the context provided. " +
        "Be concise and precise. Cite the source label (e.g. 'p. 7', 'Slide 5') " +
        "when referencing specific content. " +
        "If the answer is not in the context, say so explicitly.",
    },
    {
      role: "user",
      content:
        `Context:\n${results.map((r, i) => `[${i + 1}] ${r.content}`).join("\n\n---\n\n")}` +
        `\n\nQuestion: ${question}`,
    },
  ];

  let answer = "";
  const result = completion({ modelId: llmId, history, stream: false });
  for await (const token of result.tokenStream) {
    answer += token;
  }

  return { answer, sources };
}
