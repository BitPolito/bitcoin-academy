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
    embed: mock.fn(async () => ({ embedding: [0] })),
    completion: mock.fn(() => ({ text: Promise.resolve("") })),
    GTE_LARGE_FP16: {},
    QWEN3_4B_INST_Q4_K_M: {},
  },
});

process.env.QVAC_LLM_ENABLED = "false";
delete process.env.QVAC_MODEL_TRANSPORT;
delete process.env.QVAC_EMB_SRC;
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

it("loads both Docker defaults over HTTPS without losing an explicit embedding override", async (t) => {
  t.after(() => {
    delete process.env.QVAC_MODEL_TRANSPORT;
    delete process.env.QVAC_EMB_SRC;
    process.env.QVAC_LLM_ENABLED = "false";
  });
  process.env.QVAC_MODEL_TRANSPORT = "https";
  process.env.QVAC_LLM_ENABLED = "true";
  mockLoadModel.mock.resetCalls();
  const https = await import("../src/models.js?https");
  await https.initModels();
  const [embedding, llm] = mockLoadModel.mock.calls.map(({ arguments: [options] }) => options);
  assert.match(embedding.modelSrc, /^https:\/\/huggingface\.co\/.*\/gte-large_fp16\.gguf$/);
  assert.match(llm.modelSrc, /^https:\/\/huggingface\.co\/.*\/Qwen3-4B-Q4_K_M\.gguf$/);

  process.env.QVAC_EMB_SRC = "/models/custom.gguf";
  const custom = await import("../src/models.js?custom");
  await custom.reloadEmbeddingModel();
  assert.equal(mockLoadModel.mock.calls.at(-1).arguments[0].modelSrc, "/models/custom.gguf");
});
