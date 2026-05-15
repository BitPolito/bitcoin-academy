import { createServer } from "http";
import { initModels, shutdownModels } from "./models.js";
import { ingestFromJsonl } from "./ingest.js";
import { queryRag, retrieveChunks, generateFromContext, streamFromContext } from "./query.js";

const PORT = parseInt(process.env.QVAC_PORT ?? "3001", 10);

// Reads the full request body and parses it as JSON.
function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", (chunk) => (data += chunk));
    req.on("end", () => {
      try { resolve(JSON.parse(data)); }
      catch (e) { reject(new Error("Invalid JSON in request body")); }
    });
    req.on("error", reject);
  });
}

function send(res, status, body) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

const server = createServer(async (req, res) => {
  try {
    // POST /ingest  { jsonlPath: string, workspace: string, rebuild?: boolean }
    // Called by FastAPI after the Python ingestion pipeline writes a JSONL file.
    if (req.method === "POST" && req.url === "/ingest") {
      const { jsonlPath, workspace, rebuild = false } = await readBody(req);
      await ingestFromJsonl(jsonlPath, workspace, rebuild);
      return send(res, 200, { ok: true });
    }

    // POST /query  { question: string, workspace: string, topK?: number, topKGenerate?: number }
    // topK: chunks to retrieve (default 5); topKGenerate: chunks sent to LLM (default = topK).
    // Returns { answer: string, sources: [{ score, snippet, label, page, slide, section, doc_id }] }.
    if (req.method === "POST" && req.url === "/query") {
      const { question, workspace, topK = 5, topKGenerate } = await readBody(req);
      const result = await queryRag(question, workspace, topK, topKGenerate ?? topK);
      return send(res, 200, result);
    }

    // POST /retrieve  { question: string, workspace: string, topK?: number }
    // Dense retrieval only — returns raw chunks for Python-side hybrid search + reranking.
    // Returns { chunks: [{ id, chunk_id, content, score, label, page, slide, section, doc_id, parent_id }] }
    if (req.method === "POST" && req.url === "/retrieve") {
      const { question, workspace, topK = 20 } = await readBody(req);
      const result = await retrieveChunks(question, workspace, topK);
      return send(res, 200, result);
    }

    // POST /generate  { question: string, context: [{ label: string, text: string }], systemPrompt?: string }
    // LLM generation from pre-built parent context — no retrieval.
    // systemPrompt overrides the default; omit to use the BitPolito Academy default.
    // Returns { answer: string }
    if (req.method === "POST" && req.url === "/generate") {
      const { question, context = [], systemPrompt = null } = await readBody(req);
      const result = await generateFromContext(question, context, systemPrompt);
      return send(res, 200, result);
    }

    // POST /stream  { question: string, context: [{ label, text }], systemPrompt?: string }
    // Server-Sent Events stream — writes tokens as "data: <token>\n\n" until done.
    // Client should consume with EventSource or fetch + ReadableStream.
    if (req.method === "POST" && req.url === "/stream") {
      const { question, context = [], systemPrompt = null } = await readBody(req);
      res.writeHead(200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Transfer-Encoding": "chunked",
      });
      try {
        for await (const token of streamFromContext(question, context, systemPrompt)) {
          res.write(`data: ${JSON.stringify(token)}\n\n`);
        }
        res.write("data: [DONE]\n\n");
      } catch (err) {
        res.write(`data: ${JSON.stringify("[ERROR] " + err.message)}\n\n`);
      }
      return res.end();
    }

    // GET /health — used by FastAPI to detect whether the service is up.
    if (req.method === "GET" && req.url === "/health") {
      return send(res, 200, { status: "ok" });
    }

    send(res, 404, { error: "not found" });
  } catch (err) {
    console.error("[server] error:", err.message);
    send(res, 500, { error: err.message });
  }
});

// Give in-flight requests a chance to finish before killing models.
process.on("SIGTERM", async () => {
  console.log("[server] shutting down...");
  await shutdownModels();
  server.close(() => process.exit(0));
});

await initModels();

server.listen(PORT, () => {
  console.log(`[qvac-service] listening on http://localhost:${PORT}`);
});
