/**
 * Schema-validated JSON generation on the local LLM.
 *
 * @qvac/sdk 0.9.x exposes no GBNF grammar or response_format, so validity is
 * enforced service-side: low-temperature prompting, robust JSON extraction
 * (code fences, <think> blocks, surrounding prose), validation against a
 * JSON-Schema subset, and bounded retries that feed the validation errors
 * back to the model. Callers (course builder outline/lesson jobs) get either
 * a schema-conformant object or a typed error — never a string to regex.
 *
 * Supported schema subset (mirrors the SDK's JsonSchema type): type, enum,
 * properties, required, additionalProperties, items, plus minItems/maxItems.
 */
import { getLlmModelId } from "./models.js";
import { withLlmLock } from "./llm-queue.js";

const MAX_RETRIES_DEFAULT = parseInt(process.env.QVAC_JSON_MAX_RETRIES ?? "2", 10);

export class LlmDisabledError extends Error {
  constructor() {
    super("LLM generation is disabled (QVAC_LLM_ENABLED=false)");
    this.name = "LlmDisabledError";
  }
}

export class JsonGenerationError extends Error {
  /**
   * @param {string} message
   * @param {{ raw?: string, errors?: string[], attempts?: number }} [details]
   */
  constructor(message, details = {}) {
    super(message);
    this.name = "JsonGenerationError";
    this.raw = details.raw ?? "";
    this.errors = details.errors ?? [];
    this.attempts = details.attempts ?? 0;
  }
}

// ---------------------------------------------------------------------------
// JSON extraction
// ---------------------------------------------------------------------------

/**
 * Pulls the first complete JSON object or array out of raw model output.
 * Tolerates <think> blocks, ```json fences and prose before/after the value.
 *
 * @param {string} text
 * @returns {unknown} the parsed value
 * @throws {Error} when no parseable JSON is found
 */
export function extractJson(text) {
  let s = (text ?? "").replace(/<think>[\s\S]*?<\/think>/gi, "").trim();
  // Unwrap a markdown fence if the model added one despite instructions.
  const fence = s.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fence) s = fence[1].trim();

  const start = s.search(/[{[]/);
  if (start === -1) throw new Error("no JSON object or array found in output");

  // Scan for the matching close bracket, honouring strings and escapes.
  const open = s[start];
  const close = open === "{" ? "}" : "]";
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let i = start; i < s.length; i++) {
    const ch = s[i];
    if (escaped) { escaped = false; continue; }
    if (ch === "\\") { escaped = true; continue; }
    if (ch === '"') { inString = !inString; continue; }
    if (inString) continue;
    if (ch === open) depth++;
    else if (ch === close) {
      depth--;
      if (depth === 0) return JSON.parse(s.slice(start, i + 1));
    }
  }
  throw new Error("JSON value is truncated (unbalanced brackets)");
}

// ---------------------------------------------------------------------------
// Schema validation
// ---------------------------------------------------------------------------

function typeOf(value) {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  if (typeof value === "number") return Number.isInteger(value) ? "integer" : "number";
  return typeof value; // string | boolean | object
}

function typeMatches(actual, expected) {
  if (expected === "number") return actual === "number" || actual === "integer";
  return actual === expected;
}

/**
 * Validates a value against the supported JSON-Schema subset.
 *
 * @param {unknown} value
 * @param {object} schema
 * @param {string} [path]
 * @returns {string[]} human-readable errors, empty when valid
 */
export function validateSchema(value, schema, path = "$") {
  const errors = [];
  if (!schema || typeof schema !== "object") return errors;

  if (schema.enum) {
    if (!schema.enum.includes(value)) {
      errors.push(`${path}: value ${JSON.stringify(value)} not in enum [${schema.enum.map((v) => JSON.stringify(v)).join(", ")}]`);
    }
    return errors;
  }

  if (schema.type) {
    const expected = Array.isArray(schema.type) ? schema.type : [schema.type];
    const actual = typeOf(value);
    if (!expected.some((t) => typeMatches(actual, t))) {
      errors.push(`${path}: expected ${expected.join("|")}, got ${actual}`);
      return errors; // nested checks are meaningless on the wrong type
    }
  }

  if (typeOf(value) === "object" && (schema.properties || schema.required)) {
    for (const key of schema.required ?? []) {
      if (!(key in value)) errors.push(`${path}.${key}: required property missing`);
    }
    for (const [key, propSchema] of Object.entries(schema.properties ?? {})) {
      if (key in value) errors.push(...validateSchema(value[key], propSchema, `${path}.${key}`));
    }
    if (schema.additionalProperties === false) {
      for (const key of Object.keys(value)) {
        if (!(key in (schema.properties ?? {}))) {
          errors.push(`${path}.${key}: additional property not allowed`);
        }
      }
    }
  }

  if (Array.isArray(value)) {
    if (schema.minItems !== undefined && value.length < schema.minItems) {
      errors.push(`${path}: expected at least ${schema.minItems} items, got ${value.length}`);
    }
    if (schema.maxItems !== undefined && value.length > schema.maxItems) {
      errors.push(`${path}: expected at most ${schema.maxItems} items, got ${value.length}`);
    }
    if (schema.items) {
      value.forEach((item, i) => errors.push(...validateSchema(item, schema.items, `${path}[${i}]`)));
    }
  }

  return errors;
}

