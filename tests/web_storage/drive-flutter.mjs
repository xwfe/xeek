// K070：真实 Flutter Web 页面通过 VaultCore 调 Worker 里的 Rust，再由独立核对脚本检查写出的库。
//
//   node drive-flutter.mjs                 chrome、firefox、webkit 都跑 JS 和 Wasm 两种编译
//   node drive-flutter.mjs --serve 47114   只起服务，手动在 Safari 打开打印的地址（只测 JS 编译）
//
// 同时记录严格 CSP 下被拦的东西和所有第三方请求：ADR-0007 要求不默认走第三方 CDN。
import { execFileSync } from "node:child_process";
import { copyFile, cp, rm, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { runCheck, serve } from "./core-server.mjs";
import { RESULTS } from "./server.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
process.env.PLAYWRIGHT_BROWSERS_PATH ??= join(HERE, ".browsers");
const APP = join(HERE, "..", "flutter_bridge", "app");
const SITE = join(HERE, "site");
const TIMEOUT = Number(process.env.K070_TIMEOUT ?? 240_000);
const STYLE_INLINE = process.env.K070_STYLE_INLINE === "1";

function buildApp(mode) {
  // Flutter 打包时会把 web/ 下的文件原样带上，Worker 和 WASM 就是这样进站点的。
  execFileSync("flutter", ["build", "web", "--release", "--no-web-resources-cdn", "--csp", "--no-source-maps",
    ...(mode === "wasm" ? ["--wasm"] : []), "--output", join("build", mode)], { cwd: APP, stdio: "ignore" });
  return join(APP, "build", mode);
}

async function prepareWebFiles() {
  await copyFile(join(SITE, "kdbx-worker.js"), join(APP, "web", "kdbx-worker.js"));
  await rm(join(APP, "web", "wasm"), { recursive: true, force: true });
  await cp(join(SITE, "wasm"), join(APP, "web", "wasm"), { recursive: true });
}

async function main() {
  const argv = process.argv.slice(2);
  await prepareWebFiles();
  if (argv[0] === "--serve") {
    const root = buildApp("js");
    const { origin, configPath } = await serve({
      root,
      styleInline: STYLE_INLINE,
      port: Number(argv[1] ?? 0),
      saveReports: true,
      onReport: (report) => {
        console.log("report", report.label, report.wrongPassword, report.worstFrameGapMs);
        console.log(JSON.stringify(runCheck(report.label, configPath), null, 2));
      },
    });
    console.log(`${origin}/index.html?auto=flutter-safari`);
    return;
  }
  const { chromium, firefox, webkit } = await import("playwright");
  const browsers = {
    chrome: [chromium, { channel: "chrome" }],
    firefox: [firefox, {}],
    webkit: [webkit, {}],
  };
  const roots = { js: buildApp("js"), wasm: buildApp("wasm") };
  let failures = 0;
  for (const name of argv.length ? argv : Object.keys(browsers)) {
    const [type, launch] = browsers[name];
    for (const [mode, root] of Object.entries(roots)) {
      const label = `flutter-${name}-${mode}`;
      let done;
      const reported = new Promise((resolve) => { done = resolve; });
      const { server, origin, configPath } = await serve({ root, styleInline: STYLE_INLINE, saveReports: true, onReport: (report) => done(report) });
      const browser = await type.launch({ headless: true, ...launch });
      const page = await browser.newPage();
      const external = new Set();
      let downloaded = 0;
      let usedWasm = false;
      page.on("response", async (response) => {
        const { pathname } = new URL(response.url());
        if (pathname.endsWith("main.dart.wasm")) usedWasm = true;
        // 只算站点本身，测试样本和上传不算。
        if (pathname !== "/sample" && pathname !== "/upload" && pathname !== "/report") {
          downloaded += await response.body().then((b) => b.length, () => 0);
        }
      });
      const violations = new Set();
      const started = Date.now();
      page.on("request", (request) => {
        const url = request.url();
        if (url.startsWith("http") && !url.startsWith(origin)) external.add(new URL(url).host);
      });
      page.on("console", (message) => {
        if (/Content Security Policy|Content-Security-Policy|CSP/i.test(message.text())) violations.add(message.text().slice(0, 140));
      });
      page.on("pageerror", (error) => console.log("  pageerror", error.message.slice(0, 200)));
      try {
        await page.goto(`${origin}/index.html?auto=${label}`);
        const report = await Promise.race([
          reported,
          new Promise((_, reject) => setTimeout(() => reject(new Error("没有按时上报")), TIMEOUT)),
        ]);
        await new Promise((resolve) => setTimeout(resolve, 500));
        // 逻辑跑通不代表画出来了：严格 CSP 下要看到页面真的渲染。
        await page.screenshot({ path: join(RESULTS, `${label}.png`) });
        const checked = runCheck(label, configPath);
        const summary = {
          browser: browser.version(),
          mode,
          seconds: Math.round((Date.now() - started) / 1000),
          wrongPassword: report.wrongPassword,
          worstFrameGapMs: report.worstFrameGapMs,
          usedWasm,
          downloadedMiB: Math.round(downloaded / 104857.6) / 10,
          externalHosts: [...external],
          cspViolations: [...violations],
          checkFailures: checked.failures,
          timings: Object.fromEntries(Object.entries(report.results.roundTrips.results).map(([k, v]) => [k, [v.openMs, v.totalMs]])),
        };
        console.log(label, JSON.stringify(summary));
        await writeFile(join(RESULTS, `${label}-summary.json`), `${JSON.stringify(summary, null, 2)}\n`);
        failures += checked.failures.length + (external.size ? 1 : 0);
      } catch (error) {
        console.log(label, "失败", error.message.split("\n")[0], [...violations].slice(0, 3), [...external]);
        failures += 1;
      } finally {
        await browser.close();
        server.close();
      }
    }
  }
  process.exit(failures ? 1 : 0);
}

await main();
