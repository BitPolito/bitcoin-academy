/**
 * Unit tests for src/generate-json.js.
 *
 * @qvac/sdk and src/models.js are fully mocked — no model download happens.
 * The completion mock returns scripted outputs so the extraction, validation
 * and correction-retry paths can be exercised deterministically.
 */
import { describe, it, beforeEach, mock } from "node:test";
import assert from "node:assert/strict";

// ---------------------------------------------------------------------------
// SDK + models.js mocks — registered before generate-json.js is imported
// ---------------------------------------------------------------------------

let completionOutputs = [];
let completionCalls = [];

const mockCompletion = mock.fn((params) => {
  completionCalls.push(structuredClone(params.history));
  const next = completionOutputs.shift() ?? "";
  return { text: Promise.resolve(next) };
});

await mock.module("@qvac/sdk", {
  namedExports: {
    completion: mockCompletion,
    ragSearch: mock.fn(),
    ragIngest: mock.fn(),
    loadModel: mock.fn(),
    unloadModel: mock.fn(),
    close: mock.fn(),
    GTE_LARGE_FP16: {},
    QWEN3_4B_INST_Q4_K_M: {},
  },
});

let llmId = "test-llm-id";
await mock.module(import.meta.resolve("../src/models.js"), {
  namedExports: {
    getEmbeddingModelId: () => "test-emb-id",
    getLlmModelId: () => llmId,
    getLlmCtxSize: () => 8192,
    initModels: mock.fn(),
    shutdownModels: mock.fn(),
  },
});

const { generateJson, extractJson, validateSchema, LlmDisabledError, JsonGenerationError } =
  await import("../src/generate-json.js");

beforeEach(() => {
  completionOutputs = [];
  completionCalls = [];
  llmId = "test-llm-id";
});

// ---------------------------------------------------------------------------
// extractJson
// ---------------------------------------------------------------------------

describe("extractJson", () => {
  it("parses bare JSON objects and arrays", () => {
    assert.deepEqual(extractJson('{"a": 1}'), { a: 1 });
    assert.deepEqual(extractJson("[1, 2]"), [1, 2]);
  });

  it("unwraps markdown fences", () => {
    assert.deepEqual(extractJson('```json\n{"a": 1}\n```'), { a: 1 });
  });

  it("strips <think> blocks", () => {
    assert.deepEqual(
      extractJson('<think>{"draft": true}</think>{"a": 1}'),
      { a: 1 },
    );
  });

  it("ignores prose around the JSON value", () => {
    assert.deepEqual(extractJson('Here you go: {"a": 1} hope it helps'), { a: 1 });
  });

  it("handles brackets inside strings", () => {
    assert.deepEqual(extractJson('{"a": "with } brace and \\" quote"}'), {
      a: 'with } brace and " quote',
    });
  });

  it("throws on truncated JSON", () => {
    assert.throws(() => extractJson('{"a": [1, 2'), /truncated/);
  });

  it("throws when no JSON is present", () => {
    assert.throws(() => extractJson("no json here"), /no JSON/);
  });
});

// ---------------------------------------------------------------------------
// validateSchema
// ---------------------------------------------------------------------------

