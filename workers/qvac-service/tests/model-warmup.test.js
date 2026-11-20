/**
 * Unit tests for model warmup in src/models.js (#328).
 *
 * QVAC_WARMUP_ENABLED and QVAC_LLM_ENABLED are read once at module import, so
 * this file (default: both enabled) and model-warmup-disabled.test.js
 * (QVAC_WARMUP_ENABLED=false) each need their own process — hence separate
 * files, matching the convention already used for models.test.js vs
 * query.test.js.
 *
 * @qvac/sdk is fully mocked — no model download or real inference happens.
 */
import { describe, it, beforeEach, mock } from "node:test";
import assert from "node:assert/strict";

let loadCount = 0;
const mockLoadModel = mock.fn(async () => `model-${++loadCount}`);
const mockEmbed = mock.fn(async () => ({ embedding: [0.1, 0.2, 0.3] }));
const mockCompletion = mock.fn(() => ({ text: Promise.resolve("Hi!") }));

await mock.module("@qvac/sdk", {
  namedExports: {
    loadModel: mockLoadModel,
    unloadModel: mock.fn(),
    close: mock.fn(),
    embed: mockEmbed,
    completion: mockCompletion,
    GTE_LARGE_FP16: {},
    QWEN3_4B_INST_Q4_K_M: {},
  },
});

const { initModels, getEmbeddingModelId, getLlmModelId } = await import("../src/models.js");

describe("model warmup (enabled by default)", () => {
  beforeEach(() => {
    mockEmbed.mock.resetCalls();
    mockCompletion.mock.resetCalls();
  });

  it("warms up the embedding model with a direct embed() call after loading it", async () => {
    await initModels();

    assert.equal(mockEmbed.mock.calls.length, 1);
    assert.equal(mockEmbed.mock.calls[0].arguments[0].modelId, getEmbeddingModelId());
    assert.equal(typeof mockEmbed.mock.calls[0].arguments[0].text, "string");
  });

  it("warms up the LLM with a direct completion() call after loading it", async () => {
    await initModels();

    assert.equal(mockCompletion.mock.calls.length, 1);
    const call = mockCompletion.mock.calls[0].arguments[0];
    assert.equal(call.modelId, getLlmModelId());
    assert.equal(call.stream, false);
  });

  it("does not crash startup when the embedding warmup call fails", async () => {
    mockEmbed.mock.mockImplementationOnce(async () => {
      throw new Error("warmup boom");
    });

    await assert.doesNotReject(() => initModels());
    assert.ok(getEmbeddingModelId());
  });

  it("still warms up the LLM when the embedding warmup failed", async () => {
    mockEmbed.mock.mockImplementationOnce(async () => {
      throw new Error("warmup boom");
    });

    await initModels();

    assert.equal(mockCompletion.mock.calls.length, 1);
  });

  it("does not crash startup when the LLM warmup call fails", async () => {
    mockCompletion.mock.mockImplementationOnce(() => ({ text: Promise.reject(new Error("llm boom")) }));

    await assert.doesNotReject(() => initModels());
    assert.ok(getLlmModelId());
  });
});
