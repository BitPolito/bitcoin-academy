/**
 * Unit tests for src/caption.js (#325).
 *
 * @qvac/sdk and src/models.js are fully mocked — no model download or
 * filesystem write to a real model happens; the temp image file is real but
 * written under os.tmpdir() and always cleaned up.
 */
import { describe, it, beforeEach, mock } from "node:test";
import assert from "node:assert/strict";
import { existsSync } from "fs";

const mockCompletion = mock.fn(() => ({ text: Promise.resolve("A diagram of the Bitcoin UTXO model.") }));

await mock.module("@qvac/sdk", {
  namedExports: {
    completion: mockCompletion,
    loadModel: mock.fn(),
    unloadModel: mock.fn(),
    close: mock.fn(),
  },
});

let visionModelId = "vl-test-id";
await mock.module(import.meta.resolve("../src/models.js"), {
  namedExports: {
    getVisionModelId: () => visionModelId,
  },
});

const { captionImage, CaptioningDisabledError } = await import("../src/caption.js");

const TINY_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

describe("captionImage", () => {
  beforeEach(() => {
    mockCompletion.mock.resetCalls();
    visionModelId = "vl-test-id";
  });

  it("throws CaptioningDisabledError when no vision model is loaded", async () => {
    visionModelId = null;
    await assert.rejects(() => captionImage(TINY_PNG_BASE64), CaptioningDisabledError);
  });

  it("writes the image to a temp file and passes it as an attachment", async () => {
    await captionImage(TINY_PNG_BASE64);

    const call = mockCompletion.mock.calls[0].arguments[0];
    assert.equal(call.modelId, "vl-test-id");
    assert.equal(call.stream, false);
    const attachment = call.history[0].attachments[0];
    assert.ok(attachment.path.endsWith(".png"));
  });

  it("deletes the temp file after captioning", async () => {
    let capturedPath;
    mockCompletion.mock.mockImplementationOnce((args) => {
      capturedPath = args.history[0].attachments[0].path;
      return { text: Promise.resolve("caption") };
    });

    await captionImage(TINY_PNG_BASE64);

    assert.equal(existsSync(capturedPath), false);
  });

  it("deletes the temp file even when the completion call fails", async () => {
    let capturedPath;
    mockCompletion.mock.mockImplementationOnce((args) => {
      capturedPath = args.history[0].attachments[0].path;
      return { text: Promise.reject(new Error("model crashed")) };
    });

    await assert.rejects(() => captionImage(TINY_PNG_BASE64));
    assert.equal(existsSync(capturedPath), false);
  });

  it("trims the returned caption", async () => {
    mockCompletion.mock.mockImplementationOnce(() => ({ text: Promise.resolve("  a caption.  \n") }));

    const { caption } = await captionImage(TINY_PNG_BASE64);

    assert.equal(caption, "a caption.");
  });

  it("uses the default prompt when none is given", async () => {
    await captionImage(TINY_PNG_BASE64);

    const call = mockCompletion.mock.calls[0].arguments[0];
    assert.match(call.history[0].content, /describe this image/i);
  });

  it("uses a custom prompt when provided", async () => {
    await captionImage(TINY_PNG_BASE64, { prompt: "What formula is shown?" });

    const call = mockCompletion.mock.calls[0].arguments[0];
    assert.equal(call.history[0].content, "What formula is shown?");
  });
});
