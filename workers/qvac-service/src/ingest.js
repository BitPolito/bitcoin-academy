import { readFileSync, writeFileSync, existsSync, mkdirSync } from "fs";
import path from "path";
import { ragIngest, ragDeleteWorkspace } from "@qvac/sdk";
import { getEmbeddingModelId, reloadEmbeddingModel } from "./models.js";

const INGEST_DIR = process.env.QVAC_INGEST_DIR ?? "/qvac_ingest";

function metaPath(workspace) {
  return path.join(INGEST_DIR, `${workspace}_meta.json`);
}

function loadMeta(workspace) {
  const p = metaPath(workspace);
  if (!existsSync(p)) return {};
  try {
    return JSON.parse(readFileSync(p, "utf-8"));
  } catch {
    return {};
  }
}

function saveMeta(workspace, meta) {
  // Create the directory on first use: a missing directory made every ingest
  // fail with ENOENT after the documents had already been embedded.
  mkdirSync(INGEST_DIR, { recursive: true });
  writeFileSync(metaPath(workspace), JSON.stringify(meta), "utf-8");
}

/**
 * Reads a JSONL file from the Python ingestion pipeline and indexes
 * paragraph-level chunks into a QVAC HyperDB workspace.
 *
 * Only PARAGRAPH chunks are indexed — SECTION and MICRO chunks exist for
 * context expansion in the Python side but are not retrieval units here.
 * This matches the behavior of the old VerilocalEmbedder with ChromaDB.
 *
 * A sidecar `{workspace}_meta.json` file in QVAC_INGEST_DIR stores the
 * mapping from QVAC-assigned IDs to citation metadata (page, slide, section,
 * label, doc_id) so that query results can carry full citation information.
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

  // Index all child chunks (paragraph + table) — parent chunks are stored in the Python DB.
  const indexableChunks = lines.filter(
    (c) => c.chunk_type === "paragraph" || c.chunk_type === "table"
  );

  if (indexableChunks.length === 0) {
    console.warn("[ingest] no indexable chunks found in", jsonlPath);
    return;
  }

  if (rebuild) {
    await ragDeleteWorkspace({ workspace }).catch(() => {});
    console.log(`[ingest] workspace '${workspace}' dropped`);
    saveMeta(workspace, {});
  }

  console.log(`[ingest] indexing ${indexableChunks.length} chunks into '${workspace}'...`);

  let result;
  try {
    result = await ragIngest({
      modelId,
      workspace,
      documents: indexableChunks.map((c) => c.text),
      chunk: false,
    });
  } catch (err) {
    console.error(`[ingest] embedding failed for '${workspace}':`, err.message);
    // A failed batch leaves the SDK adapter unusable ("Adapter not initialized")
    // until the model is reloaded. The ingest error still reaches the caller.
    await reloadEmbeddingModel().catch((reloadErr) =>
      console.error("[ingest] embedding model reload failed:", reloadErr.message),
    );
    throw err;
  }

  // Build qvac_id → citation + BM25 cross-reference metadata.
  const keptChunks = indexableChunks.filter(
    (_, i) => !result.droppedIndices.includes(i)
  );
  const existingMeta = loadMeta(workspace);
  result.processed.forEach((p, j) => {
    if (p.status === "fulfilled" && p.id && keptChunks[j]) {
      const c = keptChunks[j];
      existingMeta[p.id] = {
        label: c.citation_label ?? "",
        page: c.citation_page ?? 0,
        slide: c.citation_slide ?? 0,
        section: c.citation_section ?? "",
        doc_id: c.doc_id ?? "",
        chunk_id: c.id ?? "",         // original chunk ID for BM25 cross-reference
        parent_id: c.parent_id ?? "", // parent chunk ID for context expansion
      };
    }
  });
  saveMeta(workspace, existingMeta);

  console.log(`[ingest] done. processed: ${result.processed.length}`);
  return result;
}
