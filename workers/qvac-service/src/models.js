import * as qvacSdk from "@qvac/sdk";
import {
  loadModel,
  unloadModel,
  close,
  GTE_LARGE_FP16,
  QWEN3_4B_INST_Q4_K_M,
} from "@qvac/sdk";

// Named embedding models this service knows how to request, keyed by the
// value accepted in QVAC_EMBEDDING_MODEL. Each resolver reads the matching
// modelSrc export lazily, so adding a name here does not require the
// installed @qvac/sdk version to already export it.
//
// EMBEDDINGGEMMA_300M is not exported by @qvac/sdk@0.9.1 yet (see #324) —
// this entry is wired up ahead of that release so switching the default is a
// one-line env change once it lands, instead of another models.js edit.
const EMBEDDING_MODELS = {
  "gte-large-fp16": () => GTE_LARGE_FP16,
  "embeddinggemma-300m": () => qvacSdk.EMBEDDINGGEMMA_300M,
};
const DEFAULT_EMBEDDING_MODEL = "gte-large-fp16";

export function resolveEmbeddingModelSrc(name) {
  const resolver = EMBEDDING_MODELS[name];
  if (!resolver) {
    throw new Error(
      `[qvac] unknown QVAC_EMBEDDING_MODEL "${name}". Supported values: ${Object.keys(EMBEDDING_MODELS).join(", ")}`,
    );
  }
  const modelSrc = resolver();
  if (!modelSrc) {
    throw new Error(
      `[qvac] embedding model "${name}" is not exported by the installed @qvac/sdk version. ` +
        `Upgrade @qvac/sdk or set QVAC_EMBEDDING_MODEL=${DEFAULT_EMBEDDING_MODEL}.`,
    );
  }
  return modelSrc;
}

// Select the embedding model by name; falls back to gte-large-fp16 (~670 MB).
const EMBEDDING_MODEL_NAME = process.env.QVAC_EMBEDDING_MODEL ?? DEFAULT_EMBEDDING_MODEL;
// Set QVAC_LLM_ENABLED=false to disable LLM generation (retrieval-only mode).
const LLM_ENABLED = process.env.QVAC_LLM_ENABLED !== "false";
// Context window for the LLM. Qwen3-4B supports up to 32K natively; 8192 costs
// ~+0.5 GB of KV cache over the old 4096 default and is required by the course
// builder (outline/lesson generation). Lower to 4096 on RAM-constrained hosts.
const LLM_CTX = parseInt(process.env.QVAC_LLM_CTX ?? "8192", 10);

let embeddingModelId = null;
let llmModelId = null;

export async function initModels() {
  console.log(`[qvac] loading embedding model (${EMBEDDING_MODEL_NAME})...`);
  embeddingModelId = await loadModel({
    modelSrc: resolveEmbeddingModelSrc(EMBEDDING_MODEL_NAME),
    modelType: "embeddings",
    onProgress: (p) => process.stdout.write(`\r  ${p.percentage.toFixed(0)}%`),
  });
  console.log("\n[qvac] embedding model ready:", embeddingModelId);

  if (LLM_ENABLED) {
    console.log(`[qvac] loading LLM (Qwen3-4B Q4_K_M, ctx_size=${LLM_CTX})...`);
    llmModelId = await loadModel({
      modelSrc: QWEN3_4B_INST_Q4_K_M,
      modelType: "llamacpp-completion",
      modelConfig: { ctx_size: LLM_CTX },
      onProgress: (p) => process.stdout.write(`\r  ${p.percentage.toFixed(0)}%`),
    });
    console.log("\n[qvac] LLM ready:", llmModelId);
  }
}

export async function shutdownModels() {
  if (llmModelId) await unloadModel({ modelId: llmModelId });
  if (embeddingModelId) await unloadModel({ modelId: embeddingModelId });
  await close();
}

export async function reloadEmbeddingModel() {
  console.warn("[qvac] reloading embedding model...");
  if (embeddingModelId) {
    await unloadModel({ modelId: embeddingModelId }).catch((err) =>
      console.warn("[qvac] unload of the failed embedding model failed:", err.message),
    );
  }
  embeddingModelId = await loadModel({
    modelSrc: resolveEmbeddingModelSrc(EMBEDDING_MODEL_NAME),
    modelType: "embeddings",
  });
  console.log("[qvac] embedding model reloaded:", embeddingModelId);
  return embeddingModelId;
}

export function getEmbeddingModelId() { return embeddingModelId; }
export function getEmbeddingModelName() { return EMBEDDING_MODEL_NAME; }
export function getLlmModelId() { return llmModelId; }
export function getLlmCtxSize() { return LLM_CTX; }
