import { getToolCallingModelId } from "./models.js";
import { withLlmLock } from "./llm-queue.js";
import { toolDefinitions, executeTool } from "./tools.js";

export class ToolCallingDisabledError extends Error {}

// Bounds the call → execute → re-prompt loop so a model that keeps calling
// tools forever can't turn one request into an unbounded number of
// completions. After this many rounds the model is asked once more without
// tools, forcing a final answer from whatever it has gathered so far.
const MAX_TOOL_ROUNDS = parseInt(process.env.QVAC_TOOL_CALL_MAX_ROUNDS ?? "2", 10);

/**
 * Runs the opencode-inspired tool-calling agent loop (#326): the model may
 * call read_file / list_files / grep (see tools.js) before answering.
 *
 * @param {string} question
 * @param {string|null} [systemPrompt]
 * @returns {{ answer: string, toolCalls: { name: string, arguments: object, result: string }[] }}
 */
export async function runWithTools(question, systemPrompt = null) {
  const modelId = getToolCallingModelId();
  if (!modelId) {
    throw new ToolCallingDisabledError(
      "Tool-calling is disabled or the model failed to load (set QVAC_TOOL_CALLING_ENABLED=true).",
    );
  }

  const { completion } = await import("@qvac/sdk");
  const tools = toolDefinitions();
  const history = [];
  if (systemPrompt) history.push({ role: "system", content: systemPrompt });
  history.push({ role: "user", content: question });

  const toolCallsLog = [];

  for (let round = 0; round < MAX_TOOL_ROUNDS; round++) {
    const { answer, toolCalls } = await withLlmLock(async () => {
      const result = completion({ modelId, history, stream: false, tools });
      const [text, calls] = await Promise.all([result.text, result.toolCalls]);
      return { answer: text, toolCalls: calls };
    });

    if (!toolCalls || toolCalls.length === 0) {
      return { answer: (answer || "").trim(), toolCalls: toolCallsLog };
    }

    history.push({ role: "assistant", content: answer || "" });
    for (const call of toolCalls) {
      let result;
      try {
        result = await executeTool(call.name, call.arguments);
      } catch (err) {
        result = `Error: ${err.message}`;
      }
      toolCallsLog.push({ name: call.name, arguments: call.arguments, result });
      history.push({ role: "tool", content: String(result) });
    }
  }

  const finalAnswer = await withLlmLock(async () => {
    const result = completion({ modelId, history, stream: false });
    return await result.text;
  });
  return { answer: (finalAnswer || "").trim(), toolCalls: toolCallsLog };
}
