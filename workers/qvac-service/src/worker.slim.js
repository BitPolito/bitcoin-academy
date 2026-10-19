/**
 * Lean Bare worker entrypoint for bitcoin-academy.
 * Registers ONLY LLM and Embeddings plugins so unused multimodal backends can be pruned.
 */
import { initializeWorkerCore, ensureRPCSetup } from "@qvac/sdk/worker-core";
import { registerPlugin } from "@qvac/sdk/plugins";
import { getServerLogger } from "@qvac/sdk/logging";
import { llmPlugin } from "@qvac/sdk/llamacpp-completion/plugin";
import { embeddingsPlugin } from "@qvac/sdk/llamacpp-embedding/plugin";

const { hasRPCConfig } = initializeWorkerCore();
const logger = getServerLogger();
logger.info("Hello from Lean Bare Worker (LLM + Embeddings)");

registerPlugin(llmPlugin);
registerPlugin(embeddingsPlugin);

if (hasRPCConfig) {
  ensureRPCSetup();
} else {
  logger.info("Running in direct mode - RPC setup will be lazy");
}
