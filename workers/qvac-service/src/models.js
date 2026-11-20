import * as qvacSdk from "@qvac/sdk";
import {
  loadModel,
  unloadModel,
  close,
  GTE_LARGE_FP16,
  QWEN3_4B_INST_Q4_K_M,
} from "@qvac/sdk";

// Override embedding model via env var; falls back to GTE_LARGE_FP16 (~670 MB).
const EMB_SRC = process.env.QVAC_EMB_SRC ?? GTE_LARGE_FP16;
// Set QVAC_LLM_ENABLED=false to disable LLM generation (retrieval-only mode).
const LLM_ENABLED = process.env.QVAC_LLM_ENABLED !== "false";
// Context window for the LLM. Qwen3-4B supports up to 32K natively; 8192 costs
// ~+0.5 GB of KV cache over the old 4096 default and is required by the course
// builder (outline/lesson generation). Lower to 4096 on RAM-constrained hosts.
const LLM_CTX = parseInt(process.env.QVAC_LLM_CTX ?? "8192", 10);

// Opt-in slide/page image captioning (#325), off by default: it loads a
// second, separate model (a vision-language model + its mm-projector) on top
// of the embedding/LLM models above, which adds meaningful RAM/disk.
const CAPTIONING_ENABLED = process.env.QVAC_CAPTIONING_ENABLED === "true";
// Context window for the vision model. Smaller than the text LLM's — a single
// slide image plus a short prompt fits comfortably in 2048 tokens.
const VISION_CTX = parseInt(process.env.QVAC_VISION_CTX ?? "2048", 10);

// Named vision models this service knows how to request, keyed by the value
// accepted in QVAC_VISION_MODEL. Each resolver reads its modelSrc/projector
// exports lazily, mirroring the embedding-model pattern above.
//
// #325 asks for "Qwen3.5 VL" — no such model is published; @qvac/sdk's
// registry currently ships Qwen3-VL instead. "qwen3vl-2b" is wired up against
// that real model so the captioning path is end-to-end testable today; swap
// this entry for a Qwen3.5 VL registry export if/when one ships.
const VISION_MODELS = {
  "qwen3vl-2b": () => ({
    modelSrc: qvacSdk.QWEN3VL_2B_MULTIMODAL_Q4_K,
    projectionModelSrc: qvacSdk.MMPROJ_QWEN3VL_2B_MULTIMODAL_Q4_K,
  }),
};
const DEFAULT_VISION_MODEL = "qwen3vl-2b";
const VISION_MODEL_NAME = process.env.QVAC_VISION_MODEL ?? DEFAULT_VISION_MODEL;

export function resolveVisionModelSrc(name) {
  const resolver = VISION_MODELS[name];
  if (!resolver) {
    throw new Error(
      `[qvac] unknown QVAC_VISION_MODEL "${name}". Supported values: ${Object.keys(VISION_MODELS).join(", ")}`,
    );
  }
  const { modelSrc, projectionModelSrc } = resolver();
  if (!modelSrc || !projectionModelSrc) {
    throw new Error(
      `[qvac] vision model "${name}" or its projector is not exported by the installed @qvac/sdk version.`,
    );
  }
  return { modelSrc, projectionModelSrc };
}

let embeddingModelId = null;
let llmModelId = null;
let visionModelId = null;

export async function initModels() {
  console.log("[qvac] loading embedding model...");
  embeddingModelId = await loadModel({
    modelSrc: EMB_SRC,
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

  if (CAPTIONING_ENABLED) {
    console.log(`[qvac] loading vision model (${VISION_MODEL_NAME}, ctx_size=${VISION_CTX})...`);
    const { modelSrc, projectionModelSrc } = resolveVisionModelSrc(VISION_MODEL_NAME);
    visionModelId = await loadModel({
      modelSrc,
      modelType: "llm",
      modelConfig: { ctx_size: VISION_CTX, projectionModelSrc },
      onProgress: (p) => process.stdout.write(`\r  ${p.percentage.toFixed(0)}%`),
    });
    console.log("\n[qvac] vision model ready:", visionModelId);
  }
}

export async function shutdownModels() {
  if (llmModelId) await unloadModel({ modelId: llmModelId });
  if (visionModelId) await unloadModel({ modelId: visionModelId });
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
    modelSrc: EMB_SRC,
    modelType: "embeddings",
  });
  console.log("[qvac] embedding model reloaded:", embeddingModelId);
  return embeddingModelId;
}

export function getEmbeddingModelId() { return embeddingModelId; }
export function getLlmModelId() { return llmModelId; }
export function getLlmCtxSize() { return LLM_CTX; }
export function getVisionModelId() { return visionModelId; }
export function isCaptioningEnabled() { return CAPTIONING_ENABLED; }
