// K071 实验用静态服务：只绑本机，只发站点文件和一份登记过的合成库，并接收探针上报。
import { createHash } from "node:crypto";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { dirname, extname, join, normalize, sep } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const SITE = join(HERE, "site");
export const RESULTS = join(HERE, "results");
const FIXTURES = join(HERE, "..", "fixtures", "kdbx");
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8" };

// 探针和被测代码都要在 ADR-0007 要求的严格 CSP 下工作，否则结论带不到生产。
function csp(connectSources) {
  return [
    "default-src 'none'",
    "script-src 'self'",
    "style-src 'self'",
    `connect-src 'self' ${connectSources.join(" ")}`.trim(),
    "worker-src 'self'",
    "frame-src 'self'",
    "frame-ancestors 'self'",
    "base-uri 'none'",
    "form-action 'none'",
  ].join("; ");
}

async function fixture() {
  const manifest = JSON.parse(await readFile(join(FIXTURES, "manifest.json"), "utf8"));
  const sample = manifest.samples.find((s) => s.id === "G41-RICH");
  const data = await readFile(join(FIXTURES, sample.file));
  if (createHash("sha256").update(data).digest("hex") !== sample.sha256) {
    throw new Error("registered G41-RICH changed");
  }
  return data;
}

async function readBody(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  return Buffer.concat(chunks).toString("utf8");
}

/**
 * @param {{port?: number, onReport?: (report: object) => void, saveReports?: boolean,
 *   connectSources?: string[], routes?: Record<string, () => object>}} [options]
 * connectSources 和 routes 启动后还能改：测试服务器要等拿到本站地址才能启动。
 */
export async function startServer({ port = 0, onReport, saveReports = false, connectSources = [], routes = {} } = {}) {
  const kdbx = await fixture();
  const server = createServer(async (request, response) => {
    const headers = { "Content-Security-Policy": csp(connectSources), "Cache-Control": "no-store" };
    try {
      const url = new URL(request.url, "http://localhost");
      if (routes[url.pathname]) {
        response.writeHead(200, { ...headers, "Content-Type": "application/json" }).end(JSON.stringify(routes[url.pathname]()));
        return;
      }
      if (request.method === "POST" && url.pathname === "/report") {
        const report = JSON.parse(await readBody(request));
        if (saveReports) {
          await mkdir(RESULTS, { recursive: true });
          const label = String(report.label).replace(/[^\w.-]/g, "_");
          await writeFile(join(RESULTS, `${label}.json`), JSON.stringify(report, null, 2) + "\n");
        }
        onReport?.(report);
        response.writeHead(204, headers).end();
        return;
      }
      if (url.pathname === "/fixture.kdbx") {
        response.writeHead(200, { ...headers, "Content-Type": "application/octet-stream" }).end(kdbx);
        return;
      }
      const relative = normalize(url.pathname === "/" ? "index.html" : url.pathname.slice(1));
      if (relative.split(sep).includes("..") || !TYPES[extname(relative)]) {
        response.writeHead(404, headers).end();
        return;
      }
      const body = await readFile(join(SITE, relative));
      response.writeHead(200, { ...headers, "Content-Type": TYPES[extname(relative)] }).end(body);
    } catch (error) {
      response.writeHead(error.code === "ENOENT" ? 404 : 500, headers).end();
    }
  });
  await new Promise((resolve) => server.listen(port, "127.0.0.1", resolve));
  return { server, origin: `http://127.0.0.1:${server.address().port}` };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const { origin } = await startServer({
    port: Number(process.argv[2] ?? 0),
    saveReports: true,
    onReport: (report) => console.log("report", report.label, report.failed),
  });
  console.log(origin);
}