// ---------------------------------------------------------------------------
// Generation
// ---------------------------------------------------------------------------

function buildSystemPrompt(schema, callerPrompt) {
  const base = callerPrompt ? `${callerPrompt.trim()}\n\n` : "";
  return (
    base +
    "OUTPUT FORMAT — non-negotiable:\n" +
    "Respond with ONE valid JSON value conforming exactly to this JSON Schema:\n" +
    JSON.stringify(schema) +
    "\nRules: output raw JSON only — no markdown fences, no comments, no prose" +
    " before or after, no trailing commas. Use double quotes for all strings."
  );
}

function buildContextBlock(contextBlocks) {
  if (!contextBlocks?.length) return "";
  const ctx = contextBlocks
    .map((b, i) => `[${i + 1}]${b.label ? ` [${b.label}]` : ""}\n${b.text}`)
    .join("\n\n---\n\n");
  return `Context:\n${ctx}\n\n`;
}

/**
 * Generates a JSON value that validates against *schema*.
 *
 * @param {object} params
 * @param {string} params.prompt          task instruction for the model
 * @param {{ label?: string, text: string }[]} [params.context]  grounding passages
 * @param {object} params.schema          JSON Schema (supported subset)
 * @param {string|null} [params.systemPrompt]  domain instructions, prepended to the format contract
 * @param {number} [params.maxRetries]    correction rounds after the first attempt
 * @param {object} [params.generationParams]  llama.cpp sampling overrides
 * @returns {Promise<{ json: unknown, attempts: number }>}
 * @throws {LlmDisabledError | JsonGenerationError}
 */
export async function generateJson({
  prompt,
  context = [],
  schema,
  systemPrompt = null,
  maxRetries = MAX_RETRIES_DEFAULT,
  generationParams = {},
}) {
  const llmId = getLlmModelId();
  if (!llmId) throw new LlmDisabledError();
  if (!schema || typeof schema !== "object") {
    throw new JsonGenerationError("a JSON schema object is required");
  }

  const { completion } = await import("@qvac/sdk");

  const history = [
    { role: "system", content: buildSystemPrompt(schema, systemPrompt) },
    { role: "user", content: `${buildContextBlock(context)}Task: ${prompt} /nothink` },
  ];
  // Low temperature favours format compliance; callers may override.
  const params = { temp: 0.1, ...generationParams };

  let lastRaw = "";
  let lastErrors = [];
  const attemptsTotal = 1 + Math.max(0, maxRetries);

  for (let attempt = 1; attempt <= attemptsTotal; attempt++) {
    const raw = await withLlmLock(async () => {
      const result = completion({ modelId: llmId, history, stream: false, generationParams: params });
      return await result.text;
    });
    lastRaw = raw ?? "";

    let value;
    try {
      value = extractJson(lastRaw);
    } catch (err) {
      lastErrors = [`invalid JSON: ${err.message}`];
      pushCorrectionTurn(history, lastRaw, lastErrors);
      continue;
    }

    lastErrors = validateSchema(value, schema);
    if (lastErrors.length === 0) return { json: value, attempts: attempt };
    pushCorrectionTurn(history, lastRaw, lastErrors);
  }

  throw new JsonGenerationError(
    `model output failed schema validation after ${attemptsTotal} attempts`,
    { raw: lastRaw, errors: lastErrors, attempts: attemptsTotal },
  );
}

function pushCorrectionTurn(history, badOutput, errors) {
  history.push({ role: "assistant", content: badOutput.slice(0, 2000) });
  history.push({
    role: "user",
    content:
      "Your previous answer was rejected:\n" +
      errors.slice(0, 10).map((e) => `- ${e}`).join("\n") +
      "\nReply again with ONLY the corrected JSON. /nothink",
  });
}
