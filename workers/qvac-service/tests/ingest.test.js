/**
 * Unit tests for src/ingest.js.
 *
 * @qvac/sdk and src/models.js are fully mocked — no model download happens.
 * Tests run against JSONL data written to a temp directory.
 */
import { describe, it, beforeEach, mock } from "node:test";
import assert from "node:assert/strict";
import { writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// ---------------------------------------------------------------------------
// Temp directory — must be created and registered BEFORE ingest.js is
// imported, because INGEST_DIR is evaluated at module-load time.
// ---------------------------------------------------------------------------

const TMP = join(tmpdir(), `qvac-ingest-test-${Date.now()}`);
mkdirSync(TMP, { recursive: true });
process.env.QVAC_INGEST_DIR = TMP;

// ---------------------------------------------------------------------------
// SDK mock — registered before ingest.js is imported
// ---------------------------------------------------------------------------

const mockRagIngest = mock.fn(async () => ({
  processed: [
    { status: "fulfilled", id: "qvac-id-1" },
    { status: "fulfilled", id: "qvac-id-2" },
  ],
  droppedIndices: [],
}));
const mockRagDeleteWorkspace = mock.fn(async () => {});

await mock.module("@qvac/sdk", {
  namedExports: {
    ragIngest: mockRagIngest,
    ragDeleteWorkspace: mockRagDeleteWorkspace,
    ragSearch: mock.fn(),
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

// models.js mock — use mock.fn() so individual tests can override the return value
const mockGetEmbeddingModelId = mock.fn(() => "test-emb-id");

await mock.module(import.meta.resolve("../src/models.js"), {
  namedExports: {
    getEmbeddingModelId: mockGetEmbeddingModelId,
    getLlmModelId: () => null,
    initModels: mock.fn(),
    shutdownModels: mock.fn(),
  },
});

const { ingestFromJsonl } = await import("../src/ingest.js");

// ---------------------------------------------------------------------------
// Fixture helpers
// ---------------------------------------------------------------------------

function writeJsonl(name, chunks) {
  const path = join(TMP, name);
  writeFileSync(path, chunks.map((c) => JSON.stringify(c)).join("\n"));
  return path;
}

const PARA  = { chunk_type: "paragraph", text: "Bitcoin uses UTXO." };
const PARA2 = { chunk_type: "paragraph", text: "Proof-of-work secures the chain." };
const TABLE = { chunk_type: "table",     text: "| Col1 | Col2 |\n| A    | B    |" };
const SEC   = { chunk_type: "section",   text: "1. Transactions" };
const MICRO = { chunk_type: "micro",     text: "UTXO." };

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ingestFromJsonl", () => {
  beforeEach(() => {
    mockRagIngest.mock.resetCalls();
    mockRagDeleteWorkspace.mock.resetCalls();
    mockGetEmbeddingModelId.mock.resetCalls();
    // Restore default implementation after any per-test override
    mockGetEmbeddingModelId.mock.restore?.();
  });

  // --- happy path ---

  it("calls ragIngest with chunk: false (no re-chunking)", async () => {
    const path = writeJsonl("basic.jsonl", [PARA]);
    await ingestFromJsonl(path, "WS1");
    assert.equal(mockRagIngest.mock.calls.length, 1);
    assert.equal(mockRagIngest.mock.calls[0].arguments[0].chunk, false);
  });

  it("passes the workspace to ragIngest", async () => {
    const path = writeJsonl("ws.jsonl", [PARA]);
    await ingestFromJsonl(path, "BTC_2025");
    assert.equal(mockRagIngest.mock.calls[0].arguments[0].workspace, "BTC_2025");
  });

  it("passes the embedding model id to ragIngest", async () => {
    const path = writeJsonl("model.jsonl", [PARA]);
    await ingestFromJsonl(path, "WS1");
    assert.equal(mockRagIngest.mock.calls[0].arguments[0].modelId, "test-emb-id");
  });

  it("returns the ragIngest result with processed array", async () => {
    const path = writeJsonl("result.jsonl", [PARA]);
    const result = await ingestFromJsonl(path, "WS1");
    assert.equal(result.processed.length, 2);
    assert.equal(result.processed[0].status, "fulfilled");
  });

  // --- filtering ---

  it("indexes paragraph and table chunks — discards section and micro", async () => {
    const path = writeJsonl("mixed.jsonl", [PARA, TABLE, SEC, MICRO]);
    await ingestFromJsonl(path, "WS1");
    const docs = mockRagIngest.mock.calls[0].arguments[0].documents;
    assert.deepEqual(docs, [PARA.text, TABLE.text]);
  });

  it("indexes all paragraph chunks when multiple are present", async () => {
    const path = writeJsonl("multi.jsonl", [PARA, SEC, PARA2, MICRO]);
    await ingestFromJsonl(path, "WS1");
    const docs = mockRagIngest.mock.calls[0].arguments[0].documents;
    assert.deepEqual(docs, [PARA.text, PARA2.text]);
  });

  it("indexes table chunks alongside paragraphs", async () => {
    const path = writeJsonl("with-table.jsonl", [PARA, TABLE]);
    await ingestFromJsonl(path, "WS1");
    const docs = mockRagIngest.mock.calls[0].arguments[0].documents;
    assert.deepEqual(docs, [PARA.text, TABLE.text]);
  });

  it("skips ragIngest entirely when no indexable chunks are found", async () => {
    const path = writeJsonl("no-para.jsonl", [SEC, MICRO]);
    await ingestFromJsonl(path, "WS1");
    assert.equal(mockRagIngest.mock.calls.length, 0);
  });

  // --- rebuild flag ---

  it("calls ragDeleteWorkspace before ingesting when rebuild=true", async () => {
    const path = writeJsonl("rebuild.jsonl", [PARA]);
    await ingestFromJsonl(path, "WS1", true);
    assert.equal(mockRagDeleteWorkspace.mock.calls.length, 1);
    assert.equal(mockRagDeleteWorkspace.mock.calls[0].arguments[0].workspace, "WS1");
  });

  it("calls ragDeleteWorkspace before ragIngest (order matters)", async () => {
    const callOrder = [];
    mockRagDeleteWorkspace.mock.mockImplementationOnce(async () => {
      callOrder.push("delete");
    });
    mockRagIngest.mock.mockImplementationOnce(async () => {
      callOrder.push("ingest");
      return { processed: [], droppedIndices: [] };
    });

    const path = writeJsonl("order.jsonl", [PARA]);
    await ingestFromJsonl(path, "WS1", true);
    assert.deepEqual(callOrder, ["delete", "ingest"]);
  });

  it("does not call ragDeleteWorkspace when rebuild=false", async () => {
    const path = writeJsonl("no-rebuild.jsonl", [PARA]);
    await ingestFromJsonl(path, "WS1", false);
    assert.equal(mockRagDeleteWorkspace.mock.calls.length, 0);
  });

  it("does not call ragDeleteWorkspace by default (rebuild defaults to false)", async () => {
    const path = writeJsonl("default-rebuild.jsonl", [PARA]);
    await ingestFromJsonl(path, "WS1");
    assert.equal(mockRagDeleteWorkspace.mock.calls.length, 0);
  });

  // --- guard: model not loaded ---

  it("throws when embedding model is not loaded", async () => {
    // Override just for this call
    mockGetEmbeddingModelId.mock.mockImplementationOnce(() => null);
    const path = writeJsonl("no-model.jsonl", [PARA]);
    await assert.rejects(
      () => ingestFromJsonl(path, "WS1"),
      (err) => {
        assert.ok(err.message.includes("Embedding model not loaded"));
        return true;
      }
    );
  });
});
