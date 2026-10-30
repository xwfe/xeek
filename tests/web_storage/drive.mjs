// K071 驱动：跑探针，再做页面自己做不到的事（杀进程、改配额、取消下载、重启浏览器）。
// 结果写进 results/，不变量失败时退出码非 0；能力缺失只记录，不算失败。
//
//   node drive.mjs                    全部可驱动的浏览器
//   node drive.mjs chrome firefox     指定浏览器
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { RESULTS, startServer } from "./server.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
// Playwright 在加载时读这个变量，所以要先设好再加载它。
process.env.PLAYWRIGHT_BROWSERS_PATH ??= join(HERE, ".browsers");
const { chromium, firefox, webkit } = await import("playwright");

// 官方发行版和 Playwright 自带版本要分开写：后者打过补丁，结论不能直接算到官方版头上。
const BROWSERS = {
  chrome: { type: chromium, options: { channel: "chrome" }, build: "官方发行版", engine: "chromium" },
  edge: { type: chromium, options: { channel: "msedge" }, build: "官方发行版", engine: "chromium" },
  firefox: { type: firefox, options: {}, build: "Playwright 补丁版", engine: "firefox" },
  webkit: { type: webkit, options: {}, build: "Playwright 构建（不是 Safari）", engine: "webkit" },
};
const VAULT = "k071";
const KILL_ROUNDS = 8;
const SCENARIO_TIMEOUT = 150_000;

const sha = (bytes) => createHash("sha256").update(bytes).digest("hex");
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function profile() {
  return mkdtemp(join(tmpdir(), "keex-k071-"));
}

async function launch(config, directory, extra = {}) {
  const context = await config.type.launchPersistentContext(directory, {
    headless: true,
    acceptDownloads: true,
    ...config.options,
    ...extra,
  });
  return context;
}

async function openLab(context, origin) {
  const page = await context.newPage();
  await page.goto(`${origin}/index.html`);
  await page.waitForFunction(() => document.documentElement.dataset.ready === "true");
  return page;
}

/** 浏览器真实崩溃：杀掉这个配置目录下的全部进程，不给它任何收尾机会。 */
function killProfile(directory) {
  execFileSync("pkill", ["-9", "-f", directory], { stdio: "ignore" });
}

