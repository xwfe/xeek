// K072 被测实现：浏览器里的 WebDAV 条件提交。只处理合成数据，不是生产代码。
//
// 服务器说支持什么不算数：先在临时对象上实测条件语义，没通过就不走自动覆盖，只写冲突副本。
// 每个请求都不带 cookie、不自动跟随跳转，认证头只发给配置的这个源。
import { CacheError, assertKdbx, sha256 } from "./cipher-cache.js";

/** ADR-0007 §4 的“远端条件提交确认”：只说明这一版被远端接受，不说明此后的本机修改也已同步。 */
export const REMOTE_COMMITTED = "remote-committed";

export class RemoteError extends Error {
  /**
   * @param {"unreachable"|"redirect"|"auth"|"forbidden"|"missing"|"conflict"|"locked"|"rate-limited"
   *   |"storage-full"|"not-kdbx"|"too-large"|"unsafe-server"|"insecure"|"weak-etag"|"no-etag"
   *   |"torn"|"changed-or-torn"|"unknown-outcome"|"server"} kind
   */
  constructor(kind, message, status) {
    super(message);
    this.name = "RemoteError";
    this.kind = kind;
    this.status = status;
  }
}

const STATUS_KINDS = { 401: "auth", 403: "forbidden", 404: "missing", 412: "conflict", 423: "locked", 429: "rate-limited", 507: "storage-full" };
const MAX_BYTES = 256 * 1024 * 1024;
const LOOPBACK = new Set(["127.0.0.1", "localhost", "[::1]"]);

function kindOf(status) {
  return STATUS_KINDS[status] ?? "server";
}

/** 只有 `"..."` 形式才是强校验器；`W/` 前缀和缺失都不能用来判断“还是同一版”。 */
function strongEtag(response) {
  const etag = response.headers.get("ETag");
  if (!etag) return { kind: "no-etag" };
  return /^"[^"]*"$/.test(etag) ? { etag } : { kind: "weak-etag" };
}

export class WebDavFile {
  /** @param {{url: string, authorization?: string}} options */
  constructor({ url, authorization }) {
    const parsed = new URL(url);
    // 禁止 HTTP 降级：明文 HTTP 只接受本机，给测试和本机服务用。
    if (parsed.protocol !== "https:" && !LOOPBACK.has(parsed.hostname)) {
      throw new RemoteError("insecure", "同步地址必须是 HTTPS");
    }
    this.url = parsed.href;
    this.authorization = authorization;
    this.capabilities = null;
  }

  async request(method, url, { headers = {}, body, signal } = {}) {
    let response;
    try {
      response = await fetch(url, {
        method,
        body,
        signal,
        headers: { ...(this.authorization ? { Authorization: this.authorization } : {}), ...headers },
        // 不带 cookie，也不用浏览器记住的账号；条件请求不能被 HTTP 缓存回答。
        credentials: "omit",
        cache: "no-store",
        // 跟随跳转可能把请求发到别的源。opaqueredirect 看不到目标，直接拒绝。
        redirect: "manual",
      });
    } catch (error) {
      if (error.name === "AbortError") throw error;
      // CORS、断网、证书、CSP 在这里都是同一个 TypeError，页面分不清；CSP 另有事件可查。
      throw new RemoteError("unreachable", "连不上同步服务，可能是网络或服务没有允许此网页访问");
    }
    if (response.type === "opaqueredirect" || (response.status >= 300 && response.status < 400)) {
      throw new RemoteError("redirect", "同步服务要求跳转，不跟随");
    }
    return response;
  }

  /**
   * Apache 对 1 秒内改过的文件只给弱 ETag，过了这一秒才变强，所以遇到弱的再等一次。
   * 一直是弱的才算服务器不合格。
   */
  async settledGet(url) {
    const response = await this.request("GET", url);
    if (response.ok && strongEtag(response).kind === "weak-etag") {
      await response.arrayBuffer();
      await new Promise((resolve) => setTimeout(resolve, 1100));
      return this.request("GET", url);
    }
    return response;
  }

