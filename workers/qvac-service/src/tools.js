import { z } from "zod";
import { readFile, readdir } from "fs/promises";
import path from "path";

const INGEST_DIR = path.resolve(process.env.QVAC_INGEST_DIR ?? "/qvac_ingest");

/**
 * Opencode-inspired tool set (#326) — read_file / list_files / grep, scoped
 * to QVAC_INGEST_DIR, the only directory this service has any business
 * touching. Deliberately no write/edit/bash tool: handing an LLM-chosen
 * shell command or an arbitrary file write to an agent loop is a command
 * injection / RCE surface, and #326 only needs read-only lookup to prove the
 * tool-calling layer end-to-end.
 */

function resolveInsideIngestDir(relativePath) {
  const resolved = path.resolve(INGEST_DIR, relativePath || ".");
  if (resolved !== INGEST_DIR && !resolved.startsWith(INGEST_DIR + path.sep)) {
    throw new Error(`Path "${relativePath}" escapes the ingest directory.`);
  }
  return resolved;
}

async function readFileHandler({ path: relPath, maxChars = 4000 }) {
  const resolved = resolveInsideIngestDir(relPath);
  const content = await readFile(resolved, "utf-8");
  return content.length > maxChars ? content.slice(0, maxChars) + "\n…(truncated)" : content;
}

async function listFilesHandler({ dir = "." }) {
  const resolved = resolveInsideIngestDir(dir);
  const entries = await readdir(resolved, { withFileTypes: true });
  return entries.map((e) => (e.isDirectory() ? `${e.name}/` : e.name)).join("\n") || "(empty)";
}

async function grepHandler({ pattern, dir = "." }) {
  const resolved = resolveInsideIngestDir(dir);
  const regex = new RegExp(pattern, "i");
  const entries = await readdir(resolved, { withFileTypes: true });
  const matches = [];
  for (const entry of entries) {
    if (!entry.isFile() || matches.length >= 50) continue;
    const content = await readFile(path.join(resolved, entry.name), "utf-8").catch(() => "");
    content.split("\n").forEach((line, i) => {
      if (matches.length < 50 && regex.test(line)) {
        matches.push(`${entry.name}:${i + 1}: ${line.trim()}`);
      }
    });
  }
  return matches.join("\n") || "No matches.";
}

const TOOLS = [
  {
    name: "read_file",
    description: "Read a text file from the QVAC ingest directory.",
    parameters: z.object({
      path: z.string().describe("Path relative to the ingest directory"),
      maxChars: z.number().optional().describe("Max characters to return (default 4000)"),
    }),
    handler: readFileHandler,
  },
  {
    name: "list_files",
    description: "List files and subdirectories under a directory of the QVAC ingest directory.",
    parameters: z.object({
      dir: z.string().optional().describe("Directory relative to the ingest directory (default: root)"),
    }),
    handler: listFilesHandler,
  },
  {
    name: "grep",
    description: "Search for a regex pattern across files in a directory of the QVAC ingest directory.",
    parameters: z.object({
      pattern: z.string().describe("Regular expression to search for"),
      dir: z.string().optional().describe("Directory relative to the ingest directory (default: root)"),
    }),
    handler: grepHandler,
  },
];

/** Tool definitions in the shape @qvac/sdk's completion() expects: {name, description, parameters}. */
export function toolDefinitions() {
  return TOOLS.map(({ name, description, parameters }) => ({ name, description, parameters }));
}

export async function executeTool(name, args) {
  const tool = TOOLS.find((t) => t.name === name);
  if (!tool) throw new Error(`Unknown tool "${name}".`);
  return await tool.handler(args || {});
}