const scenarios = {
  /**
   * 页面自己跑完全部探针并上报，和 Safari、真机走同一条路。
   * Playwright 默认关掉 Chromium 的 BFCache，这里放开，否则测不到恢复页面的情况。
   */
  async probes({ config, origin, name, reports }) {
    const directory = await profile();
    const extra = config.engine === "chromium" ? { ignoreDefaultArgs: ["--disable-back-forward-cache"] } : {};
    const context = await launch(config, directory, extra);
    try {
      const page = await context.newPage();
      const report = reports.next(name);
      await page.goto(`${origin}/index.html?auto=${name}`);
      const result = await report;
      return { ok: result.failed.length === 0, failed: result.failed, capabilities: result.capabilities, results: result.probes, bfcache: result.bfcache };
    } finally {
      await context.close();
      await rm(directory, { recursive: true, force: true });
    }
  },

  /** 提交成功后重启浏览器，内容还在；隐私模式的对照放在 privateMode。 */
  async survivesRestart({ config, origin }) {
    const directory = await profile();
    let context = await launch(config, directory);
    try {
      let page = await openLab(context, origin);
      const committed = await page.evaluate(async (vault) => {
        const store = await window.lab.CipherCache.open(vault);
        const result = await store.commit(await window.lab.variant(1), 0);
        store.close();
        return result;
      }, VAULT);
      await context.close();
      context = await launch(config, directory);
      page = await openLab(context, origin);
      const loaded = await page.evaluate(async (vault) => {
        const store = await window.lab.CipherCache.open(vault);
        const result = await store.load();
        store.close();
        return { status: result.status, generation: result.generation, sha256: await window.lab.sha256(result.bytes) };
      }, VAULT);
      return { ok: loaded.status === "ok" && loaded.sha256 === committed.sha256, loaded };
    } finally {
      await context.close().catch(() => {});
      await rm(directory, { recursive: true, force: true });
    }
  },

  /**
   * 不停提交时杀掉整个浏览器。重开后只允许两种结果：最后确认的版本，或正在提交的下一版。
   * 这模拟的是进程崩溃，不是断电：操作系统的页缓存还在，所以证明不了真正落盘。
   */
  async killDuringCommit({ config, origin }) {
    const directory = await profile();
    const rounds = [];
    let context;
    try {
      for (let round = 0; round < KILL_ROUNDS; round += 1) {
        context = await launch(config, directory);
        const page = await openLab(context, origin);
        // 确认记录放在页面外：浏览器被杀后，只有这里的记录是可信的。
        let confirmed = await page.evaluate(async (vault) => {
          const store = await window.lab.CipherCache.open(vault);
          const generation = await store.generation();
          store.close();
          return generation;
        }, VAULT);
        await page.exposeFunction("confirmCommit", (generation) => { confirmed = generation; });
        await page.evaluate(async (vault) => {
          const { lab } = window;
          const store = await lab.CipherCache.open(vault);
          (async () => {
            const bytes = await lab.grown(4 * 1024 * 1024, 7);
            for (;;) {
              const generation = await store.generation();
              const result = await store.commit(bytes, generation);
              await window.confirmCommit(result.generation);
            }
          })();
        }, VAULT);
        await sleep(150 + round * 90);
        const before = confirmed;
        killProfile(directory);
        await context.close().catch(() => {});
        await sleep(300);

        context = await launch(config, directory);
        const check = await openLab(context, origin);
        const loaded = await check.evaluate(async (vault) => {
          const store = await window.lab.CipherCache.open(vault);
          const result = await store.load();
          store.close();
          return { status: result.status, generation: result.generation };
        }, VAULT);
        await context.close();
        rounds.push({ confirmed: before, reopened: loaded.generation, status: loaded.status });
      }
      const torn = rounds.filter((r) => r.status === "corrupt");
      const lost = rounds.filter((r) => r.reopened < r.confirmed);
      return { ok: torn.length === 0 && lost.length === 0, torn: torn.length, lost: lost.length, rounds };
    } finally {
      await context?.close().catch(() => {});
      await rm(directory, { recursive: true, force: true });
    }
  },

  /** 两个真实标签：写锁互斥；持锁标签崩溃后锁被放开；它留下的旧基线提交不过去。 */
  async twoTabs({ config, origin }) {
    const directory = await profile();
    const context = await launch(config, directory);
    try {
      const [a, b] = [await openLab(context, origin), await openLab(context, origin)];
      const acquire = (page) => page.evaluate(async (vault) => {
        const writer = await window.lab.acquireWriter(vault);
        window.writer = writer;
        return writer.status;
      }, VAULT);
      const first = await acquire(a);
      const blocked = await acquire(b);
      await a.evaluate(async (vault) => {
        const store = await window.lab.CipherCache.open(vault);
        window.store = store;
        window.base = (await store.commit(await window.lab.variant(1), 0)).generation;
      }, VAULT);
      // A 还拿着第 1 版时 B 不走锁直接提交一版，相当于 A 的锁判断出了错：条件提交是第二道保险。
      await b.evaluate(async (vault) => {
        const store = await window.lab.CipherCache.open(vault);
        await store.commit(await window.lab.variant(2), 1);
        store.close();
      }, VAULT);
      const stale = await a.evaluate(async () => window.lab.refused(window.store.commit(await window.lab.variant(3), window.base)));
      await a.close();
      await sleep(200);
      const afterClose = await acquire(b);
      return {
        ok: first === "writer" && blocked === "busy" && stale === "conflict" && afterClose === "writer",
        first, blocked, stale, afterClose,
      };
    } finally {
      await context.close();
      await rm(directory, { recursive: true, force: true });
    }
  },

  /**
   * 持写锁的页面离开后可能留在 BFCache 里：看不见的页面不能继续占着锁，否则别的标签一直只读。
   */
  async writerLockAcrossBFCache({ config, origin }) {
    const directory = await profile();
    const extra = config.engine === "chromium" ? { ignoreDefaultArgs: ["--disable-back-forward-cache"] } : {};
    const context = await launch(config, directory, extra);
    try {
      const [a, b] = [await openLab(context, origin), await openLab(context, origin)];
      const acquire = (page) => page.evaluate(async (vault) => {
        window.writer = await window.lab.acquireWriter(vault);
        return window.writer.status;
      }, VAULT);
      const first = await acquire(a);
      await a.evaluate(() => { window.restored = null; addEventListener("pageshow", (e) => { window.restored = e.persisted; }); });
      await a.goto(`${origin}/away.html?stay=1`);
      await sleep(300);
      const whileAway = await acquire(b);
      await b.evaluate(() => window.writer.release?.());
      // 从 BFCache 恢复不会触发 load，等 load 会一直超时；只等导航提交。
      await a.goBack({ waitUntil: "commit", timeout: 15_000 });
      await a.waitForFunction(() => document.documentElement.dataset.ready === "true", null, { timeout: 15_000 });
      await sleep(300);
      const back = await a.evaluate(() => ({ restored: window.restored === true, released: window.writer?.released ?? null }));
      const reacquire = await acquire(a);
      return {
        ok: first === "writer" && whileAway === "writer" && reacquire === "writer" && (!back.restored || back.released === true),
        first, whileAway, ...back, reacquire,
      };
    } finally {
      await context.close();
      await rm(directory, { recursive: true, force: true });
    }
  },

  /**
   * 配额满：报配额错误，旧版本还能完整读出，界面不说已保存。只有 Chromium 能把配额调小；
   * Firefox 的 dom.quotaManager 配置项实测不生效（estimate 仍是 10 GiB），另两个引擎看 diskFull。
   */
  async quotaExceeded({ config, origin }) {
    if (config.engine !== "chromium") return { ok: true, limited: "无法调小配额，失败路径见 diskFull" };
    const directory = await profile();
    const context = await launch(config, directory);
    try {
      const page = await openLab(context, origin);
      const cdp = await context.newCDPSession(page);
      await cdp.send("Storage.overrideQuotaForOrigin", { origin, quotaSize: 48 * 1024 * 1024 });
      const result = await page.evaluate(async (vault) => {
        const { lab } = window;
        const store = await lab.CipherCache.open(vault);
        const small = await lab.grown(4 * 1024 * 1024, 1);
        await store.commit(small, 0);
        const expected = await lab.sha256(small);
        // 用别的库 ID 把配额占满，再提交目标库；旧版本必须还在。
        let filled = null;
        const filler = await lab.grown(8 * 1024 * 1024, 2);
        for (let n = 0; n < 8 && !filled; n += 1) {
          store.vaultId = lab.unique("filler");
          filled = await lab.refused(store.commit(filler, 0));
        }
        store.vaultId = vault;
        lab.show(lab.SaveState.MEMORY_ONLY);
        const retry = await lab.refused(store.commit(await lab.grown(64 * 1024 * 1024, 3), 1));
        const loaded = await store.load();
        store.close();
        return {
          filled,
          retry,
          status: loaded.status,
          generation: loaded.generation,
          intact: loaded.status === "ok" && (await lab.sha256(loaded.bytes)) === expected,
          shown: document.querySelector("#save-state").dataset.state,
        };
      }, VAULT);
      return { ok: result.retry === "quota" && result.intact && result.generation === 1 && result.shown === "memory-only", ...result };
    } finally {
      await context.close();
      await rm(directory, { recursive: true, force: true });
    }
  },

  /**
   * 磁盘真的写满（配置目录放在 300 MB 的磁盘镜像上）。不依赖调试接口，三个引擎都能测。
   * 不管报哪种错，都不能说已保存；重启浏览器后，确认过的旧版本必须还能完整读出。
   */
  async diskFull({ config, origin }) {
    const mount = await mkdtemp(join(tmpdir(), "keex-k071-disk-"));
    const image = `${mount}.dmg`;
    execFileSync("hdiutil", ["create", "-size", "300m", "-fs", "HFS+", "-volname", "keex-k071", "-quiet", image]);
    execFileSync("hdiutil", ["attach", "-mountpoint", mount, "-nobrowse", "-quiet", image]);
    const directory = join(mount, "profile");
    let context;
    try {
      context = await launch(config, directory);
      let page = await openLab(context, origin);
      const result = await page.evaluate(async (vault) => {
        const { lab } = window;
        const store = await lab.CipherCache.open(vault);
        const small = await lab.grown(4 * 1024 * 1024, 1);
        await store.commit(small, 0);
        const expected = await lab.sha256(small);
        const filler = await lab.grown(16 * 1024 * 1024, 2);
        // 记下底层错误名：同样是存储耗尽，各浏览器给的错误不一样。
        const failure = (promise) => promise.then(() => null, (error) => ({ kind: error.kind ?? null, cause: error.cause?.name ?? error.name }));
        let failed = null;
        let filled = 0;
        while (!failed && filled < 40) {
          store.vaultId = lab.unique("filler");
          failed = await failure(store.commit(filler, 0));
          if (!failed) filled += 1;
        }
        store.vaultId = vault;
        lab.show(lab.SaveState.MEMORY_ONLY);
        const retry = await failure(store.commit(filler, 1));
        const shown = document.querySelector("#save-state").dataset.state;
        store.close();
        return { failed, filledMiB: filled * 16, retry, expected, shown };
      }, VAULT);
      await context.close();
      context = await launch(config, directory);
      page = await openLab(context, origin);
      const loaded = await page.evaluate(async (vault) => {
        const store = await window.lab.CipherCache.open(vault);
        const version = await store.load();
        store.close();
        return { status: version.status, generation: version.generation, sha256: version.bytes && await window.lab.sha256(version.bytes) };
      }, VAULT);
      return {
        ok: result.failed?.kind != null && result.retry?.kind != null && result.shown === "memory-only"
          && loaded.status === "ok" && loaded.generation === 1 && loaded.sha256 === result.expected,
        failed: result.failed, retry: result.retry, filledMiB: result.filledMiB, loaded: { status: loaded.status, generation: loaded.generation },
      };
    } finally {
      await context?.close().catch(() => {});
      execFileSync("hdiutil", ["detach", "-force", "-quiet", mount]);
      await rm(mount, { recursive: true, force: true });
      await rm(image, { force: true });
    }
  },

  /**
   * 隐私模式：能力有没有；结束后数据是不是真没了。
   * Chromium 用 Playwright 的非持久上下文，它和隐身窗口是同一种配置类型，但不是界面上的隐身窗口；
   * 持久上下文加 --incognito 实测不生效，重启后数据还在。
   */
  async privateMode({ config, origin }) {
    if (config.engine === "webkit") return { ok: true, limited: "WebKit 构建没有隐私模式开关；真实 Safari 要手动打开隐私窗口运行 ?auto=" };
    const inside = async (page) => page.evaluate(async (vault) => {
      const { lab } = window;
      const out = {};
      out.opfs = await navigator.storage.getDirectory().then(() => "可用", (error) => error.name);
      out.quotaMiB = await navigator.storage.estimate().then((e) => Math.round(e.quota / 1048576), (error) => error.name);
      try {
        const store = await lab.CipherCache.open(vault);
        out.commit = (await store.commit(await lab.variant(1), 0)).state;
        out.load = (await store.load()).status;
        store.close();
      } catch (error) {
        out.commit = error.kind ?? error.name;
      }
      return out;
    }, VAULT);
    const statusAfter = async (page) => page.evaluate(async (vault) => {
      const store = await window.lab.CipherCache.open(vault);
      const { status } = await store.load();
      store.close();
      return status;
    }, VAULT);
    if (config.engine === "chromium") {
      const browser = await config.type.launch({ headless: true, ...config.options });
      try {
        let context = await browser.newContext();
        const result = await inside(await openLab(context, origin));
        await context.close();
        context = await browser.newContext();
        const afterRestart = await statusAfter(await openLab(context, origin));
        return { ok: afterRestart === "empty", ...result, afterRestart };
      } finally {
        await browser.close();
      }
    }
    const directory = await profile();
    const extra = { firefoxUserPrefs: { "browser.privatebrowsing.autostart": true } };
    let context = await launch(config, directory, extra);
    try {
      const result = await inside(await openLab(context, origin));
      await context.close();
      context = await launch(config, directory, extra);
      const afterRestart = await statusAfter(await openLab(context, origin));
      return { ok: afterRestart === "empty", ...result, afterRestart };
    } finally {
      await context.close().catch(() => {});
      await rm(directory, { recursive: true, force: true });
    }
  },

  /** 下载：取消或完成，页面都只说“已交给浏览器”，原文件不变。 */
  async downloadIsNotWriteBack({ config, origin }) {
    const directory = await profile();
    const context = await launch(config, directory);
    const source = join(directory, "source.kdbx");
    try {
      const page = await openLab(context, origin);
      const original = Buffer.from(await page.evaluate(async () => Array.from(new Uint8Array(await window.lab.fixture()))));
      await writeFile(source, original);
      await page.setInputFiles("#file", source);
      const offer = async () => {
        const waiting = page.waitForEvent("download");
        await page.evaluate(async () => {
          const { lab } = window;
          const bytes = await lab.variant(2);
          lab.show(lab.offerDownload(bytes, "keex-synthetic.kdbx").state);
        });
        return waiting;
      };
      const cancelled = await offer();
      await cancelled.cancel();
      const afterCancel = await page.evaluate(() => document.querySelector("#save-state").textContent);
      const finished = await offer();
      const failure = await finished.failure();
      const saved = await readFile(await finished.path());
      const afterFinish = await page.evaluate(() => document.querySelector("#save-state").dataset.state);
      const sourceUnchanged = sha(await readFile(source)) === sha(original);
      const claimsSaved = /已保存|写回|已写入/.test(afterCancel.replace("没有写回", "").replace("未改动", ""));
      return {
        ok: afterFinish === "download-initiated" && sourceUnchanged && failure === null && !claimsSaved
          && sha(saved) !== sha(original),
        afterCancel, afterFinish, sourceUnchanged,
      };
    } finally {
      await context.close();
      await rm(directory, { recursive: true, force: true });
    }
  },

  /**
   * 拖入真实磁盘文件拿到的句柄：只有读权限。不经用户授权写不进去，原文件不变，页面不说已保存。
   * 授权后的写入要点浏览器弹窗，自动化点不了，见 site/manual.html。
   */
  async realFileWithoutPermission({ config, origin }) {
    if (config.engine !== "chromium") return { ok: true, limited: "这个浏览器没有文件句柄 API，只能走下载" };
    const directory = await profile();
    const context = await launch(config, directory);
    const source = join(directory, "source.kdbx");
    try {
      const page = await openLab(context, origin);
      const original = Buffer.from("synthetic-real-file");
      await writeFile(source, original);
      await page.evaluate(() => {
        window.dropped = new Promise((resolve) => {
          addEventListener("dragover", (event) => event.preventDefault());
          addEventListener("drop", (event) => {
            event.preventDefault();
            resolve(event.dataTransfer.items[0].getAsFileSystemHandle());
          });
        });
      });
      const cdp = await context.newCDPSession(page);
      const data = { items: [], files: [source], dragOperationsMask: 1 };
      for (const type of ["dragEnter", "dragOver", "drop"]) {
        await cdp.send("Input.dispatchDragEvent", { type, x: 40, y: 40, data });
      }
      const result = await page.evaluate(async () => {
        const { lab } = window;
        const handle = await window.dropped;
        const out = {
          kind: handle.kind,
          read: await (await handle.getFile()).text(),
          readPermission: await handle.queryPermission({ mode: "read" }),
          writePermission: await handle.queryPermission({ mode: "readwrite" }),
        };
        // 拖放算用户手势，所以这里会弹授权框等人回答；无头模式没有界面，就一直等下去。
        // 界面不能把这段等待说成“正在保存”：等待期间保存状态必须还是只在内存。
        const settle = (promise) => Promise.race([
          promise.then((value) => value, (error) => error.name),
          new Promise((resolve) => setTimeout(() => resolve("pending"), 1500)),
        ]);
        lab.show(lab.SaveState.MEMORY_ONLY);
        out.write = await settle(lab.writeFileVerified(handle, new TextEncoder().encode("ours")).then((r) => {
          lab.show(r.state);
          return r.state;
        }));
        out.shown = document.querySelector("#save-state").dataset.state;
        return out;
      });
      const unchanged = sha(await readFile(source)) === sha(original);
      return {
        ok: result.write !== "file-written-verified" && unchanged && result.shown === "memory-only",
        unchanged,
        ...result,
      };
    } finally {
      await context.close();
      await rm(directory, { recursive: true, force: true });
    }
  },

  /**
   * input 选的文件在磁盘上变了之后再读会怎样。各浏览器不同，这里只记录：
   * 产品规则是选中时立刻读完并记下哈希，之后绝不重读。
   */
  async inputFileChangedOnDisk({ config, origin }) {
    const directory = await profile();
    const context = await launch(config, directory);
    const source = join(directory, "source.kdbx");
    try {
      const page = await openLab(context, origin);
      await writeFile(source, Buffer.from("synthetic-before"));
      await page.setInputFiles("#file", source);
      const before = await page.evaluate(() => document.querySelector("#file").files[0].text());
      await sleep(1100);
      await writeFile(source, Buffer.from("synthetic-after-with-a-new-size"));
      const after = await page.evaluate(() => document.querySelector("#file").files[0].text().then(
        (text) => ({ text }), (error) => ({ error: error.name })));
      const behaviour = after.error ? `报错 ${after.error}` : after.text === before ? "还是旧内容" : "悄悄变成新内容";
      return { ok: before === "synthetic-before", behaviour };
    } finally {
      await context.close();
      await rm(directory, { recursive: true, force: true });
    }
  },
};

