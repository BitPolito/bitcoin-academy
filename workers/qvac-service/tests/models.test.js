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
  },
});

process.env.QVAC_LLM_ENABLED = "false";
const { initModels, reloadEmbeddingModel, getEmbeddingModelId } = await import("../src/models.js");

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