  /** 读当前版本。内容必须是 KDBX：错误的 HTML 登录页也可能是 200。 */
  async read() {
    const response = await this.settledGet(this.url);
    if (!response.ok) throw new RemoteError(kindOf(response.status), `读取失败：${response.status}`, response.status);
    const declared = Number(response.headers.get("Content-Length") ?? 0);
    if (declared > MAX_BYTES) throw new RemoteError("too-large", "文件超过大小上限");
    const bytes = await response.arrayBuffer();
    if (bytes.byteLength > MAX_BYTES) throw new RemoteError("too-large", "文件超过大小上限");
    try {
      await assertKdbx(bytes);
    } catch (error) {
      if (error instanceof CacheError) throw new RemoteError("not-kdbx", "远端内容不是 KDBX 文件");
      throw error;
    }
    const version = strongEtag(response);
    return { bytes, etag: version.etag ?? null, etagProblem: version.kind ?? null, sha256: await sha256(bytes) };
  }

  /**
   * 在同目录的临时对象上实测条件语义，不碰目标文件。ADR-0003 §2 的能力报告：
   * 强版本标识、创建防覆盖、最终替换条件，以及内容变了版本标识是否一定变。
   */
  async probe(payload) {
    const scratch = new URL(`keex-probe-${crypto.randomUUID()}.tmp`, this.url).href;
    const report = { readableEtag: false, strongEtag: false, createGuard: false, replaceGuard: false, etagChanges: false };
    const put = (body, headers) => this.request("PUT", scratch, { body, headers });
    try {
      const created = await put(payload, { "If-None-Match": "*" });
      if (!created.ok) throw new RemoteError(kindOf(created.status), `无法创建临时对象：${created.status}`, created.status);
      const first = await this.settledGet(scratch);
      const version = strongEtag(first);
      report.readableEtag = version.kind !== "no-etag";
      report.strongEtag = Boolean(version.etag);
      await first.arrayBuffer();
      if (!version.etag) return this.remember(report);

      report.createGuard = (await put(payload, { "If-None-Match": "*" })).status === 412;
      report.replaceGuard = (await put(payload, { "If-Match": '"keex-stale-version"' })).status === 412;
      // 同样大小、紧接着写：只靠“修改时间到秒 + 大小”算 ETag 的服务器，版本不会变，
      // 这时条件提交防不住丢失更新。连写三次，免得恰好跨秒时漏判。
      let current = version.etag;
      report.etagChanges = true;
      for (let round = 0; round < 3 && report.etagChanges; round += 1) {
        const same = new Uint8Array(payload.slice(0));
        same[same.length - 1] ^= round + 1;
        const changed = await put(same, { "If-Match": current });
        const after = await this.settledGet(scratch);
        await after.arrayBuffer();
        const next = strongEtag(after).etag;
        report.etagChanges = changed.ok && next !== undefined && next !== current;
        current = next;
      }
      return this.remember(report);
    } finally {
      await this.request("DELETE", scratch).catch(() => {});
    }
  }

  remember(report) {
    this.capabilities = { ...report, safe: Object.values(report).every(Boolean) };
    return this.capabilities;
  }

  assertSafe() {
    if (!this.capabilities?.safe) throw new RemoteError("unsafe-server", "这个服务的条件写入没有实测通过，不做自动覆盖");
  }

  /** 首次创建：目标已存在时不覆盖。 */
  async create(bytes) {
    this.assertSafe();
    return this.commit(bytes, { "If-None-Match": "*" });
  }

  /** 只有远端还停在 baseEtag 这一版时才替换。收到 412 保留双方，不自动重试。 */
  async replace(bytes, baseEtag, { signal } = {}) {
    this.assertSafe();
    return this.commit(bytes, { "If-Match": baseEtag }, { signal, baseEtag });
  }

