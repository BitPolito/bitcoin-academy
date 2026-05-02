import {
  loadModel,
  unloadModel,
  startQVACProvider,
  stopQVACProvider,
  close,
  GTE_LARGE_FP16,
} from "@qvac/sdk";

// Override embedding model via env var; falls back to GTE_LARGE_FP16 (~670 MB).
const EMB_SRC = process.env.QVAC_EMB_SRC ?? GTE_LARGE_FP16;

let embeddingModelId = null;

// LLM generation is not configured yet.
// query.js returns raw retrieved context until a model is wired in here.
// To add one: loadModel({ modelSrc: QWEN3_4B_INST_Q4_K_M, modelType: "llm" })
// and export getLlmModelId() returning its id.

export async function initModels() {
  await startQVACProvider();

  console.log("[qvac] loading embedding model...");
  embeddingModelId = await loadModel({
    modelSrc: EMB_SRC,
    modelType: "embeddings",
    onProgress: (p) => process.stdout.write(`\r  ${p.percentage.toFixed(0)}%`),
  });
  console.log("\n[qvac] embedding model ready:", embeddingModelId);
}

export async function shutdownModels() {
  if (embeddingModelId) await unloadModel({ modelId: embeddingModelId });
  await stopQVACProvider();
  await close();
}

export function getEmbeddingModelId() { return embeddingModelId; }

// Returns null until an LLM is configured above.
export function getLlmModelId() { return null; }
