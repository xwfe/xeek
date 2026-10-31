// K070 驱动：让浏览器在 Worker 里跑补丁版 keepass，把写出的库交给独立核对脚本。
//
//   node drive-core.mjs                 全部可驱动的浏览器
//   node drive-core.mjs chrome firefox  指定浏览器
//   node drive-core.mjs --serve 47113   只起服务，手动在 Safari 或真机打开打印的地址
import { writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { runCheck, serve } from "./core-server.mjs";
import { RESULTS } from "./server.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
process.env.PLAYWRIGHT_BROWSERS_PATH ??= join(HERE, ".browsers");
const TIMEOUT = Number(process.env.K070_TIMEOUT ?? 900_000);

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