  async commit(bytes, headers, { signal, baseEtag } = {}) {
    const expected = await sha256(bytes);
    let response;
    try {
      response = await this.request("PUT", this.url, { body: bytes, headers, signal });
    } catch (error) {
      if (error.kind !== "unreachable" && error.name !== "AbortError") throw error;
      // 请求发出去后断了，服务器可能已经写完，也可能写了一半：不猜，读回来看。
      return this.settleUnknown(expected, baseEtag);
    }
    if (!response.ok) throw new RemoteError(kindOf(response.status), `提交失败：${response.status}`, response.status);
    const check = await this.read();
    if (check.sha256 !== expected) throw new RemoteError("conflict", "提交后远端内容不是这一版");
    return { state: REMOTE_COMMITTED, etag: check.etag, sha256: expected };
  }

  async settleUnknown(expected, baseEtag) {
    let check;
    try {
      check = await this.read();
    } catch (error) {
      if (error.kind === "missing" && !baseEtag) return { state: "not-committed" };
      if (error.kind === "not-kdbx") throw new RemoteError("torn", "上传中断后远端文件已损坏，本地副本要保留");
      throw new RemoteError("unknown-outcome", "上传中断，读不到远端结果");
    }
    if (check.sha256 === expected) return { state: REMOTE_COMMITTED, etag: check.etag, sha256: expected };
    if (check.etag === baseEtag) return { state: "not-committed", etag: check.etag };
    // 截断的 KDBX 头部还是完整的，没有密钥分不清是别人的新版本还是写坏了。两种都要保留本地副本。
    throw new RemoteError("changed-or-torn", "上传中断后远端变了：可能是别人写的，也可能被截断");
  }

  /**
   * 实测“先传临时文件、再条件改名”这条路：改名在服务器上是原子的，上传中断碰不到目标文件。
   * 只是记录能力；MOVE 还要求部署方在 CORS 里放开 MOVE、Destination、If、Overwrite。
   */
  async probeAtomicMove(payload) {
    const target = new URL(`keex-move-${crypto.randomUUID()}.tmp`, this.url).href;
    const temporary = new URL(`keex-move-${crypto.randomUUID()}.tmp`, this.url).href;
    const report = { staleRefused: false, moved: false };
    try {
      await this.request("PUT", target, { body: payload, headers: { "If-None-Match": "*" } });
      const current = await this.request("GET", target);
      await current.arrayBuffer();
      const etag = current.headers.get("ETag");
      await this.request("PUT", temporary, { body: payload, headers: { "If-None-Match": "*" } });
      const move = (tag) => this.request("MOVE", temporary, {
        headers: { Destination: target, Overwrite: "T", If: `<${target}> ([${tag}])` },
      });
      report.staleStatus = (await move('"keex-stale-version"')).status;
      report.staleRefused = report.staleStatus === 412;
      report.movedStatus = (await move(etag)).status;
      report.moved = report.movedStatus >= 200 && report.movedStatus < 300;
    } catch (error) {
      report.error = error.kind ?? error.name;
    } finally {
      await this.request("DELETE", target).catch(() => {});
      await this.request("DELETE", temporary).catch(() => {});
    }
    return report;
  }

  /**
   * 不能安全覆盖或发生冲突时的退路：写一份新名字的副本，绝不碰原文件。
   * 名字带随机数，就算服务器忽略 If-None-Match 也不会撞上已有文件。
   */
  async writeConflictCopy(bytes) {
    const name = new URL(this.url).pathname.split("/").pop();
    const url = new URL(`${name}.keex-conflict-${crypto.randomUUID()}.kdbx`, this.url).href;
    const response = await this.request("PUT", url, { body: bytes, headers: { "If-None-Match": "*" } });
    if (!response.ok) throw new RemoteError(kindOf(response.status), `写冲突副本失败：${response.status}`, response.status);
    return { url };
  }
}
