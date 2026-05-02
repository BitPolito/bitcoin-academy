import { createServer } from "http";
import { initModels, shutdownModels } from "./models.js";
import { ingestFromJsonl } from "./ingest.js";
import { queryRag } from "./query.js";

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

    // POST /query  { question: string, workspace: string, topK?: number }
    // Returns { answer: string, sources: [{ score, snippet }] }.
    if (req.method === "POST" && req.url === "/query") {
      const { question, workspace, topK = 5 } = await readBody(req);
      const result = await queryRag(question, workspace, topK);
      return send(res, 200, result);
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
