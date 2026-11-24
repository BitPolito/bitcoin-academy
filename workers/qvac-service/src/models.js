import {
  loadModel,
  unloadModel,
  close,
  GTE_LARGE_FP16,
  QWEN3_4B_INST_Q4_K_M,
} from "@qvac/sdk";

const useHttps = process.env.QVAC_MODEL_TRANSPORT === "https";
const EMB_HTTPS = "https://huggingface.co/ChristianAzinn/gte-large-gguf/resolve/f9fa5479908e72c2a8b9d6ba112911cd1e51be53/gte-large_fp16.gguf";
const LLM_HTTPS = "https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q4_K_M.gguf";
const EMB_SRC = process.env.QVAC_EMB_SRC || (useHttps ? EMB_HTTPS : GTE_LARGE_FP16);
const LLM_SRC = useHttps ? LLM_HTTPS : QWEN3_4B_INST_Q4_K_M;
// Set QVAC_LLM_ENABLED=false to disable LLM generation (retrieval-only mode).
const LLM_ENABLED = process.env.QVAC_LLM_ENABLED !== "false";
// Context window for the LLM. Qwen3-4B supports up to 32K natively; 8192 costs
// ~+0.5 GB of KV cache over the old 4096 default and is required by the course
// builder (outline/lesson generation). Lower to 4096 on RAM-constrained hosts.
const LLM_CTX = parseInt(process.env.QVAC_LLM_CTX ?? "8192", 10);

let embeddingModelId = null;
let llmModelId = null;

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
      modelSrc: LLM_SRC,
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
    modelSrc: EMB_SRC,
    modelType: "embeddings",
  });
  console.log("[qvac] embedding model reloaded:", embeddingModelId);
  return embeddingModelId;
}

export function getEmbeddingModelId() { return embeddingModelId; }
export function getLlmModelId() { return llmModelId; }
export function getLlmCtxSize() { return LLM_CTX; }
