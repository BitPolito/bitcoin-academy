import { readFileSync } from "fs";
import { ragIngest, ragDeleteWorkspace } from "@qvac/sdk";
import { getEmbeddingModelId } from "./models.js";

/**
 * Reads a JSONL file from the Python ingestion pipeline and indexes
 * paragraph-level chunks into a QVAC HyperDB workspace.
 *
 * Only PARAGRAPH chunks are indexed — SECTION and MICRO chunks exist for
 * context expansion in the Python side but are not retrieval units here.
 * This matches the behavior of the old VerilocalEmbedder with ChromaDB.
 *
 * @param {string}  jsonlPath  absolute path to the *_contingency.jsonl file
 * @param {string}  workspace  workspace name; use course_id for per-course isolation
 * @param {boolean} rebuild    drop the existing workspace before ingesting
 */
export async function ingestFromJsonl(jsonlPath, workspace, rebuild = false) {
  const modelId = getEmbeddingModelId();
  if (!modelId) throw new Error("Embedding model not loaded — call initModels() first.");

  const lines = readFileSync(jsonlPath, "utf-8")
    .split("\n")
    .filter(Boolean)
    .map((l) => JSON.parse(l));

  const paragraphChunks = lines.filter((c) => c.chunk_type === "paragraph");

  if (paragraphChunks.length === 0) {
    console.warn("[ingest] no paragraph chunks found in", jsonlPath);
    return;
  }

  if (rebuild) {
    // Silently ignore errors — workspace may not exist on first run.
    await ragDeleteWorkspace({ workspace }).catch(() => {});
    console.log(`[ingest] workspace '${workspace}' dropped`);
  }

  console.log(`[ingest] indexing ${paragraphChunks.length} chunks into '${workspace}'...`);

  // chunk: false — the Python pipeline already split the text; don't re-chunk.
  const result = await ragIngest({
    modelId,
    workspace,
    documents: paragraphChunks.map((c) => c.text),
    chunk: false,
  });

  console.log(`[ingest] done. processed: ${result.processed.length}`);
  return result;
}
