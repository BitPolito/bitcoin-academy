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

// Opt-in tool-calling layer (#326), off by default: it loads a second model
// instance with llama.cpp's "tools: true" grammar enabled, on top of the
// plain-completion LLM above (same weights can't be shared between a
// tools-enabled and a tools-disabled load, so this doubles that model's RAM
// cost when both are active).
const TOOL_CALLING_ENABLED = process.env.QVAC_TOOL_CALLING_ENABLED === "true";
const TOOL_CTX = parseInt(process.env.QVAC_TOOL_CTX ?? "4096", 10);

// Named tool-calling models this service knows how to request, keyed by the
// value accepted in QVAC_TOOL_MODEL. Mirrors the embedding/vision model
// registries: each resolver reads its export lazily.
//
// #326 asks for "FunctionGemma" — no such model is published by @qvac/sdk.
// Unlike #325's vision model (where a real substitute, Qwen3-VL, existed),
// there's no comparably-named real alternative here, so the default instead
// reuses the Qwen3-4B weights already wired up for plain generation — the
// SDK's own tool-calling example (llamacpp-native-tools.js) uses the same
// kind of general-purpose instruct model with modelConfig.tools=true, not a
// tool-calling-specific checkpoint. "functiongemma" is kept as a selectable
// name that fails fast until/unless the SDK ever exports one.
const TOOL_MODELS = {
  functiongemma: () => qvacSdk.FUNCTIONGEMMA,
  "qwen3-4b-tools": () => QWEN3_4B_INST_Q4_K_M,
};
const DEFAULT_TOOL_MODEL = "qwen3-4b-tools";
const TOOL_MODEL_NAME = process.env.QVAC_TOOL_MODEL ?? DEFAULT_TOOL_MODEL;

export function resolveToolModelSrc(name) {
  const resolver = TOOL_MODELS[name];
  if (!resolver) {
    throw new Error(
      `[qvac] unknown QVAC_TOOL_MODEL "${name}". Supported values: ${Object.keys(TOOL_MODELS).join(", ")}`,
    );
  }
  const modelSrc = resolver();
  if (!modelSrc) {
    throw new Error(
      `[qvac] tool-calling model "${name}" is not exported by the installed @qvac/sdk version. ` +
        `Upgrade @qvac/sdk or set QVAC_TOOL_MODEL=${DEFAULT_TOOL_MODEL}.`,
    );
  }
  return modelSrc;
}

let embeddingModelId = null;
let llmModelId = null;
let toolModelId = null;

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

  if (TOOL_CALLING_ENABLED) {
    console.log(`[qvac] loading tool-calling model (${TOOL_MODEL_NAME}, ctx_size=${TOOL_CTX})...`);
    toolModelId = await loadModel({
      modelSrc: resolveToolModelSrc(TOOL_MODEL_NAME),
      modelType: "llm",
      modelConfig: { ctx_size: TOOL_CTX, tools: true },
      onProgress: (p) => process.stdout.write(`\r  ${p.percentage.toFixed(0)}%`),
    });
    console.log("\n[qvac] tool-calling model ready:", toolModelId);
  }
}

export async function shutdownModels() {
  if (llmModelId) await unloadModel({ modelId: llmModelId });
  if (toolModelId) await unloadModel({ modelId: toolModelId });
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
export function getToolCallingModelId() { return toolModelId; }
export function isToolCallingEnabled() { return TOOL_CALLING_ENABLED; }
