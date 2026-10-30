// K071 被测实现：密文缓存、单写者、文件写回和保存状态。只处理合成数据，不是生产代码。
//
// 新版本和版本指针写在同一个 IndexedDB 事务里，条件检查也在这个事务里做：要么全成功，要么
// 旧版本原样留着。这样不用自己写两阶段提交和孤儿清理。OPFS 做不到跨文件原子提交，所以不用它存版本。

const DB_NAME = "keex-cipher-cache";
const VERSIONS = "versions";
const HEADS = "heads";
const MAGIC = [0x03, 0xd9, 0xa2, 0x9a, 0x67, 0xfb, 0x4b, 0xb5];

/** ADR-0007 §4 的保存状态。界面只能按这里的含义说话：下载发起不等于文件已保存。 */
export const SaveState = Object.freeze({
  MEMORY_ONLY: "memory-only",
  CACHE_COMMITTED: "cache-committed",
  DOWNLOAD_INITIATED: "download-initiated",
  FILE_WRITTEN_VERIFIED: "file-written-verified",
});

export const SaveStateText = Object.freeze({
  [SaveState.MEMORY_ONLY]: "只在内存里，尚未保存",
  [SaveState.CACHE_COMMITTED]: "此浏览器的缓存已提交（不是备份，也没有写回原文件）",
  [SaveState.DOWNLOAD_INITIATED]: "已交给浏览器下载（原文件未改动，请确认下载结果）",
  [SaveState.FILE_WRITTEN_VERIFIED]: "文件已写入并读回核对",
});

export class CacheError extends Error {
  /** @param {"conflict"|"evicted"|"quota"|"verify"|"invalid"|"unavailable"} kind */
  constructor(kind, message, cause) {
    super(message, { cause });
    this.name = "CacheError";
    this.kind = kind;
  }
}

