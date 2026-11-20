/**
 * Unit tests for src/tool-calling.js (#326).
 *
 * @qvac/sdk, src/models.js and src/tools.js are fully mocked — no model
 * download or real file access happens.
 */
import { describe, it, beforeEach, mock } from "node:test";
import assert from "node:assert/strict";

const mockCompletion = mock.fn();
await mock.module("@qvac/sdk", {
  namedExports: {
    completion: mockCompletion,
    loadModel: mock.fn(),
    unloadModel: mock.fn(),
    close: mock.fn(),
  },
});

let toolModelId = "tool-test-id";
await mock.module(import.meta.resolve("../src/models.js"), {
  namedExports: {
    getToolCallingModelId: () => toolModelId,
  },
});

const mockExecuteTool = mock.fn(async (name) => `result of ${name}`);
await mock.module(import.meta.resolve("../src/tools.js"), {
  namedExports: {
    toolDefinitions: () => [{ name: "read_file", description: "...", parameters: {} }],
    executeTool: mockExecuteTool,
  },
});

const { runWithTools, ToolCallingDisabledError } = await import("../src/tool-calling.js");

function textResult(text) {
  return { text: Promise.resolve(text), toolCalls: Promise.resolve([]) };
}

describe("runWithTools", () => {
  beforeEach(() => {
    mockCompletion.mock.resetCalls();
    mockExecuteTool.mock.resetCalls();
    toolModelId = "tool-test-id";
  });

  it("throws ToolCallingDisabledError when no tool-calling model is loaded", async () => {
    toolModelId = null;
    await assert.rejects(() => runWithTools("hello"), ToolCallingDisabledError);
  });

  it("returns the answer directly when the model calls no tools", async () => {
    mockCompletion.mock.mockImplementationOnce(() => textResult("42 is the answer."));

    const { answer, toolCalls } = await runWithTools("What is the answer?");

    assert.equal(answer, "42 is the answer.");
    assert.deepEqual(toolCalls, []);
    assert.equal(mockCompletion.mock.calls.length, 1);
  });

  it("passes tools and history to completion", async () => {
    mockCompletion.mock.mockImplementationOnce(() => textResult("ok"));

    await runWithTools("hi", "You are helpful.");

    const call = mockCompletion.mock.calls[0].arguments[0];
    assert.equal(call.modelId, "tool-test-id");
    assert.equal(call.stream, false);
    assert.deepEqual(call.tools, [{ name: "read_file", description: "...", parameters: {} }]);
    assert.equal(call.history[0].role, "system");
    assert.equal(call.history[1].content, "hi");
  });

  it("executes a tool call, appends the result, and asks again", async () => {
    mockCompletion.mock.mockImplementationOnce(
      () => ({
        text: Promise.resolve(""),
        toolCalls: Promise.resolve([{ id: "1", name: "read_file", arguments: { path: "a.txt" } }]),
      }),
      0,
    );
    mockCompletion.mock.mockImplementationOnce(() => textResult("Based on a.txt, the answer is 7."), 1);

    const { answer, toolCalls } = await runWithTools("read a.txt and tell me the answer");

    assert.equal(mockCompletion.mock.calls.length, 2);
    assert.equal(mockExecuteTool.mock.calls.length, 1);
    assert.deepEqual(mockExecuteTool.mock.calls[0].arguments, ["read_file", { path: "a.txt" }]);
    assert.equal(answer, "Based on a.txt, the answer is 7.");
    assert.deepEqual(toolCalls, [
      { name: "read_file", arguments: { path: "a.txt" }, result: "result of read_file" },
    ]);

    const secondCallHistory = mockCompletion.mock.calls[1].arguments[0].history;
    assert.ok(secondCallHistory.some((m) => m.role === "tool" && m.content === "result of read_file"));
  });

  it("logs the tool call even when execution throws", async () => {
    mockExecuteTool.mock.mockImplementationOnce(async () => {
      throw new Error("file not found");
    });
    mockCompletion.mock.mockImplementationOnce(
      () => ({
        text: Promise.resolve(""),
        toolCalls: Promise.resolve([{ id: "1", name: "read_file", arguments: { path: "missing.txt" } }]),
      }),
      0,
    );
    mockCompletion.mock.mockImplementationOnce(() => textResult("I could not read that file."), 1);

    const { toolCalls } = await runWithTools("read missing.txt");

    assert.equal(toolCalls[0].result, "Error: file not found");
  });

  it("stops calling tools after QVAC_TOOL_CALL_MAX_ROUNDS and forces a final answer", async () => {
    const infiniteToolCall = () => ({
      text: Promise.resolve(""),
      toolCalls: Promise.resolve([{ id: "1", name: "read_file", arguments: {} }]),
    });
    mockCompletion.mock.mockImplementationOnce(infiniteToolCall, 0);
    mockCompletion.mock.mockImplementationOnce(infiniteToolCall, 1);
    mockCompletion.mock.mockImplementationOnce(() => textResult("Final answer without tools."), 2);

    const { answer } = await runWithTools("loop forever");

    assert.equal(answer, "Final answer without tools.");
    assert.equal(mockCompletion.mock.calls.length, 3);
    // The forced final call must not offer tools again.
    assert.equal(mockCompletion.mock.calls[2].arguments[0].tools, undefined);
  });
});
