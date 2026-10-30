// K072 测试服务器：两种真实 WebDAV 实现，加一个故意出错的脚本服务器。只绑本机，只放合成数据。
import { execFileSync, spawn } from "node:child_process";
import { createHash, randomBytes } from "node:crypto";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { connect } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
export const USER = "synthetic-user";
// 每次运行随机生成：只给本机回环地址上的测试服务器用，运行结束就没了。
export const PASSWORD = randomBytes(18).toString("hex");
const WSGIDAV_PYTHON = join(HERE, ".wsgidav", "bin", "python");
const ALLOW_HEADERS = "Authorization, Content-Type, Depth, Destination, If, If-Match, If-None-Match, Overwrite";
const ALLOW_METHODS = "GET, HEAD, PUT, DELETE, OPTIONS, PROPFIND, MOVE";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitForPort(url) {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      await fetch(url, { method: "OPTIONS", signal: AbortSignal.timeout(500) });
      return;
    } catch {
      await sleep(250);
    }
  }
  throw new Error(`server did not start: ${url}`);
}

function freePort() {
  return new Promise((resolve) => {
    const probe = createServer();
    probe.listen(0, "127.0.0.1", () => {
      const { port } = probe.address();
      probe.close(() => resolve(port));
    });
  });
}

/** 服务器要放在自己的进程组：Apache 停止时会向整个进程组发 SIGTERM，同组的话连驱动一起杀掉，还不留任何报错。 */
function spawnGroup(command, args) {
  return spawn(command, args, { stdio: "ignore", detached: true });
}

function started(child, cleanup) {
  return async () => {
    try {
      process.kill(-child.pid, "SIGTERM");
      await sleep(200);
      process.kill(-child.pid, "SIGKILL");
    } catch (error) {
      if (error.code !== "ESRCH") throw error;
    }
    await rm(cleanup, { recursive: true, force: true });
  };
}

/** macOS 自带的 Apache mod_dav。预检不要求认证，这是 CORS 规定的，别的方法都要。 */
export async function startApache(allowedOrigin) {
  const root = await mkdtemp(join(tmpdir(), "keex-k072-apache-"));
  const data = join(root, "data");
  await mkdir(data);
  const port = await freePort();
  const modules = ["mpm_prefork", "unixd", "authn_core", "authn_file", "authz_core", "authz_user", "auth_basic", "dav", "dav_fs", "headers", "rewrite", "log_config"];
  execFileSync("/usr/sbin/htpasswd", ["-cbB", join(root, "users"), USER, PASSWORD], { stdio: "ignore" });
  await writeFile(join(root, "httpd.conf"), `
ServerRoot "/usr"
ServerName 127.0.0.1
Listen 127.0.0.1:${port}
PidFile "${root}/httpd.pid"
ErrorLog "${root}/error.log"
${modules.map((m) => `LoadModule ${m}_module libexec/apache2/mod_${m}.so`).join("\n")}
DavLockDB "${root}/lockdb"
DocumentRoot "${data}"
Header always set Access-Control-Allow-Origin "${allowedOrigin}"
Header always set Access-Control-Allow-Methods "${ALLOW_METHODS}"
Header always set Access-Control-Allow-Headers "${ALLOW_HEADERS}"
Header always set Access-Control-Expose-Headers "ETag"
Header always set Vary "Origin"
<Directory "${data}">
  Dav On
  AuthType Basic
  AuthName "keex-synthetic"
  AuthUserFile "${root}/users"
  <LimitExcept OPTIONS>
    Require valid-user
  </LimitExcept>
  RewriteEngine On
  RewriteCond %{REQUEST_METHOD} OPTIONS
  RewriteCond %{HTTP:Access-Control-Request-Method} !^$
  RewriteRule .* - [R=204,L]
</Directory>
`);
  const child = spawnGroup("/usr/sbin/httpd", ["-f", join(root, "httpd.conf"), "-DFOREGROUND"]);
  const url = `http://127.0.0.1:${port}`;
  await waitForPort(url);
  return { url, stop: started(child, root) };
}