async function versionOf(config) {
  const browser = await config.type.launch({ headless: true, ...config.options });
  const version = browser.version();
  await browser.close();
  return version;
}

async function main() {
  const argv = process.argv.slice(2);
  const only = argv.find((a) => a.startsWith("--only="))?.slice(7);
  const chosen = argv.filter((a) => !a.startsWith("--"));
  const names = chosen.length ? chosen : Object.keys(BROWSERS);
  const waiting = new Map();
  const { server, origin } = await startServer({
    onReport: (report) => waiting.get(report.label)?.(report),
  });
  const reports = {
    next: (label) => Promise.race([
      new Promise((resolve) => waiting.set(label, resolve)),
      sleep(120_000).then(() => { throw new Error("探针两分钟内没有上报"); }),
    ]),
  };
  await mkdir(RESULTS, { recursive: true });
  let failures = 0;
  for (const name of names) {
    const config = BROWSERS[name];
    const report = { browser: name, build: config.build, version: await versionOf(config), scenarios: {} };
    for (const [scenario, run] of Object.entries(scenarios)) {
      if (only && scenario !== only) continue;
      try {
        // 挂死本身也是结果（比如页面进了 BFCache 后再也回不来），不能让它拖住整轮。
        report.scenarios[scenario] = await Promise.race([
          run({ config, origin, name, reports }),
          sleep(SCENARIO_TIMEOUT).then(() => { throw new Error(`${SCENARIO_TIMEOUT / 1000} 秒内没有结束`); }),
        ]);
      } catch (error) {
        report.scenarios[scenario] = { ok: false, error: `${error.name}: ${error.message.split("\n")[0]}` };
      }
      const result = report.scenarios[scenario];
      console.log(`${name.padEnd(8)} ${scenario.padEnd(24)} ${result.ok ? (result.limited ? "受限" : "通过") : "失败"} ${result.error ?? result.limited ?? ""}`);
      if (!result.ok) failures += 1;
    }
    await writeFile(join(RESULTS, `${name}.json`), JSON.stringify(report, null, 2) + "\n");
  }
  server.close();
  // 探针超时的计时器还在，直接退出。
  process.exit(failures ? 1 : 0);
}

await main();
