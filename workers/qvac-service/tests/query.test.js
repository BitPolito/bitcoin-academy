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

const { queryRag, retrieveChunks, generateFromContext } = await import("../src/query.js");

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
    // The message is in Italian ("Nessun contenuto rilevante trovato...")
    assert.ok(answer.length > 0, "answer should be non-empty");
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


// ---------------------------------------------------------------------------
// retrieveChunks
// ---------------------------------------------------------------------------

describe("retrieveChunks", () => {
  beforeEach(() => {
    mockRagSearch.mock.resetCalls();
    mockGetEmbeddingModelId.mock.resetCalls();
    mockRagSearch.mock.restore?.();
    mockGetEmbeddingModelId.mock.restore?.();
  });

  it("calls ragSearch with correct params", async () => {
    await retrieveChunks("UTXO question", "BTC_WS", 10);
    const arg = mockRagSearch.mock.calls[0].arguments[0];
    assert.equal(arg.query, "UTXO question");
    assert.equal(arg.workspace, "BTC_WS");
    assert.equal(arg.topK, 10);
  });

  it("returns { chunks } array", async () => {
    const result = await retrieveChunks("What is Bitcoin?", "WS1");
    assert.ok("chunks" in result, "result must have chunks field");
    assert.ok(Array.isArray(result.chunks));
  });

  it("returns empty chunks array when ragSearch returns nothing", async () => {
    mockRagSearch.mock.mockImplementationOnce(async () => []);
    const { chunks } = await retrieveChunks("Unknown.", "EMPTY_WS");
    assert.deepEqual(chunks, []);
  });

  it("each chunk has required citation fields", async () => {
    const { chunks } = await retrieveChunks("What is Bitcoin?", "WS1");
    assert.ok(chunks.length > 0);
    for (const c of chunks) {
      assert.ok("content" in c, "chunk missing content");
      assert.ok("score" in c, "chunk missing score");
      assert.ok("label" in c, "chunk missing label");
      assert.ok("page" in c, "chunk missing page");
      assert.ok("slide" in c, "chunk missing slide");
      assert.ok("doc_id" in c, "chunk missing doc_id");
      assert.ok("parent_id" in c, "chunk missing parent_id");
      assert.ok("chunk_id" in c, "chunk missing chunk_id");
    }
  });

  it("chunk content matches ragSearch result content", async () => {
    const { chunks } = await retrieveChunks("What is Bitcoin?", "WS1");
    assert.equal(chunks[0].content, FAKE_RESULTS[0].content);
  });

  it("throws when embedding model is not loaded", async () => {
    mockGetEmbeddingModelId.mock.mockImplementationOnce(() => null);
    await assert.rejects(
      () => retrieveChunks("What is Bitcoin?", "WS1"),
      (err) => {
        assert.ok(err.message.includes("Embedding model not loaded"));
        return true;
      }
    );
  });
});


// ---------------------------------------------------------------------------
// generateFromContext — no LLM (getLlmModelId returns null)
// ---------------------------------------------------------------------------

describe("generateFromContext — no LLM", () => {
  it("returns first context block text when no LLM is configured", async () => {
    const ctx = [
      { label: "p. 1", text: "Bitcoin is peer-to-peer cash." },
      { label: "p. 2", text: "Miners validate transactions." },
    ];
    const { answer } = await generateFromContext("What is Bitcoin?", ctx);
    assert.equal(answer, ctx[0].text);
  });

  it("returns fallback string when context is empty", async () => {
    const { answer } = await generateFromContext("What is Bitcoin?", []);
    assert.ok(typeof answer === "string");
    assert.ok(answer.length > 0);
  });
});
