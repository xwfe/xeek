// K070 驱动：让浏览器在 Worker 里跑补丁版 keepass，把写出的库交给独立核对脚本。
//
//   node drive-core.mjs                 全部可驱动的浏览器
//   node drive-core.mjs chrome firefox  指定浏览器
//   node drive-core.mjs --serve 47113   只起服务，手动在 Safari 或真机打开打印的地址
import { execFileSync } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { RESULTS, startServer } from "./server.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
process.env.PLAYWRIGHT_BROWSERS_PATH ??= join(HERE, ".browsers");
const FIXTURES = join(HERE, "..", "fixtures", "kdbx");
const PYTHON = process.env.PYTHON ?? "python3";
const CHECK = join(HERE, "..", "wasm_core", "check_outputs.py");
const OUTPUTS = join(RESULTS, "wasm-out");
const TIMEOUT = Number(process.env.K070_TIMEOUT ?? 900_000);
const CONFIG_DIRECTORY = join(HERE, "..", "wasm_core", "target", "inputs");

async function serve(options) {
  const configPath = execFileSync(PYTHON, ["-B", CHECK, "inputs", CONFIG_DIRECTORY], { encoding: "utf8" }).trim();
  const raw = await readFile(configPath, "utf8");
  // @ 开头的文件在实验输入目录里，别的都是登记过的样本；页面只能拿这些，不能读任意路径。
  const config = JSON.parse(raw);
  const allowed = new Map();
  const add = (file) => {
    if (file) allowed.set(file, file.startsWith("@") ? join(dirname(configPath), file.slice(1)) : resolve(FIXTURES, file));
  };
  config.roundTrips.forEach((s) => add(s.file));
  config.allSamples.forEach((s) => { add(s.file); add(s.keyfile); });
  add(config.guarded.unknown);
  add(config.guarded.protected);
  await mkdir(OUTPUTS, { recursive: true });
  const site = await startServer({
    ...options,
    wasm: true,
    samples: allowed,
    uploads: OUTPUTS,
    routes: { "/core-config.json": () => config },
  });
  return { ...site, configPath };
}

function runCheck(label, configPath) {
  const report = join(RESULTS, `${label}.json`);
  try {
    const output = execFileSync(PYTHON, ["-B", CHECK, "check", report, OUTPUTS, configPath], { encoding: "utf8", maxBuffer: 1 << 24 });
    return JSON.parse(output);
  } catch (error) {
    if (error.stdout) return JSON.parse(error.stdout);
    throw error;
  }
}

function summarize(name, report) {
  console.log(`${name}`);
  for (const [probe, result] of Object.entries(report.results)) {
    console.log(`  ${probe.padEnd(34)} ${result.ok ? "通过" : "失败"} ${result.error ?? ""}`);
  }
}

async function main() {
  const argv = process.argv.slice(2);
  if (argv[0] === "--serve") {
    const { origin, configPath } = await serve({
      port: Number(argv[1] ?? 0),
      saveReports: true,
      onReport: (report) => {
        summarize(report.label, report);
        console.log(JSON.stringify(runCheck(report.label, configPath), null, 2));
      },
    });
    console.log(`${origin}/core.html?auto=safari-core`);
    return;
  }
  const { chromium, firefox, webkit } = await import("playwright");
  const browsers = {
    chrome: [chromium, { channel: "chrome" }],
    edge: [chromium, { channel: "msedge" }],
    firefox: [firefox, {}],
    webkit: [webkit, {}],
  };
  let failures = 0;
  for (const name of argv.length ? argv : Object.keys(browsers)) {
    const [type, launch] = browsers[name];
    const label = `core-${name}`;
    let done;
    const reported = new Promise((r) => { done = r; });
    const { server, origin, configPath } = await serve({ saveReports: true, onReport: (report) => done(report) });
    const browser = await type.launch({ headless: true, ...launch });
    try {
      const page = await (await browser.newContext()).newPage();
      page.on("pageerror", (error) => console.log("  pageerror", error.message));
      await page.goto(`${origin}/core.html?auto=${label}`);
      const report = await Promise.race([
        reported,
        new Promise((_, reject) => setTimeout(() => reject(new Error("探针没有按时上报")), TIMEOUT)),
      ]);
      summarize(`${name} ${browser.version()}`, report);
      failures += report.failed.length;
      const checked = runCheck(label, configPath);
      console.log(JSON.stringify(checked.facts));
      if (checked.failures.length) console.log("  核对失败", JSON.stringify(checked.failures, null, 1));
      failures += checked.failures.length;
      await writeFile(join(RESULTS, `${label}-version.txt`), `${browser.version()}\n`);
    } catch (error) {
      console.log(`${name} 失败 ${error.message.split("\n")[0]}`);
      console.log(await browser.contexts()[0]?.pages()[0]?.textContent("#log").catch(() => ""));
      failures += 1;
    } finally {
      await browser.close();
      server.close();
    }
  }
  process.exit(failures ? 1 : 0);
}

await main();
