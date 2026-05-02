/**
 * Unit tests for src/query.js.
 *
 * No LLM is configured (getLlmModelId returns null), so all tests
 * exercise the placeholder path: ragSearch → raw context returned.
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

describe("queryRag — placeholder path (no LLM configured)", () => {
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

  // --- placeholder answer when no LLM ---

  it("answer contains the placeholder note", async () => {
    const { answer } = await queryRag("What is Bitcoin?", "WS1");
    assert.ok(
      answer.includes("[LLM not configured]"),
      `placeholder note missing; got: "${answer.slice(0, 120)}"`
    );
  });

  it("answer includes all retrieved chunk texts", async () => {
    const { answer } = await queryRag("What is Bitcoin?", "WS1");
    for (const r of FAKE_RESULTS) {
      assert.ok(answer.includes(r.content), `chunk text missing from answer: "${r.content}"`);
    }
  });

  // --- sources ---

  it("sources length matches ragSearch result count", async () => {
    const { sources } = await queryRag("What is Bitcoin?", "WS1");
    assert.equal(sources.length, FAKE_RESULTS.length);
  });

  it("each source has score and snippet fields", async () => {
    const { sources } = await queryRag("What is Bitcoin?", "WS1");
    for (const src of sources) {
      assert.ok("score" in src, "source missing score");
      assert.ok("snippet" in src, "source missing snippet");
      assert.equal(typeof src.score, "number");
      assert.equal(typeof src.snippet, "string");
    }
  });

  it("snippet is at most 200 characters", async () => {
    const { sources } = await queryRag("What is Bitcoin?", "WS1");
    for (const src of sources) {
      assert.ok(src.snippet.length <= 200, `snippet too long: ${src.snippet.length}`);
    }
  });

  it("source scores match ragSearch scores in order", async () => {
    const { sources } = await queryRag("What is Bitcoin?", "WS1");
    assert.equal(sources[0].score, FAKE_RESULTS[0].score);
    assert.equal(sources[1].score, FAKE_RESULTS[1].score);
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