export async function startWsgiDav(allowedOrigin) {
  const root = await mkdtemp(join(tmpdir(), "keex-k072-wsgidav-"));
  const data = join(root, "data");
  await mkdir(data);
  const port = await freePort();
  await writeFile(join(root, "wsgidav.json"), JSON.stringify({
    host: "127.0.0.1",
    port,
    server: "cheroot",
    provider_mapping: { "/": data },
    logging: { enable: false },
    verbose: 0,
    http_authenticator: { domain_controller: null, accept_basic: true, accept_digest: false, default_to_digest: false },
    simple_dc: { user_mapping: { "*": { [USER]: { password: PASSWORD } } } },
    cors: {
      allow_origin: allowedOrigin,
      allow_methods: ALLOW_METHODS.split(", "),
      allow_headers: ALLOW_HEADERS.split(", "),
      // 4.3.5 的 expose_headers 只进预检响应，实际响应没有，浏览器读不到 ETag（规范要求相反）。
      // 用 add_always 绕开；部署方照文档配 expose_headers 会得到“连得上但不能写”。
      add_always: { "Access-Control-Expose-Headers": "ETag" },
      allow_max_age: 60,
    },
  }));
  const child = spawnGroup(WSGIDAV_PYTHON, ["-m", "wsgidav.server.server_cli", "--config", join(root, "wsgidav.json")]);
  const url = `http://127.0.0.1:${port}`;
  await waitForPort(url);
  return { url, stop: started(child, root) };
}

/**
 * 脚本服务器：正常时严格遵守条件语义，再按 mode 故意出错一种。
 * 这里测的是客户端遇到坏服务器时会不会犯错，所以不追求实现完整的 WebDAV。
 */