export async function sha256(bytes) {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** 只认 KDBX 文件头；KDBX 4 还核对头部的 SHA-256，没有密钥也能发现截断和损坏。 */
export async function assertKdbx(bytes) {
  const view = new Uint8Array(bytes);
  if (view.length < 12 || !MAGIC.every((b, i) => view[i] === b)) {
    throw new CacheError("invalid", "不是 KDBX 文件");
  }
  const data = new DataView(view.buffer, view.byteOffset, view.byteLength);
  const major = data.getUint16(10, true);
  if (major < 4) return;
  let position = 12;
  while (true) {
    if (position + 5 > view.length) throw new CacheError("invalid", "KDBX 头部被截断");
    const id = view[position];
    const size = data.getUint32(position + 1, true);
    position += 5 + size;
    if (id === 0) break;
  }
  if (position + 32 > view.length) throw new CacheError("invalid", "KDBX 头部被截断");
  const actual = await sha256(view.subarray(0, position));
  const expected = [...view.subarray(position, position + 32)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
  if (actual !== expected) throw new CacheError("invalid", "KDBX 头部校验失败");
}

function requestResult(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function transactionDone(transaction) {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onabort = () => reject(transaction.error);
    transaction.onerror = () => reject(transaction.error);
  });
}

function isQuota(error) {
  return error?.name === "QuotaExceededError";
}

export class CipherCache {
  static async open(vaultId) {
    let database;
    try {
      database = await new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, 1);
        request.onupgradeneeded = () => {
          request.result.createObjectStore(VERSIONS, { keyPath: "id" });
          request.result.createObjectStore(HEADS, { keyPath: "vaultId" });
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
    } catch (error) {
      throw new CacheError("unavailable", "浏览器存储不可用", error);
    }
    return new CipherCache(vaultId, database);
  }

  constructor(vaultId, database) {
    this.vaultId = vaultId;
    this.database = database;
  }

  close() {
    this.database.close();
  }

  async generation() {
    const transaction = this.database.transaction(HEADS);
    const head = await requestResult(transaction.objectStore(HEADS).get(this.vaultId));
    return head?.generation ?? 0;
  }

  /**
   * 只有缓存还停在 baseGeneration 时才提交。保留当前和上一版，读回核对通过才算成功。
   * 基线是第 N 版、缓存却是空的，说明被驱逐或清理过，不能当成新库重新开始。
   */
  async commit(bytes, baseGeneration) {
    await assertKdbx(bytes);
    const digest = await sha256(bytes);
    let transaction;
    try {
      // Safari 忽略 durability，选项本身不报错；是否真落盘由崩溃场景实测。
      transaction = this.database.transaction([VERSIONS, HEADS], "readwrite", { durability: "strict" });
    } catch (error) {
      // Firefox 磁盘写满后会强制关掉连接，之后每次调用都是 InvalidStateError。
      throw new CacheError("unavailable", "缓存连接已失效，需要重新打开", error);
    }
    const done = transactionDone(transaction);
    const versions = transaction.objectStore(VERSIONS);
    const heads = transaction.objectStore(HEADS);
    let refusal = null;
    let generation = 0;
    try {
      const head = await requestResult(heads.get(this.vaultId));
      const current = head?.generation ?? 0;
      if (current !== baseGeneration) {
        refusal =
          current === 0
            ? new CacheError("evicted", `基线是第 ${baseGeneration} 版，缓存已是空的`)
            : new CacheError("conflict", `基线第 ${baseGeneration} 版，缓存已是第 ${current} 版`);
        transaction.abort();
      } else {
        generation = current + 1;
        const id = `${this.vaultId}:${generation}`;
        versions.put({ id, bytes: bytes.slice(0), sha256: digest });
        if (head?.previous) versions.delete(head.previous);
        heads.put({ vaultId: this.vaultId, generation, current: id, previous: head?.current ?? null });
      }
    } catch (error) {
      // 事务已自行中止时这里也会抛错；等 done 给出的原因更准，这个只作兜底。
      if (!isQuota(error)) refusal ??= new CacheError("unavailable", "缓存事务失败", error);
    }
    try {
      await done;
    } catch (error) {
      if (refusal) throw refusal;
      if (isQuota(error)) throw new CacheError("quota", "浏览器存储配额不足", error);
      throw new CacheError("unavailable", "缓存事务失败", error);
    }
    if (refusal) throw refusal;
    const check = await this.load().catch((error) => {
      throw new CacheError("verify", "提交后读回失败", error);
    });
    if (check.status !== "ok" || check.generation !== generation) {
      throw new CacheError("verify", "提交后读回核对失败");
    }
    return { state: SaveState.CACHE_COMMITTED, generation, sha256: digest };
  }

  /** 损坏时不自动退回上一版：把两版都交给调用方，由界面明确告诉用户。 */
  async load() {
    const transaction = this.database.transaction([VERSIONS, HEADS]);
    const versions = transaction.objectStore(VERSIONS);
    const head = await requestResult(transaction.objectStore(HEADS).get(this.vaultId));
    if (!head) return { status: "empty", generation: 0 };
    const [current, previous] = await Promise.all([
      requestResult(versions.get(head.current)),
      head.previous ? requestResult(versions.get(head.previous)) : null,
    ]);
    if (current && (await sha256(current.bytes)) === current.sha256) {
      return { status: "ok", generation: head.generation, bytes: current.bytes, previous: head.previous };
    }
    const intact = previous && (await sha256(previous.bytes)) === previous.sha256;
    return { status: "corrupt", generation: head.generation, previousBytes: intact ? previous.bytes : null };
  }
}

/**
 * 申请这个库的写权限并一直持有到 release。别的标签持有时返回 busy。
 * 浏览器没有 Web Locks 时返回 unsupported，调用方必须只读，不能退化成最后写入获胜。
 *
 * 离开页面就释放：页面进了 BFCache 后还占着锁的话，别的标签能不能拿到要看浏览器（Chromium 会
 * 驱逐缓存页，别的没测到），不赌这个。页面恢复回来后 released 为 true，要重新申请。
 */
export function acquireWriter(vaultId) {
  if (!navigator.locks) return Promise.resolve({ status: "unsupported" });
  return new Promise((resolve, reject) => {
    navigator.locks
      .request(`keex-writer:${vaultId}`, { ifAvailable: true }, (lock) => {
        if (!lock) {
          resolve({ status: "busy" });
          return undefined;
        }
        return new Promise((free) => {
          const writer = {
            status: "writer",
            released: false,
            release() {
              writer.released = true;
              removeEventListener("pagehide", writer.release);
              free();
            },
          };
          addEventListener("pagehide", writer.release);
          resolve(writer);
        });
      })
      .catch(reject);
  });
}

/**
 * 写入并读回核对。createWritable 写的是临时文件，close 才替换；中途失败原文件不变。
 * 本地文件系统没有条件提交：expectedSha256 只能发现打开之后别的程序改过文件，
 * 核对和替换之间仍有很短的窗口，所以这不等于远端的版本条件。
 */
export async function writeFileVerified(handle, bytes, { expectedSha256 } = {}) {
  if (expectedSha256) {
    const current = await (await handle.getFile()).arrayBuffer();
    if ((await sha256(current)) !== expectedSha256) {
      throw new CacheError("conflict", "文件在打开之后被别的程序改过");
    }
  }
  const expected = await sha256(bytes);
  const writable = await handle.createWritable();
  try {
    await writable.write(bytes);
    await writable.close();
  } catch (error) {
    await writable.abort().catch(() => {});
    throw error;
  }
  const written = await (await handle.getFile()).arrayBuffer();
  if ((await sha256(written)) !== expected) throw new CacheError("verify", "写入后读回不一致");
  return { state: SaveState.FILE_WRITTEN_VERIFIED, sha256: expected };
}

/** 只能发起下载：页面无从得知用户是否取消、文件存到了哪里。 */
export function offerDownload(bytes, name) {
  const url = URL.createObjectURL(new Blob([bytes], { type: "application/octet-stream" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
  return { state: SaveState.DOWNLOAD_INITIATED };
}

/**
 * 模拟解锁后的会话。离开页面就撤销，BFCache 恢复回来也不复活；
 * 内存里那份占位数据代表解密后的内容，真实实现由 K081 负责。
 */
export class Session {
  constructor() {
    this.epoch = 0;
    this.unlocked = false;
    this.lockedBy = null;
    addEventListener("pagehide", () => this.lock("pagehide"));
  }

  unlock() {
    this.unlocked = true;
    this.epoch += 1;
    this.lockedBy = null;
  }

  lock(reason) {
    this.unlocked = false;
    this.epoch += 1;
    this.lockedBy = reason;
  }
}
