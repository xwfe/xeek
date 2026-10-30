// K072 WebDAV 驱动：起测试服务器，用浏览器打开探针页等它上报，结果写进 results/。
//
//   node drive-webdav.mjs                 全部可驱动的浏览器
//   node drive-webdav.mjs chrome firefox  指定浏览器
//   node drive-webdav.mjs --serve 47111   只起服务，手动在 Safari 或真机打开打印的地址
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { RESULTS, startServer } from "./server.mjs";
import { PASSWORD, SCRIPTED_MODES, USER, interruptedPut, startApache, startScripted, startWsgiDav } from "./webdav-servers.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
process.env.PLAYWRIGHT_BROWSERS_PATH ??= join(HERE, ".browsers");
const BROWSER_TIMEOUT = Number(process.env.K072_TIMEOUT ?? 300_000);

async function fixtureBytes() {
  const fixtures = join(HERE, "..", "fixtures", "kdbx");
  const manifest = JSON.parse(await readFile(join(fixtures, "manifest.json"), "utf8"));
  return readFile(join(fixtures, manifest.samples.find((s) => s.id === "G41-RICH").file));
}

async function startAll(options) {
  const connectSources = [];
  const config = { real: [], scripted: [] };
  const stopping = [];
  const site = await startServer({
    ...options,
    connectSources,
    routes: {
      "/webdav-config.json": () => config,
      "/webdav-leaks.json": () => ({ leaks: stopping.flatMap((s) => s.leaks ?? []) }),
    },
  });
  const authorization = `Basic ${Buffer.from(`${USER}:${PASSWORD}`).toString("base64")}`;
  const seed = await fixtureBytes();
  const seedSha256 = createHash("sha256").update(seed).digest("hex");
  // WsgiDAV 的 ETag 是“inode-修改时间到秒-大小”，同一秒内同样大小的写入版本不变，探针应判它不安全。
  for (const [name, start, expectUnsafe] of [["apache", startApache], ["wsgidav", startWsgiDav, "etagChanges"]]) {
    const server = await start(site.origin);
    stopping.push(server);
    connectSources.push(server.url);
    config.real.push({ name, base: server.url, authorization, expectUnsafe });
  }
  for (const mode of SCRIPTED_MODES) {
    const server = await startScripted(site.origin, mode);
    stopping.push(server);
    connectSources.push(server.url);
    server.files.set("/vault.kdbx", { body: seed, second: 0 });
    config.scripted.push({ mode, url: `${server.url}/vault.kdbx`, authorization, seedSha256 });
  }
  // 这个地址故意不进 CSP。
  const outside = await startScripted(site.origin, "strict");
  stopping.push(outside);
  outside.files.set("/vault.kdbx", { body: seed, second: 0 });
  config.cspBlocked = { url: `${outside.url}/vault.kdbx`, authorization };
  return {
    origin: site.origin,
    stop: async () => {
      await Promise.all(stopping.map((s) => s.stop()));
      site.server.close();
    },
  };
}

/**
 * 服务器本身的事实，和浏览器无关：上传发一半断开，目标文件怎样；同一秒内写同样大小的内容，
 * 过期的 If-Match 能不能拦住。
 */
