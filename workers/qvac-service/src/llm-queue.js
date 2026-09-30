/**
 * FIFO lock that serialises every LLM call in the service.
 *
 * llama.cpp holds a single Qwen3-4B instance: concurrent completions degrade
 * to interleaved token generation (slower for everyone) or crash on some
 * backends. The course builder fires bursts of generation jobs, so every
 * /generate, /stream and /generate_json call must queue here.
 */

let tail = Promise.resolve();

/**
 * Acquires the lock. Resolves to a release function once every previously
 * queued caller has released. Always call release() (use try/finally).
 *
 * @returns {Promise<() => void>}
 */
export function acquireLlmLock() {
  let release;
  const turn = new Promise((resolve) => (release = resolve));
  const ready = tail;
  tail = tail.then(() => turn);
  return ready.then(() => release);
}

/**
 * Runs an async function while holding the lock.
 *
 * @template T
 * @param {() => Promise<T>} fn
 * @returns {Promise<T>}
 */
export async function withLlmLock(fn) {
  const release = await acquireLlmLock();
  try {
    return await fn();
  } finally {
    release();
  }
}

/**
 * Runs an async generator while holding the lock. The lock is held until the
 * generator is fully consumed (or the consumer breaks/throws), because tokens
 * keep flowing from the model for the whole iteration.
 *
 * @template T
 * @param {() => AsyncGenerator<T>} genFactory
 * @returns {AsyncGenerator<T>}
 */
export async function* withLlmLockGen(genFactory) {
  const release = await acquireLlmLock();
  try {
    yield* genFactory();
  } finally {
    release();
  }
}
