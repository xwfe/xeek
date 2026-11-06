// forui 预实验：同一个 Flutter 页面打成 JS 和 Wasm 两种 Web 包，放在 ADR-0007 的严格 CSP 下看：
// 有没有第三方请求和 CSP 拦截、中文能不能显示、读屏树里有什么、秘密有没有进 DOM；Chrome 另测输入法组合态。
//
//   node ../forui_candidate/mirror_fonts.mjs   先镜像中文回退字体，不镜像的话中文会显示成方块
//   node drive-forui.mjs                       chrome、firefox、webkit 都跑 JS 和 Wasm 两种编译
//   node drive-forui.mjs chrome                只跑指定浏览器
//
// 结果和截图写进 tests/forui_candidate/results/。只用公开合成数据。
import { execFileSync } from "node:child_process";
import { cp, mkdir, stat, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { startServer } from "./server.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
process.env.PLAYWRIGHT_BROWSERS_PATH ??= join(HERE, ".browsers");
const EXPERIMENT = join(HERE, "..", "forui_candidate");
const APP = join(EXPERIMENT, "app");
const RESULTS = join(EXPERIMENT, "results");
const FONTS = join(EXPERIMENT, ".fallback-fonts");
const HIDDEN_VALUE = "Kx-synth-00000!";
const TABS = ["密码", "验证", "证件", "银行", "设置"];
// 390 宽视口里搜索框的位置。不开读屏时页面上没有可定位的元素，只能按坐标点。
const SEARCH_FIELD = { x: 195, y: 106 };

async function build(mode) {
  execFileSync("flutter", ["build", "web", "--release", "--no-web-resources-cdn", "--csp", "--no-source-maps",
    ...(mode === "wasm" ? ["--wasm"] : []), "--output", join("build", `web-${mode}`)],
  { cwd: APP, stdio: "ignore", env: { ...process.env, PUB_CACHE: join(EXPERIMENT, ".pub-cache") } });
  const root = join(APP, "build", `web-${mode}`);
  if (await stat(FONTS).catch(() => null)) await cp(FONTS, join(root, "fallback-fonts"), { recursive: true });
  return root;
}

const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const countOf = (snapshot) => snapshot.match(/共 (\d+) 条/)?.[1] ?? null;

/** Flutter 默认不建读屏树，读屏软件按下页面里那个隐藏按钮后才建。这里替读屏软件按一下。 */
async function enableSemantics(page) {
  await page.evaluate(() => document.querySelector("flt-semantics-placeholder")?.click());
  await page.waitForSelector("flt-semantics", { state: "attached", timeout: 20_000 });
  await pause(800);
}

async function open(context, origin) {
  const page = await context.newPage();
  await page.goto(`${origin}/index.html`);
  await page.waitForSelector("flutter-view", { timeout: 90_000 });
  await pause(5000);
  return page;
}

/**
 * Chrome 的调试协议能直接发输入法组合事件，效果等同于用拼音输入法打字还没选词。
 * 两条路径分开测：普通用户手指点输入框；开着读屏时点读屏树里的输入框。
 * 不开读屏时画面上的数字读不出来，只能事后打开读屏树看；组合中途打开会打断组合，
 * 所以普通路径的“组合中”和“上屏后”各用一次全新加载。
 */
async function compose(context, origin, withScreenReader, commit) {
  const page = await open(context, origin);
  const cdp = await context.newCDPSession(page);
  try {
    if (withScreenReader) {
      await enableSemantics(page);
      await page.getByRole("textbox", { name: /搜索/ }).click();
    } else {
      await page.mouse.click(SEARCH_FIELD.x, SEARCH_FIELD.y);
    }
    await pause(500);
    await cdp.send("Input.imeSetComposition", { text: "shi", selectionStart: 3, selectionEnd: 3 });
    await pause(400);
    await cdp.send("Input.imeSetComposition", { text: "shili", selectionStart: 5, selectionEnd: 5 });
    await pause(600);
    if (commit) {
      await cdp.send("Input.insertText", { text: "示例" });
      await pause(1000);
    }
    if (!withScreenReader) await enableSemantics(page);
    return countOf(await page.locator("body").ariaSnapshot());
  } finally {
    await page.close();
  }
}

async function imeCheck(context, origin, withScreenReader) {
  return {
    duringComposition: await compose(context, origin, withScreenReader, false),
    afterCommit: await compose(context, origin, withScreenReader, true),
  };
}

async function run(name, type, launch, mode, root) {
  const label = `forui-${name}-${mode}`;
  const { server, origin } = await startServer({ root, wasm: true });
  const browser = await type.launch({ headless: true, ...launch });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, locale: "zh-CN" });
  const external = new Set();
  const failed = new Set();
  const fonts = new Set();
  const violations = new Set();
  let downloaded = 0;
  let fallbackFonts = { files: 0, bytes: 0 };
  await context.addInitScript(() => {
    window.__csp = [];
    document.addEventListener("securitypolicyviolation", (e) => window.__csp.push(`${e.violatedDirective} ${e.blockedURI}`));
  });
  const started = Date.now();
  const page = await context.newPage();
  page.on("request", (request) => {
    const url = request.url();
    if (url.startsWith("http") && !url.startsWith(origin)) external.add(new URL(url).host);
    if (/\.(ttf|otf|woff2?)(\?|$)/.test(url) && !url.includes("/fallback-fonts/")) fonts.add(url.split("/").pop());
  });
  page.on("requestfailed", (request) => failed.add(`${request.url().replace(origin, "")} ${request.failure()?.errorText}`));
  page.on("response", async (response) => {
    const size = await response.body().then((b) => b.length, () => 0);
    downloaded += size;
    if (response.url().includes("/fallback-fonts/")) {
      fallbackFonts = { files: fallbackFonts.files + 1, bytes: fallbackFonts.bytes + size };
      if (response.status() !== 200) failed.add(`${response.url().replace(origin, "")} ${response.status()}`);
    }
  });
  page.on("console", (message) => {
    if (/Content Security Policy|Content-Security-Policy|CSP/i.test(message.text())) violations.add(message.text().slice(0, 160));
  });
  try {
    await page.goto(`${origin}/index.html`);
    await page.waitForSelector("flutter-view", { timeout: 90_000 });
    // 只量到 Flutter 视图挂上页面；后面固定等的 5 秒是给首屏和字体加载的余量，不算在内。
    const flutterViewSeconds = Math.round((Date.now() - started) / 100) / 10;
    await pause(5000);
    await page.screenshot({ path: join(RESULTS, `${label}-list.png`) });
    await enableSemantics(page);
    const list = await page.locator("body").ariaSnapshot();

    await page.getByRole("button", { name: /示例银行 00000/ }).first().click();
    await pause(1500);
    await page.screenshot({ path: join(RESULTS, `${label}-detail.png`) });
    const detail = await page.locator("body").ariaSnapshot();
    const inputTypes = await page.evaluate(() => [...document.querySelectorAll("input, textarea")].map((e) => e.type || e.tagName));
    const leakedBeforeReveal = await page.evaluate((secret) => document.documentElement.outerHTML.includes(secret)
      || [...document.querySelectorAll("input, textarea")].some((e) => e.value.includes(secret)), HIDDEN_VALUE) || detail.includes(HIDDEN_VALUE);
    const csp = [...violations, ...(await page.evaluate(() => window.__csp))];
    // 被 CSP 拦下的请求根本没发出去，request 事件里看不到，只能从违规记录里找被拦的第三方地址。
    const blockedHosts = [...new Set(csp.map((v) => v.match(/https?:\/\/([^/\s']+)/)?.[1]).filter((h) => h && !origin.includes(h)))];
    const ime = name === "chrome"
      ? { plain: await imeCheck(context, origin, false), screenReader: await imeCheck(context, origin, true) }
      : null;
    const summary = {
      browser: `${name} ${browser.version()}`,
      mode,
      flutterViewSeconds,
      downloadedMiB: Math.round(downloaded / 104857.6) / 10,
      externalHosts: [...external],
      blockedHosts,
      inlineStyleViolations: csp.filter((v) => /style-src|inline style/.test(v)).length,
      otherViolations: csp.filter((v) => !/style-src|inline style/.test(v)).slice(0, 5),
      failedRequests: [...failed].slice(0, 10),
      appFonts: [...fonts],
      fallbackFonts,
      tabsInSemantics: Object.fromEntries(TABS.map((tab) => [tab, list.includes(tab)])),
      listCount: countOf(list),
      otpHidden: detail.includes("动态口令，已隐藏"),
      inputTypes,
      secretLeakedBeforeReveal: leakedBeforeReveal,
      ime,
    };
    console.log(label, JSON.stringify(summary));
    await writeFile(join(RESULTS, `${label}.json`), `${JSON.stringify({ ...summary, list, detail }, null, 2)}\n`);
    return summary.externalHosts.length + summary.blockedHosts.length + (summary.secretLeakedBeforeReveal ? 1 : 0);
  } catch (error) {
    await page.screenshot({ path: join(RESULTS, `${label}-error.png`) }).catch(() => {});
    console.log(label, "失败", error.message.split("\n")[0], [...violations].slice(0, 3), [...external], [...failed].slice(0, 5));
    return 1;
  } finally {
    await browser.close();
    server.close();
  }
}

async function main() {
  await mkdir(RESULTS, { recursive: true });
  const { chromium, firefox, webkit } = await import("playwright");
  const browsers = { chrome: [chromium, { channel: "chrome" }], firefox: [firefox, {}], webkit: [webkit, {}] };
  const roots = { js: await build("js"), wasm: await build("wasm") };
  let failures = 0;
  for (const name of process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(browsers)) {
    const [type, launch] = browsers[name];
    for (const [mode, root] of Object.entries(roots)) failures += await run(name, type, launch, mode, root);
  }
  process.exit(failures ? 1 : 0);
}

await main();
