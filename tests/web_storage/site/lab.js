// 探针页：能自己跑完并上报（?auto=标签），这样不能被驱动的浏览器（Safari、真机）也能用同一份代码。
// 驱动（drive.mjs）只负责页面自己做不到的事：杀进程、改配额、取消下载。
import * as cache from "./cipher-cache.js";

const { CipherCache, CacheError, SaveState, SaveStateText, acquireWriter, sha256, writeFileVerified } = cache;
const session = new cache.Session();
const state = document.querySelector("#save-state");
const log = document.querySelector("#log");

function show(saveState) {
  state.textContent = SaveStateText[saveState];
  state.dataset.state = saveState;
}
show(SaveState.MEMORY_ONLY);

let cached;
async function fixture() {
  cached ??= await (await fetch("/fixture.kdbx")).arrayBuffer();
  return cached;
}

/** 合成库的第 n 个“版本”：头部不变，只改末尾字节。密文本来就不可读，这里只测存储。 */
async function variant(n) {
  const copy = (await fixture()).slice(0);
  new DataView(copy).setUint32(copy.byteLength - 4, n);
  return copy;
}

/** 真实密文不可压缩，IndexedDB 内部又会压缩；用全零填充既撑不满配额，耗时也会失真。 */
async function grown(size, n) {
  const base = new Uint8Array(await variant(n));
  const bytes = new Uint8Array(size);
  const words = new Uint32Array(bytes.buffer, 0, size >>> 2);
  let x = (n * 2654435761 + 1) >>> 0;
  for (let i = 0; i < words.length; i += 1) {
    x ^= x << 13;
    x ^= x >>> 17;
    x ^= x << 5;
    words[i] = x;
  }
  bytes.set(base);
  return bytes.buffer;
}