describe("validateSchema", () => {
  const schema = {
    type: "object",
    required: ["title", "lessons"],
    properties: {
      title: { type: "string" },
      difficulty: { enum: ["easy", "medium", "hard"] },
      lessons: {
        type: "array",
        minItems: 1,
        items: {
          type: "object",
          required: ["title"],
          properties: { title: { type: "string" }, page: { type: "integer" } },
        },
      },
    },
  };

  it("accepts a conforming value", () => {
    const value = { title: "Ch. 1", difficulty: "easy", lessons: [{ title: "L1", page: 3 }] };
    assert.deepEqual(validateSchema(value, schema), []);
  });

  it("reports missing required properties with their path", () => {
    const errors = validateSchema({ title: "x", lessons: [{}] }, schema);
    assert.equal(errors.length, 1);
    assert.match(errors[0], /\$\.lessons\[0\]\.title: required/);
  });

  it("reports type mismatches", () => {
    const errors = validateSchema({ title: 5, lessons: [] }, schema);
    assert.ok(errors.some((e) => e.includes("$.title: expected string, got integer")));
    assert.ok(errors.some((e) => e.includes("at least 1 items")));
  });

  it("reports enum violations", () => {
    const errors = validateSchema(
      { title: "x", difficulty: "extreme", lessons: [{ title: "y" }] },
      schema,
    );
    assert.equal(errors.length, 1);
    assert.match(errors[0], /not in enum/);
  });

  it("accepts integers where numbers are expected", () => {
    assert.deepEqual(validateSchema(3, { type: "number" }), []);
  });

  it("rejects additional properties when additionalProperties is false", () => {
    const errors = validateSchema(
      { a: 1, extra: true },
      { type: "object", properties: { a: { type: "integer" } }, additionalProperties: false },
    );
    assert.equal(errors.length, 1);
    assert.match(errors[0], /\$\.extra: additional property/);
  });
});

// ---------------------------------------------------------------------------
// generateJson
// ---------------------------------------------------------------------------

const SIMPLE_SCHEMA = {
  type: "object",
  required: ["answer"],
  properties: { answer: { type: "string" } },
};

describe("generateJson", () => {
  it("returns parsed JSON on the first valid attempt", async () => {
    completionOutputs = ['{"answer": "ok"}'];
    const { json, attempts } = await generateJson({
      prompt: "say ok",
      schema: SIMPLE_SCHEMA,
    });
    assert.deepEqual(json, { answer: "ok" });
    assert.equal(attempts, 1);
    assert.equal(completionCalls.length, 1);
  });

  it("embeds the schema in the system prompt and context in the user turn", async () => {
    completionOutputs = ['{"answer": "ok"}'];
    await generateJson({
      prompt: "summarise",
      schema: SIMPLE_SCHEMA,
      context: [{ label: "p. 7", text: "Bitcoin is..." }],
      systemPrompt: "You are a tutor.",
    });
    const [history] = completionCalls;
    assert.match(history[0].content, /You are a tutor\./);
    assert.match(history[0].content, /"required":\["answer"\]/);
    assert.match(history[1].content, /\[p\. 7\]\nBitcoin is\.\.\./);
    assert.match(history[1].content, /\/nothink/);
  });

  it("retries with validation feedback and succeeds", async () => {
    completionOutputs = ["not json at all", '{"answer": 42}', '{"answer": "fixed"}'];
    const { json, attempts } = await generateJson({
      prompt: "x",
      schema: SIMPLE_SCHEMA,
      maxRetries: 2,
    });
    assert.deepEqual(json, { answer: "fixed" });
    assert.equal(attempts, 3);
    // Third call's history must carry both correction turns.
    const lastHistory = completionCalls[2];
    assert.equal(lastHistory.length, 6); // system, user, asst, user, asst, user
    assert.match(lastHistory[3].content, /invalid JSON/);
    assert.match(lastHistory[5].content, /expected string, got integer/);
  });

  it("throws JsonGenerationError with details after exhausting retries", async () => {
    completionOutputs = ['{"wrong": 1}', '{"wrong": 2}'];
    await assert.rejects(
      generateJson({ prompt: "x", schema: SIMPLE_SCHEMA, maxRetries: 1 }),
      (err) => {
        assert.ok(err instanceof JsonGenerationError);
        assert.equal(err.attempts, 2);
        assert.ok(err.errors.some((e) => e.includes("required property missing")));
        assert.equal(err.raw, '{"wrong": 2}');
        return true;
      },
    );
  });

  it("throws LlmDisabledError when no LLM is loaded", async () => {
    llmId = null;
    await assert.rejects(
      generateJson({ prompt: "x", schema: SIMPLE_SCHEMA }),
      LlmDisabledError,
    );
  });

  it("rejects a missing schema", async () => {
    await assert.rejects(
      generateJson({ prompt: "x" }),
      /schema object is required/,
    );
  });
});
