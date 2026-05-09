/**
 * Unit tests for src/query.js.
 *
 * No LLM is configured (getLlmModelId returns null), so all tests
 * exercise the no-LLM path: ragSearch → top-1 chunk returned as answer.
 *
 * @qvac/sdk and src/models.js are fully mocked.
 */
import { describe, it, beforeEach, mock } from "node:test";
import assert from "node:assert/strict";

// ---------------------------------------------------------------------------
// SDK mock
// ---------------------------------------------------------------------------

const FAKE_RESULTS = [
  { content: "Bitcoin is a peer-to-peer electronic cash system.", score: 0.92 },
  { content: "Transactions are validated via proof-of-work.",    score: 0.85 },
];

const mockRagSearch = mock.fn(async () => FAKE_RESULTS);

await mock.module("@qvac/sdk", {
  namedExports: {
    ragSearch: mockRagSearch,
    ragIngest: mock.fn(),
    ragDeleteWorkspace: mock.fn(),
    completion: mock.fn(),
    loadModel: mock.fn(),
    unloadModel: mock.fn(),
    startQVACProvider: mock.fn(),
    stopQVACProvider: mock.fn(),
    close: mock.fn(),
    GTE_LARGE_FP16: {},
    QWEN3_4B_INST_Q4_K_M: {},
  },
});

// models.js mock — getLlmModelId returns null (no LLM configured)
const mockGetEmbeddingModelId = mock.fn(() => "test-emb-id");

await mock.module(import.meta.resolve("../src/models.js"), {
  namedExports: {
    getEmbeddingModelId: mockGetEmbeddingModelId,
    getLlmModelId: () => null,
    initModels: mock.fn(),
    shutdownModels: mock.fn(),
  },
});

const { queryRag } = await import("../src/query.js");

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("queryRag — no LLM configured (top-1 answer)", () => {
  beforeEach(() => {
    mockRagSearch.mock.resetCalls();
    mockGetEmbeddingModelId.mock.resetCalls();
    mockRagSearch.mock.restore?.();
    mockGetEmbeddingModelId.mock.restore?.();
  });

  // --- ragSearch call ---

  it("calls ragSearch with the question and workspace", async () => {
    await queryRag("What is a UTXO?", "BTC_2025");
    assert.equal(mockRagSearch.mock.calls.length, 1);
    const arg = mockRagSearch.mock.calls[0].arguments[0];
    assert.equal(arg.query, "What is a UTXO?");
    assert.equal(arg.workspace, "BTC_2025");
  });

  it("passes modelId to ragSearch", async () => {
    await queryRag("Explain SegWit.", "WS1");
    const arg = mockRagSearch.mock.calls[0].arguments[0];
    assert.equal(arg.modelId, "test-emb-id");
  });

  it("passes topK to ragSearch", async () => {
    await queryRag("Explain Merkle trees.", "WS1", 3);
    assert.equal(mockRagSearch.mock.calls[0].arguments[0].topK, 3);
  });

  it("uses topK=5 by default", async () => {
    await queryRag("What is Bitcoin?", "WS1");
    assert.equal(mockRagSearch.mock.calls[0].arguments[0].topK, 5);
  });

  // --- answer when no LLM: top-1 chunk only ---

  it("answer is the top-1 chunk content verbatim", async () => {
    const { answer } = await queryRag("What is Bitcoin?", "WS1");
    assert.equal(answer, FAKE_RESULTS[0].content);
  });

  it("answer does not contain a placeholder note", async () => {
    const { answer } = await queryRag("What is Bitcoin?", "WS1");
    assert.ok(!answer.includes("[LLM not configured]"));
  });

  // --- sources ---

  it("returns exactly one source when no LLM is configured", async () => {
    const { sources } = await queryRag("What is Bitcoin?", "WS1");
    assert.equal(sources.length, 1);
  });

  it("the single source has score and snippet fields", async () => {
    const { sources } = await queryRag("What is Bitcoin?", "WS1");
    assert.ok("score" in sources[0], "source missing score");
    assert.ok("snippet" in sources[0], "source missing snippet");
    assert.equal(typeof sources[0].score, "number");
    assert.equal(typeof sources[0].snippet, "string");
  });

  it("snippet is at most 200 characters", async () => {
    const { sources } = await queryRag("What is Bitcoin?", "WS1");
    assert.ok(sources[0].snippet.length <= 200, `snippet too long: ${sources[0].snippet.length}`);
  });

  it("source score matches top-1 ragSearch score", async () => {
    const { sources } = await queryRag("What is Bitcoin?", "WS1");
    assert.equal(sources[0].score, FAKE_RESULTS[0].score);
  });

  // --- empty corpus ---

  it("returns no-content message when ragSearch returns nothing", async () => {
    mockRagSearch.mock.mockImplementationOnce(async () => []);
    const { answer, sources } = await queryRag("Unknown topic.", "EMPTY_WS");
    assert.ok(answer.toLowerCase().includes("no relevant content"));
    assert.deepEqual(sources, []);
  });

  it("returns empty sources when ragSearch returns nothing", async () => {
    mockRagSearch.mock.mockImplementationOnce(async () => []);
    const { sources } = await queryRag("Unknown topic.", "EMPTY_WS");
    assert.deepEqual(sources, []);
  });

  // --- guard: embedding model not loaded ---

  it("throws when embedding model is not loaded", async () => {
    mockGetEmbeddingModelId.mock.mockImplementationOnce(() => null);
    await assert.rejects(
      () => queryRag("What is Bitcoin?", "WS1"),
      (err) => {
        assert.ok(err.message.includes("Embedding model not loaded"));
        return true;
      }
    );
  });
});
