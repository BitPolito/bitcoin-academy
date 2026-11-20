/**
 * Unit tests for the embedding model reload in src/models.js.
 *
 * @qvac/sdk is fully mocked — no model download happens.
 */
import { describe, it, beforeEach, mock } from "node:test";
import assert from "node:assert/strict";

let loadCount = 0;
const mockLoadModel = mock.fn(async () => `emb-${++loadCount}`);
const mockUnloadModel = mock.fn(async () => {});

await mock.module("@qvac/sdk", {
  namedExports: {
    loadModel: mockLoadModel,
    unloadModel: mockUnloadModel,
    close: mock.fn(),
    GTE_LARGE_FP16: {},
    QWEN3_4B_INST_Q4_K_M: {},
    // EmbeddingGemma 300M is not published by the installed SDK yet (#324) —
    // omitted here on purpose to exercise the "unsupported model" error path.
  },
});

process.env.QVAC_LLM_ENABLED = "false";
const { initModels, reloadEmbeddingModel, getEmbeddingModelId, getEmbeddingModelName, resolveEmbeddingModelSrc } =
  await import("../src/models.js");

describe("reloadEmbeddingModel", () => {
  beforeEach(() => {
    mockLoadModel.mock.resetCalls();
    mockUnloadModel.mock.resetCalls();
  });

  it("unloads the current embedding model and loads a new one", async () => {
    await initModels();
    const before = getEmbeddingModelId();

    const after = await reloadEmbeddingModel();

    assert.deepEqual(mockUnloadModel.mock.calls[0].arguments[0], { modelId: before });
    assert.equal(mockLoadModel.mock.calls.at(-1).arguments[0].modelType, "embeddings");
    assert.notEqual(after, before);
    assert.equal(getEmbeddingModelId(), after);
  });

  it("still loads a new model when the unload fails", async () => {
    mockUnloadModel.mock.mockImplementationOnce(async () => {
      throw new Error("adapter not initialized");
    });

    const after = await reloadEmbeddingModel();

    assert.equal(mockLoadModel.mock.calls.length, 1);
    assert.equal(getEmbeddingModelId(), after);
  });
});

describe("embedding model selection", () => {
  it("defaults to gte-large-fp16 when QVAC_EMBEDDING_MODEL is unset", () => {
    assert.equal(getEmbeddingModelName(), "gte-large-fp16");
  });

  it("resolves a known model name to its SDK modelSrc", () => {
    assert.doesNotThrow(() => resolveEmbeddingModelSrc("gte-large-fp16"));
  });

  it("rejects an unknown model name", () => {
    assert.throws(() => resolveEmbeddingModelSrc("not-a-real-model"), /unknown QVAC_EMBEDDING_MODEL/);
  });

  it("rejects embeddinggemma-300m until the SDK exports it", () => {
    assert.throws(() => resolveEmbeddingModelSrc("embeddinggemma-300m"), /not exported by the installed @qvac\/sdk/);
  });
});