export async function startScripted(allowedOrigin, mode) {
  const files = new Map();
  const leaks = [];
  // 跨源跳转的目标：记下它收到的头，用来证明认证头没有漏过去。
  const elsewhere = createServer((request, response) => {
    leaks.push({ method: request.method, authorization: request.headers.authorization ?? null });
    response.writeHead(200, { "Access-Control-Allow-Origin": "*" }).end("elsewhere");
  });
  await new Promise((resolve) => elsewhere.listen(0, "127.0.0.1", resolve));
  const elsewhereUrl = `http://127.0.0.1:${elsewhere.address().port}/`;

  const corsHeaders = () => {
    if (mode === "no-cors") return {};
    if (mode === "wildcard") {
      return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": ALLOW_METHODS,
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Expose-Headers": "*",
      };
    }
    return {
      "Access-Control-Allow-Origin": allowedOrigin,
      "Access-Control-Allow-Methods": ALLOW_METHODS,
      "Access-Control-Allow-Headers": ALLOW_HEADERS,
      ...(mode === "no-expose" ? {} : { "Access-Control-Expose-Headers": "ETag" }),
      Vary: "Origin",
    };
  };
  const etagOf = (file) => {
    if (mode === "no-etag") return {};
    const digest = createHash("sha256").update(mode === "second-mtime" ? `${file.second}-${file.body.length}` : file.body).digest("hex").slice(0, 16);
    return { ETag: mode === "weak-etag" ? `W/"${digest}"` : `"${digest}"` };
  };

  const server = createServer(async (request, response) => {
    const cors = corsHeaders();
    if (request.method === "OPTIONS") {
      response.writeHead(204, cors).end();
      return;
    }
    const url = new URL(request.url, "http://localhost");
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    const body = Buffer.concat(chunks);
    if (request.headers.authorization !== `Basic ${Buffer.from(`${USER}:${PASSWORD}`).toString("base64")}`) {
      response.writeHead(401, { ...cors, "WWW-Authenticate": 'Basic realm="keex-synthetic"' }).end();
      return;
    }
    const path = url.pathname;
    const isTarget = path.endsWith(".kdbx") && !path.includes("keex-conflict");
    if (mode === "cross-redirect" && isTarget) {
      response.writeHead(307, { ...cors, Location: elsewhereUrl }).end();
      return;
    }
    if (mode === "same-origin-redirect" && isTarget) {
      response.writeHead(307, { ...cors, Location: "/moved.kdbx" }).end();
      return;
    }
    if (mode === "html-login" && request.method === "GET") {
      response.writeHead(200, { ...cors, "Content-Type": "text/html", ETag: '"login"' }).end("<html>请登录</html>");
      return;
    }
    for (const [fault, status] of [["status-403", 403], ["status-423", 423], ["status-429", 429], ["status-507", 507], ["status-500", 500]]) {
      if (mode === fault && request.method === "PUT") {
        response.writeHead(status, cors).end();
        return;
      }
    }
    const file = files.get(path);
    if (request.method === "GET" || request.method === "HEAD") {
      if (!file) {
        response.writeHead(404, cors).end();
        return;
      }
      const cache = mode === "cacheable" ? { "Cache-Control": "public, max-age=3600" } : {};
      response.writeHead(200, { ...cors, ...etagOf(file), ...cache, "Content-Length": file.body.length }).end(request.method === "GET" ? file.body : undefined);
      return;
    }
    if (request.method === "DELETE") {
      files.delete(path);
      response.writeHead(204, cors).end();
      return;
    }
    if (request.method === "PUT" && isTarget) {
      // 模拟连接在响应前断开：服务器做到哪一步，客户端都只看到网络错误。
      if (mode === "drop-before-write") { request.socket.destroy(); return; }
      if (mode === "write-then-drop") { files.set(path, { body, second: 0 }); request.socket.destroy(); return; }
      if (mode === "truncate-then-drop") { files.set(path, { body: body.subarray(0, body.length >> 1), second: 0 }); request.socket.destroy(); return; }
      if (mode === "truncate-header-then-drop") { files.set(path, { body: body.subarray(0, 40), second: 0 }); request.socket.destroy(); return; }
    }
    if (request.method === "PUT") {
      const ignoring = mode === "ignore-conditions";
      if (!ignoring && request.headers["if-none-match"] === "*" && file) {
        response.writeHead(412, cors).end();
        return;
      }
      const ifMatch = request.headers["if-match"];
      if (!ignoring && ifMatch && (!file || etagOf(file).ETag !== ifMatch)) {
        response.writeHead(412, cors).end();
        return;
      }
      files.set(path, { body, second: Math.floor(Date.now() / 1000) });
      response.writeHead(file ? 204 : 201, cors).end();
      return;
    }
    response.writeHead(405, cors).end();
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  return {
    url: `http://127.0.0.1:${server.address().port}`,
    leaks,
    files,
    stop: async () => {
      server.closeAllConnections();
      elsewhere.closeAllConnections();
      await new Promise((resolve) => server.close(resolve));
      await new Promise((resolve) => elsewhere.close(resolve));
    },
  };
}

/**
 * 裸 socket 发一半请求就断开，看服务器怎么处理目标文件。浏览器里本机传得太快，断不下来，
 * 所以服务器的行为在这里测，客户端的判断用上面的脚本模式测。
 */
export function interruptedPut(url, headers, body, sentBytes) {
  const target = new URL(url);
  return new Promise((resolve, reject) => {
    const socket = connect(Number(target.port), target.hostname, () => {
      const lines = [`PUT ${target.pathname} HTTP/1.1`, `Host: ${target.host}`, `Content-Length: ${body.length}`,
        ...Object.entries(headers).map(([k, v]) => `${k}: ${v}`), "", ""];
      socket.write(lines.join("\r\n"));
      socket.write(body.subarray(0, sentBytes), () => {
        setTimeout(() => { socket.destroy(); setTimeout(resolve, 500); }, 200);
      });
    });
    socket.on("error", reject);
  });
}

export const SCRIPTED_MODES = [
  "strict", "no-cors", "wildcard", "no-expose", "no-etag", "weak-etag", "second-mtime", "ignore-conditions",
  "html-login", "cross-redirect", "same-origin-redirect", "cacheable",
  "write-then-drop", "drop-before-write", "truncate-then-drop", "truncate-header-then-drop",
  "status-403", "status-423", "status-429", "status-507", "status-500",
];
