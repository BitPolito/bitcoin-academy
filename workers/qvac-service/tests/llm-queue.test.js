/**
 * Unit tests for src/llm-queue.js — FIFO serialisation of LLM calls.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { withLlmLock, withLlmLockGen } from "../src/llm-queue.js";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

describe("withLlmLock", () => {
  it("serialises concurrent calls in FIFO order", async () => {
    const events = [];
    const task = (name, ms) =>
      withLlmLock(async () => {
        events.push(`${name}:start`);
        await sleep(ms);
        events.push(`${name}:end`);
      });

    // a is slower but queued first — b must not start until a ends.
    await Promise.all([task("a", 30), task("b", 5)]);
    assert.deepEqual(events, ["a:start", "a:end", "b:start", "b:end"]);
  });

  it("releases the lock when the task throws", async () => {
    await assert.rejects(
      withLlmLock(async () => { throw new Error("boom"); }),
      /boom/,
    );
    // Lock must be free again.
    const result = await withLlmLock(async () => "ok");
    assert.equal(result, "ok");
  });

  it("returns the task's value", async () => {
    assert.equal(await withLlmLock(async () => 42), 42);
  });
});

describe("withLlmLockGen", () => {
  it("holds the lock until the generator is fully consumed", async () => {
    const events = [];

    async function* tokens() {
      events.push("gen:first");
      yield "t1";
      await sleep(20);
      events.push("gen:second");
      yield "t2";
    }

    const consume = (async () => {
      for await (const t of withLlmLockGen(tokens)) void t;
      events.push("gen:done");
    })();
    // Queued while the stream is still flowing.
    const blocked = withLlmLock(async () => events.push("lock:acquired"));

    await Promise.all([consume, blocked]);
    assert.deepEqual(events, ["gen:first", "gen:second", "gen:done", "lock:acquired"]);
  });

  it("releases the lock when the consumer breaks early", async () => {
    async function* tokens() {
      yield "t1";
      yield "t2";
    }
    for await (const t of withLlmLockGen(tokens)) {
      void t;
      break;
    }
    const result = await withLlmLock(async () => "free");
    assert.equal(result, "free");
  });
});
