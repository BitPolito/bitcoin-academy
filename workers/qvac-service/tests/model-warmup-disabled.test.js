/**
 * Unit test for QVAC_WARMUP_ENABLED=false (#328) — see model-warmup.test.js
 * for why this is a separate file (env vars are read once at import time).
 *
 * @qvac/sdk is fully mocked — no model download or real inference happens.
 */
import { describe, it, mock } from "node:test";
import assert from "node:assert/strict";

const mockEmbed = mock.fn(async () => ({ embedding: [0.1] }));
const mockCompletion = mock.fn(() => ({ text: Promise.resolve("Hi!") }));

await mock.module("@qvac/sdk", {
  namedExports: {
    loadModel: mock.fn(async () => "model-1"),
    unloadModel: mock.fn(),
    close: mock.fn(),
    embed: mockEmbed,
    completion: mockCompletion,
    GTE_LARGE_FP16: {},
    QWEN3_4B_INST_Q4_K_M: {},
  },
});

process.env.QVAC_WARMUP_ENABLED = "false";
const { initModels } = await import("../src/models.js");

describe("model warmup (QVAC_WARMUP_ENABLED=false)", () => {
  it("skips both the embedding and LLM warmup calls", async () => {
    await initModels();

    assert.equal(mockEmbed.mock.calls.length, 0);
    assert.equal(mockCompletion.mock.calls.length, 0);
  });
});
