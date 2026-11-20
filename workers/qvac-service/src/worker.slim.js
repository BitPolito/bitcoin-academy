/**
 * Lean Bare worker entrypoint for bitcoin-academy.
 * Registers ONLY LLM and Embeddings plugins so unused multimodal backends can be pruned.
 */
import { initializeWorker, ensureRPCSetup } from "@qvac/sdk/worker-lifecycle";
import { registerPlugins } from "@qvac/sdk/plugins";
import { getServerLogger } from "@qvac/sdk/logging";
import { llmPlugin } from "@qvac/sdk/llamacpp-completion/plugin";
import { embeddingsPlugin } from "@qvac/sdk/llamacpp-embedding/plugin";

const { hasRPCConfig } = initializeWorker();
const logger = getServerLogger();
logger.info("Hello from Lean Bare Worker (LLM + Embeddings)");

registerPlugins([llmPlugin, embeddingsPlugin]);

if (hasRPCConfig) {
  ensureRPCSetup();
} else {
  logger.info("Running in direct mode - RPC setup will be lazy");
}