async function serverFacts(origin) {
  const authorization = `Basic ${Buffer.from(`${USER}:${PASSWORD}`).toString("base64")}`;
  const headers = { Authorization: authorization };
  const facts = {};
  for (const [name, start] of [["apache", startApache], ["wsgidav", startWsgiDav]]) {
    const server = await start(origin);
    const url = `${server.url}/facts.kdbx`;
    const body = (n, size) => Buffer.alloc(size, n);
    const put = (data, extra = {}) => fetch(url, { method: "PUT", body: data, headers: { ...headers, ...extra } });
    const settled = async () => {
      let response = await fetch(url, { headers });
      if (response.headers.get("ETag")?.startsWith("W/")) {
        await response.arrayBuffer();
        await new Promise((resolve) => setTimeout(resolve, 1100));
        response = await fetch(url, { headers });
      }
      return { etag: response.headers.get("ETag"), bytes: Buffer.from(await response.arrayBuffer()) };
    };
    const size = 8 * 1024 * 1024;
    await put(body(1, size));
    const before = await settled();
    await interruptedPut(url, { ...headers, "If-Match": before.etag }, body(2, size), size >> 1);
    const after = await settled();
    const interrupted = after.bytes.equals(before.bytes) ? "还是旧版" : `被改写：${after.bytes.length} 字节`;

    let lost = 0;
    const rounds = 6;
    for (let round = 0; round < rounds; round += 1) {
      await put(body(10 + round, 1024));
      const base = await settled();
      await put(body(30 + round, 1024), { "If-Match": base.etag });
      const stale = await put(body(50 + round, 1024), { "If-Match": base.etag });
      if (stale.ok) lost += 1;
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    facts[name] = { interruptedPut: interrupted, lostUpdates: `${lost}/${rounds}` };
    await server.stop();
  }
  return facts;
}

function summarize(report) {
  for (const [name, r] of Object.entries(report.targets)) {
    console.log(`  ${name.padEnd(22)} ${r.ok ? "通过" : "失败"} ${r.error ?? ""}`);
  }
  for (const [name, r] of Object.entries(report.results)) {
    console.log(`  ${name.padEnd(22)} ${r.ok ? "通过" : "失败"}`);
  }
}

async function main() {
  const argv = process.argv.slice(2);
  if (argv[0] === "--serve") {
    const { origin } = await startAll({
      port: Number(argv[1] ?? 0),
      saveReports: true,
      onReport: (report) => { console.log("report", report.label, report.failed); summarize(report); },
    });
    console.log(`${origin}/webdav.html?auto=safari-webdav`);
    return;
  }
  const { chromium, firefox, webkit } = await import("playwright");
  const browsers = {
    chrome: [chromium, { channel: "chrome" }],
    edge: [chromium, { channel: "msedge" }],
    firefox: [firefox, {}],
    webkit: [webkit, {}],
  };
  await mkdir(RESULTS, { recursive: true });
  let failures = 0;
  const facts = await serverFacts("http://127.0.0.1:1");
  console.log("服务器事实", JSON.stringify(facts));
  await writeFile(join(RESULTS, "webdav-servers.json"), `${JSON.stringify(facts, null, 2)}\n`);
  for (const name of argv.length ? argv : Object.keys(browsers)) {
    const [type, launch] = browsers[name];
    let resolve;
    const reported = new Promise((r) => { resolve = r; });
    const servers = await startAll({ onReport: (report) => resolve(report) });
    const browser = await type.launch({ headless: true, ...launch });
    let lastPage = null;
    try {
      const page = await (await browser.newContext()).newPage();
      lastPage = page;
      page.on("pageerror", (error) => console.log("  pageerror", error.message));
      await page.goto(`${servers.origin}/webdav.html?auto=${name}`);
      const report = await Promise.race([
        reported,
        new Promise((_, reject) => setTimeout(() => reject(new Error("探针五分钟内没有上报")), BROWSER_TIMEOUT)),
      ]);
      console.log(`${name} ${browser.version()}`);
      summarize(report);
      failures += report.failed.length;
      await writeFile(join(RESULTS, `webdav-${name}.json`), `${JSON.stringify({ version: browser.version(), ...report }, null, 2)}\n`);
    } catch (error) {
      console.log(`${name} 失败 ${error.message.split("\n")[0]}`);
      if (lastPage) console.log(await lastPage.textContent("#log").catch(() => "（页面日志读不到）"));
      failures += 1;
    } finally {
      await browser.close();
      await servers.stop();
    }
  }
  process.exit(failures ? 1 : 0);
}

await main();
