/**
 * Unit tests for src/tools.js (#326).
 *
 * Operates on a real temp directory under os.tmpdir() set as QVAC_INGEST_DIR
 * before the module is imported (INGEST_DIR is read once at module load).
 */
import { describe, it, before, after } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile, mkdir, rm } from "fs/promises";
import { tmpdir } from "os";
import path from "path";

let tmpDir;
let toolDefinitions, executeTool;

before(async () => {
  tmpDir = await mkdtemp(path.join(tmpdir(), "qvac-tools-test-"));
  await writeFile(path.join(tmpDir, "notes.txt"), "line one\nBitcoin uses proof-of-work\nline three\n");
  await mkdir(path.join(tmpDir, "sub"));
  await writeFile(path.join(tmpDir, "sub", "nested.txt"), "nested content");

  process.env.QVAC_INGEST_DIR = tmpDir;
  ({ toolDefinitions, executeTool } = await import("../src/tools.js"));
});

after(async () => {
  await rm(tmpDir, { recursive: true, force: true });
});

describe("toolDefinitions", () => {
  it("exposes read_file, list_files and grep, and nothing else", () => {
    const names = toolDefinitions().map((t) => t.name).sort();
    assert.deepEqual(names, ["grep", "list_files", "read_file"]);
  });

  it("each definition has a name, description and parameters schema", () => {
    for (const tool of toolDefinitions()) {
      assert.equal(typeof tool.name, "string");
      assert.equal(typeof tool.description, "string");
      assert.ok(tool.parameters);
    }
  });
});

describe("executeTool — read_file", () => {
  it("reads a file relative to the ingest directory", async () => {
    const content = await executeTool("read_file", { path: "notes.txt" });
    assert.match(content, /proof-of-work/);
  });

  it("truncates content longer than maxChars", async () => {
    const content = await executeTool("read_file", { path: "notes.txt", maxChars: 5 });
    assert.ok(content.startsWith("line "));
    assert.match(content, /truncated/);
  });

  it("rejects a path that escapes the ingest directory", async () => {
    await assert.rejects(() => executeTool("read_file", { path: "../../etc/passwd" }), /escapes/);
  });
});

describe("executeTool — list_files", () => {
  it("lists files and marks directories", async () => {
    const listing = await executeTool("list_files", {});
    assert.match(listing, /notes\.txt/);
    assert.match(listing, /sub\//);
  });

  it("lists a subdirectory", async () => {
    const listing = await executeTool("list_files", { dir: "sub" });
    assert.match(listing, /nested\.txt/);
  });
});

describe("executeTool — grep", () => {
  it("finds a matching line with file name and line number", async () => {
    const result = await executeTool("grep", { pattern: "proof-of-work" });
    assert.match(result, /notes\.txt:2:/);
  });

  it("is case-insensitive", async () => {
    const result = await executeTool("grep", { pattern: "BITCOIN" });
    assert.match(result, /notes\.txt/);
  });

  it("returns a no-match message when nothing matches", async () => {
    const result = await executeTool("grep", { pattern: "nonexistent-pattern-xyz" });
    assert.equal(result, "No matches.");
  });
});

describe("executeTool — unknown tool", () => {
  it("rejects an unregistered tool name", async () => {
    await assert.rejects(() => executeTool("delete_everything", {}), /Unknown tool/);
  });
});