function unique(name) {
  return `${name}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function refused(promise) {
  try {
    await promise;
    return null;
  } catch (error) {
    return error instanceof CacheError || error?.name === "CacheError" ? error.kind : String(error?.name);
  }
}

function within(promise, ms, fallback) {
  return Promise.race([promise, new Promise((resolve) => setTimeout(() => resolve(fallback), ms))]);
}

function capabilities() {
  const handle = globalThis.FileSystemFileHandle?.prototype ?? {};
  return {
    userAgent: navigator.userAgent,
    secureContext: isSecureContext,
    indexedDB: "indexedDB" in globalThis,
    durabilityOption: "durability" in (globalThis.IDBTransaction?.prototype ?? {}),
    webLocks: "locks" in navigator,
    broadcastChannel: "BroadcastChannel" in globalThis,
    showOpenFilePicker: "showOpenFilePicker" in globalThis,
    showSaveFilePicker: "showSaveFilePicker" in globalThis,
    dragFileHandle: "getAsFileSystemHandle" in (globalThis.DataTransferItem?.prototype ?? {}),
    opfs: "getDirectory" in (navigator.storage ?? {}),
    createWritable: "createWritable" in handle,
    persist: "persist" in (navigator.storage ?? {}),
    estimate: "estimate" in (navigator.storage ?? {}),
  };
}

const probes = {
  async commitAndReload() {
    const store = await CipherCache.open(unique("cycle"));
    const first = await store.commit(await variant(1), 0);
    const second = await store.commit(await variant(2), 1);
    const loaded = await store.load();
    store.close();
    const ok = first.state === SaveState.CACHE_COMMITTED && second.generation === 2 && loaded.status === "ok"
      && (await sha256(loaded.bytes)) === (await sha256(await variant(2)));
    return { ok };
  },

  async staleBaseIsRefused() {
    const store = await CipherCache.open(unique("stale"));
    await store.commit(await variant(1), 0);
    await store.commit(await variant(2), 1);
    const kind = await refused(store.commit(await variant(3), 1));
    const loaded = await store.load();
    store.close();
    return { ok: kind === "conflict" && loaded.generation === 2, kind };
  },

  async onlyCurrentAndPreviousAreKept() {
    const vault = unique("retain");
    const store = await CipherCache.open(vault);
    for (let n = 0; n < 5; n += 1) await store.commit(await variant(n + 1), n);
    const keys = await new Promise((resolve, reject) => {
      const request = store.database.transaction("versions").objectStore("versions").getAllKeys();
      request.onsuccess = () => resolve(request.result.filter((k) => String(k).startsWith(vault)));
      request.onerror = () => reject(request.error);
    });
    store.close();
    return { ok: keys.length === 2, kept: keys.length };
  },

  async invalidBytesAreRefused() {
    const store = await CipherCache.open(unique("invalid"));
    const notKdbx = await refused(store.commit(new TextEncoder().encode("明文不许进缓存").buffer, 0));
    const truncated = await refused(store.commit((await fixture()).slice(0, 64), 0));
    const generation = await store.generation();
    store.close();
    return { ok: notKdbx === "invalid" && truncated === "invalid" && generation === 0, notKdbx, truncated };
  },

  async corruptionIsReportedNotHidden() {
    const vault = unique("corrupt");
    const store = await CipherCache.open(vault);
    await store.commit(await variant(1), 0);
    await store.commit(await variant(2), 1);
    const transaction = store.database.transaction("versions", "readwrite");
    const versions = transaction.objectStore("versions");
    const id = `${vault}:2`;
    await new Promise((resolve, reject) => {
      const read = versions.get(id);
      read.onsuccess = () => {
        new Uint8Array(read.result.bytes)[100] ^= 1;
        versions.put(read.result).onsuccess = resolve;
      };
      read.onerror = () => reject(read.error);
    });
    await new Promise((resolve) => { transaction.oncomplete = resolve; });
    const loaded = await store.load();
    store.close();
    const previousIntact = loaded.previousBytes
      && (await sha256(loaded.previousBytes)) === (await sha256(await variant(1)));
    return { ok: loaded.status === "corrupt" && Boolean(previousIntact), status: loaded.status };
  },

  async evictionIsNotMistakenForANewVault() {
    const vault = unique("evicted");
    const store = await CipherCache.open(vault);
    await store.commit(await variant(1), 0);
    await store.commit(await variant(2), 1);
    await new Promise((resolve, reject) => {
      const transaction = store.database.transaction(["versions", "heads"], "readwrite");
      transaction.objectStore("heads").delete(vault);
      transaction.objectStore("versions").delete(`${vault}:1`);
      transaction.objectStore("versions").delete(`${vault}:2`);
      transaction.oncomplete = resolve;
      transaction.onerror = () => reject(transaction.error);
    });
    const empty = await store.load();
    const kind = await refused(store.commit(await variant(3), 2));
    store.close();
    return { ok: empty.status === "empty" && kind === "evicted", kind, note: "用页面脚本删除模拟，不是浏览器真实驱逐" };
  },

  async twoWritersNeverLoseAnUpdate() {
    const vault = unique("race");
    const frames = await Promise.all([frame(), frame()]);
    const rounds = 40;
    const bytes = await variant(9);
    const runs = frames.map(async (win, side) => {
      const store = await win.cache.CipherCache.open(vault);
      let won = 0;
      let lost = 0;
      for (let n = 0; n < rounds; n += 1) {
        const base = await store.generation();
        try {
          await store.commit(bytes, base);
          won += 1;
        } catch (error) {
          if (error.kind !== "conflict") throw new Error(`side ${side}: ${error.kind ?? error}`);
          lost += 1;
        }
      }
      store.close();
      return { won, lost };
    });
    const [a, b] = await Promise.all(runs);
    const store = await CipherCache.open(vault);
    const generation = await store.generation();
    const loaded = await store.load();
    store.close();
    frames.forEach((win) => win.frameElement.remove());
    return { ok: generation === a.won + b.won && loaded.status === "ok" && a.lost + b.lost > 0, a, b, generation };
  },

  async writerLockIsExclusive() {
    if (!navigator.locks) return { ok: true, limited: "没有 Web Locks，只能只读" };
    const vault = unique("lock");
    const [other] = await Promise.all([frame()]);
    const held = await other.cache.acquireWriter(vault);
    const blocked = await acquireWriter(vault);
    held.release();
    await new Promise((resolve) => setTimeout(resolve, 50));
    const after = await acquireWriter(vault);
    after.release?.();
    other.frameElement.remove();
    return { ok: held.status === "writer" && blocked.status === "busy" && after.status === "writer", blocked: blocked.status };
  },

  async missingLockApiMeansReadOnly() {
    const descriptor = Object.getOwnPropertyDescriptor(Navigator.prototype, "locks");
    if (!descriptor) return { ok: (await acquireWriter("x")).status === "unsupported", note: "浏览器本来就没有" };
    Object.defineProperty(Navigator.prototype, "locks", { configurable: true, get: () => undefined });
    const result = await acquireWriter("x");
    Object.defineProperty(Navigator.prototype, "locks", descriptor);
    return { ok: result.status === "unsupported" };
  },

  async opfsWritableReplacesOnlyOnClose() {
    if (!navigator.storage?.getDirectory) return { ok: true, limited: "没有 OPFS" };
    let root;
    try {
      root = await navigator.storage.getDirectory();
    } catch (error) {
      return { ok: true, limited: `OPFS 不可用：${error.name}` };
    }
    const name = unique("writable");
    const handle = await root.getFileHandle(name, { create: true });
    if (!handle.createWritable) {
      await root.removeEntry(name);
      return { ok: true, limited: "没有 createWritable" };
    }
    const text = async () => (await handle.getFile()).text();
    const put = async (value) => {
      const writable = await handle.createWritable();
      await writable.write(value);
      await writable.close();
    };
    await put("old");
    const pending = await handle.createWritable();
    await pending.write("new");
    const whileOpen = await text();
    await pending.abort();
    const afterAbort = await text();
    const verified = await writeFileVerified(handle, new TextEncoder().encode("final"));
    const finalText = await text();
    await root.removeEntry(name);
    return {
      ok: whileOpen === "old" && afterAbort === "old" && finalText === "final"
        && verified.state === SaveState.FILE_WRITTEN_VERIFIED,
      whileOpen,
      afterAbort,
    };
  },

  async changedFileIsNotOverwritten() {
    if (!navigator.storage?.getDirectory) return { ok: true, limited: "没有 OPFS" };
    let root;
    try {
      root = await navigator.storage.getDirectory();
    } catch (error) {
      return { ok: true, limited: `OPFS 不可用：${error.name}` };
    }
    const name = unique("changed");
    const handle = await root.getFileHandle(name, { create: true });
    if (!handle.createWritable) {
      await root.removeEntry(name);
      return { ok: true, limited: "没有 createWritable" };
    }
    const encoder = new TextEncoder();
    const opened = encoder.encode("opened");
    await writeFileVerified(handle, opened);
    const base = await sha256(opened);
    await writeFileVerified(handle, encoder.encode("changed-elsewhere"));
    const kind = await refused(writeFileVerified(handle, encoder.encode("ours"), { expectedSha256: base }));
    const text = await (await handle.getFile()).text();
    await root.removeEntry(name);
    return { ok: kind === "conflict" && text === "changed-elsewhere", kind };
  },

  async largeCommit() {
    const size = 16 * 1024 * 1024;
    const store = await CipherCache.open(unique("large"));
    const bytes = await grown(size, 1);
    const started = performance.now();
    await store.commit(bytes, 0);
    const committed = performance.now();
    const loaded = await store.load();
    const read = performance.now();
    store.close();
    return {
      ok: loaded.status === "ok" && loaded.bytes.byteLength === size,
      commitMs: Math.round(committed - started),
      loadMs: Math.round(read - committed),
    };
  },

  async storageFigures() {
    const estimate = await navigator.storage?.estimate?.().catch((error) => ({ error: error.name }));
    const persisted = await navigator.storage?.persisted?.().catch((error) => error.name);
    // Firefox 会弹窗问用户，等不到结果时如实记成未决定，而不是当成已授权。
    const persist = navigator.storage?.persist
      ? await within(navigator.storage.persist().catch((error) => error.name), 2000, "pending-prompt")
      : "unsupported";
    return { ok: true, quotaMiB: estimate?.quota && Math.round(estimate.quota / 1048576), persisted, persist };
  },
};

function frame() {
  return new Promise((resolve) => {
    const element = document.createElement("iframe");
    element.src = "frame.html";
    element.hidden = true;
    const listener = (event) => {
      if (event.source === element.contentWindow && event.data === "frame-ready") {
        removeEventListener("message", listener);
        resolve(element.contentWindow);
      }
    };
    addEventListener("message", listener);
    document.body.append(element);
  });
}

async function fillUntilQuota(capBytes) {
  const chunk = await grown(32 * 1024 * 1024, 1);
  let stored = 0;
  // 只保留两版的缓存撑不满配额，所以每次用新的库 ID 累积。
  const store = await CipherCache.open(unique("fill"));
  try {
    while (stored < capBytes) {
      store.vaultId = unique("fill");
      await store.commit(chunk, 0);
      stored += chunk.byteLength;
    }
    return { reached: false, storedMiB: stored / 1048576 };
  } catch (error) {
    return { reached: error.kind === "quota", kind: error.kind ?? String(error), storedMiB: stored / 1048576 };
  } finally {
    store.close();
  }
}

async function runProbes() {
  const results = {};
  for (const [name, probe] of Object.entries(probes)) {
    log.textContent += `${name}…\n`;
    try {
      results[name] = await probe();
    } catch (error) {
      results[name] = { ok: false, error: `${error?.name}: ${error?.message}` };
    }
  }
  return results;
}

function clearStorage() {
  return new Promise((resolve) => {
    const request = indexedDB.deleteDatabase("keex-cipher-cache");
    request.onsuccess = request.onerror = request.onblocked = () => resolve();
  });
}

// BFCache：解锁后离开再返回。每轮都从干净页面开始，否则刚跑完探针的页面可能因别的原因进不了缓存。
const STAGE_KEY = "keex-auto";
const BF_STAGES = ["withoutLock", "holdingWriterLock"];

function autoStage() {
  return JSON.parse(sessionStorage.getItem(STAGE_KEY) ?? "null");
}

function setAutoStage(value) {
  sessionStorage.setItem(STAGE_KEY, JSON.stringify(value));
}

async function nextBFStage(progress) {
  const [stage, ...pending] = progress.pending;
  if (!stage) {
    progress.probes.sessionDoesNotSurviveBFCache = {
      ok: Object.values(progress.bfcache).every((r) => !r.sessionStillUnlocked && r.writerReleased !== false),
    };
    await report(progress);
    return;
  }
  // load 之前跳转算替换当前历史记录，返回时会跳过这一页。
  if (document.readyState !== "complete") await new Promise((resolve) => addEventListener("load", resolve, { once: true }));
  await new Promise((resolve) => setTimeout(resolve, 100));
  setAutoStage({ ...progress, pending, current: stage });
  session.unlock();
  // 留住写锁对象：要看页面进了 BFCache 之后，它还占不占着锁。
  window.heldWriter = stage === "holdingWriterLock" ? await acquireWriter(unique("bf")) : null;
  location.href = "away.html";
}

function afterReturn(persisted) {
  const progress = autoStage();
  progress.bfcache[progress.current] = {
    restoredFromBFCache: persisted,
    // 恢复回来的页面还留着旧的 JS 堆；这里要确认会话已撤销。
    sessionStillUnlocked: session.unlocked,
    lockedBy: session.lockedBy,
  };
  // 只有真从 BFCache 恢复时才看得到旧对象；重新加载的页面已经没有这把锁了。
  if (persisted && window.heldWriter) progress.bfcache[progress.current].writerReleased = window.heldWriter.released;
  setAutoStage({ ...progress, current: null });
  location.reload();
}

async function report(progress) {
  const failed = Object.entries(progress.probes).filter(([, r]) => !r.ok).map(([name]) => name);
  await clearStorage();
  await fetch("/report", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label: progress.label, capabilities: capabilities(), probes: progress.probes, bfcache: progress.bfcache, failed }),
  });
  sessionStorage.removeItem(STAGE_KEY);
  log.textContent += failed.length ? `失败：${failed.join("、")}\n` : "全部完成，可以关闭此页。\n";
  document.title = "K071 完成";
}

addEventListener("pageshow", (event) => {
  if (event.persisted && autoStage()?.current) afterReturn(true);
});

async function start() {
  const params = new URLSearchParams(location.search);
  const progress = autoStage();
  if (progress?.current) {
    afterReturn(false);
    return;
  }
  if (progress) {
    await nextBFStage(progress);
    return;
  }
  if (!params.has("auto")) return;
  await clearStorage();
  const probes = await runProbes();
  const cap = Number(params.get("cap") ?? 0);
  if (cap) probes.fillToCap = { ok: true, ...(await fillUntilQuota(cap * 1048576)) };
  await clearStorage();
  setAutoStage({ label: params.get("auto"), probes, bfcache: {}, pending: BF_STAGES, current: null });
  location.reload();
}

window.lab = { ...cache, session, show, fixture, variant, grown, unique, refused, capabilities, probes, runProbes, fillUntilQuota, clearStorage };
document.documentElement.dataset.ready = "true";
start();
