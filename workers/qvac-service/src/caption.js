import { writeFile, unlink } from "fs/promises";
import { randomUUID } from "crypto";
import path from "path";
import os from "os";
import { getVisionModelId } from "./models.js";
import { withLlmLock } from "./llm-queue.js";

const DEFAULT_PROMPT =
  "Describe this image in one or two concise sentences, focused on what a " +
  "student studying from these course materials needs to know. Do not " +
  "mention that it is a slide, a screenshot, or an image.";

export class CaptioningDisabledError extends Error {}

/**
 * Caption one image with the vision-language model (#325).
 *
 * The SDK's multimodal API only accepts attachments by filesystem path, so
 * the base64 payload is written to a temp file for the duration of the call.
 *
 * @param {string} imageBase64  raw image bytes, base64-encoded
 * @param {{ prompt?: string }} [opts]
 * @returns {{ caption: string }}
 */
export async function captionImage(imageBase64, opts = {}) {
  const modelId = getVisionModelId();
  if (!modelId) {
    throw new CaptioningDisabledError(
      "Vision captioning is disabled or the model failed to load (set QVAC_CAPTIONING_ENABLED=true).",
    );
  }

  const { completion } = await import("@qvac/sdk");
  const prompt = opts.prompt || DEFAULT_PROMPT;
  const tmpPath = path.join(os.tmpdir(), `qvac-caption-${randomUUID()}.png`);
  await writeFile(tmpPath, Buffer.from(imageBase64, "base64"));

  try {
    const history = [{ role: "user", content: prompt, attachments: [{ path: tmpPath }] }];
    // Serialised through the same queue as text generation: captioning and
    // chat completion never run concurrently on this single-GPU/CPU host.
    const rawCaption = await withLlmLock(async () => {
      const result = completion({ modelId, history, stream: false });
      return await result.text;
    });
    return { caption: (rawCaption || "").trim() };
  } finally {
    await unlink(tmpPath).catch(() => {});
  }
}
