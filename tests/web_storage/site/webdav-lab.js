// K072 探针页：同样能自己跑完并上报，Safari 不用驱动也能测。
import { sha256 } from "./cipher-cache.js";
import { REMOTE_COMMITTED, RemoteError, WebDavFile } from "./webdav-client.js";

const log = document.querySelector("#log");
const say = (text) => { log.textContent += `${text}\n`; };

const fixture = await (await fetch("/fixture.kdbx")).arrayBuffer();

/** 第 n 版：头部不变，只改末尾。 */
function version(n, size = fixture.byteLength) {
  const bytes = new Uint8Array(size);
  const words = new Uint32Array(bytes.buffer, 0, size >>> 2);
  let x = (n * 2654435761 + 1) >>> 0;
  for (let i = 0; i < words.length; i += 1) {
    x ^= x << 13;
    x ^= x >>> 17;
    x ^= x << 5;
    words[i] = x;
  }
  bytes.set(new Uint8Array(fixture));
  new DataView(bytes.buffer).setUint32(fixture.byteLength - 4, n);
  return bytes.buffer;
}

/** 把结果归成一个词：成功值原样返回，失败只留错误类别。 */
const outcome = (promise) => promise.then(
  (value) => value,
  (error) => ({ failed: error instanceof RemoteError ? error.kind : error.name }),
);

const unique = (prefix) => `${prefix}-${crypto.randomUUID()}.kdbx`;

function badCredentials(url) {
  return new WebDavFile({ url, authorization: `Basic ${btoa(`synthetic-user:${crypto.randomUUID()}`)}` });
}

/** 真实服务器：完整走一遍条件提交和反例。 */
async function realServer(target) {
  const { base, authorization } = target;
  const url = `${base}/${unique("vault")}`;
  const open = (address = url) => new WebDavFile({ url: address, authorization });
  const a = open();
  const b = open();
  const result = {};

  result.capabilities = await outcome(a.probe(version(1)));
  await outcome(b.probe(version(1)));
  result.atomicMove = await a.probeAtomicMove(version(1));
  const trusted = result.capabilities.safe === true;
  if (result.capabilities.failed) return { ...result, ok: false };
  // 探针判定不安全的服务器也往下走一遍，实测这个判定是不是冤枉了它。正常客户端到这里就只写冲突副本。
  if (!trusted) {
    a.capabilities = { safe: true };
    b.capabilities = { safe: true };
  }

  say("  创建");
  result.create = (await outcome(a.create(version(1)))).state ?? "failed";
  result.createAgain = (await outcome(b.create(version(2)))).failed ?? "overwrote";

  const baseA = await a.read();
  const baseB = await b.read();
  const committed = await outcome(b.replace(version(2), baseB.etag));
  result.replace = committed.state ?? committed.failed;
  // A 还拿着旧基线：这就是 M07 的“A 开始 → B 提交 → A 完成”。
  result.staleReplace = (await outcome(a.replace(version(3), baseA.etag))).failed ?? "overwrote";
  const afterRace = await a.read();
  result.remoteKeptB = afterRace.sha256 === await sha256(version(2));
  const copy = await outcome(a.writeConflictCopy(version(3)));
  result.conflictCopy = copy.url
    ? (await open(copy.url).read()).sha256 === await sha256(version(3))
    : copy.failed;
  result.mainUntouchedByCopy = (await a.read()).sha256 === await sha256(version(2));

  say("  错误密码");
  result.badCredentials = (await outcome(badCredentials(url).read())).failed ?? "accepted";
  result.noCredentials = (await outcome(new WebDavFile({ url }).read())).failed ?? "accepted";

  // PROPFIND 的预检、Depth 头和响应都要在浏览器里实际走通。
  const propfind = await outcome(a.request("PROPFIND", url, {
    headers: { Depth: "0", "Content-Type": "application/xml" },
    body: '<?xml version="1.0"?><D:propfind xmlns:D="DAV:"><D:prop><D:getetag/></D:prop></D:propfind>',
  }));
  if (propfind.failed) {
    result.propfind = propfind.failed;
  } else {
    const text = await propfind.text();
    const etag = new DOMParser().parseFromString(text, "application/xml").getElementsByTagNameNS("DAV:", "getetag")[0]?.textContent;
    result.propfind = { status: propfind.status, sameEtag: etag === afterRace.etag };
  }

  await outcome(a.request("DELETE", url));
  if (target.expectUnsafe) {
    result.ok = result.capabilities.safe === false && result.capabilities[target.expectUnsafe] === false;
    return result;
  }
  result.ok = result.capabilities.safe === true && result.create === REMOTE_COMMITTED
    && result.createAgain === "conflict" && result.replace === REMOTE_COMMITTED
    && result.staleReplace === "conflict" && result.remoteKeptB && result.conflictCopy === true
    && result.mainUntouchedByCopy && result.badCredentials === "auth" && result.noCredentials === "auth";
  return result;
}

/** 每种坏服务器的预期：连接、读取、替换各得到什么。替换后目标文件都不能被盖掉，除非服务器确实可靠。 */
const EXPECT = {
  strict: { safe: true, read: "ok", attempt: REMOTE_COMMITTED },
  "no-cors": { connect: "unreachable", read: "unreachable", attempt: "unsafe-server" },
  // 规范说 Allow-Headers 的 * 不包含 Authorization，各浏览器实际不一样，这里只记录。
  // 不管哪种结果都不能破坏数据：连得上时条件语义是好的，连不上时写不进去。
  wildcard: { varies: true },
  "no-expose": { safe: false, read: "ok", attempt: "unsafe-server", missing: "readableEtag" },
  "no-etag": { safe: false, read: "ok", attempt: "unsafe-server", missing: "readableEtag" },
  "weak-etag": { safe: false, read: "ok", attempt: "unsafe-server", missing: "strongEtag" },
  "second-mtime": { safe: false, read: "ok", attempt: "unsafe-server", missing: "etagChanges" },
  "ignore-conditions": { safe: false, read: "ok", attempt: "unsafe-server", missing: "createGuard" },
  "html-login": { read: "not-kdbx", attempt: "unsafe-server" },
  // 临时对象不跳转，所以探针能过；目标文件一跳转就拒绝，读写都不跟随。
  "cross-redirect": { read: "redirect", attempt: "redirect" },
  "same-origin-redirect": { read: "redirect", attempt: "redirect" },
  cacheable: { safe: true, read: "ok", attempt: REMOTE_COMMITTED },
  // 连接在响应前断开，客户端不知道写没写：必须读回来判断，不能猜。
  "write-then-drop": { safe: true, read: "ok", attempt: REMOTE_COMMITTED },
  "drop-before-write": { safe: true, read: "ok", attempt: "not-committed" },
  "truncate-then-drop": { safe: true, read: "ok", attempt: "changed-or-torn", remoteAfter: "别的内容" },
  "truncate-header-then-drop": { safe: true, read: "ok", attempt: "torn", remoteAfter: "读不到" },
  "status-403": { connect: "forbidden", read: "ok", attempt: "unsafe-server" },
  "status-423": { connect: "locked", read: "ok", attempt: "unsafe-server" },
  "status-429": { connect: "rate-limited", read: "ok", attempt: "unsafe-server" },
  "status-507": { connect: "storage-full", read: "ok", attempt: "unsafe-server" },
  "status-500": { connect: "server", read: "ok", attempt: "unsafe-server" },
};

async function scriptedServer({ mode, url, authorization, seedSha256 }) {
  const file = new WebDavFile({ url, authorization });
  const expected = EXPECT[mode];
  const result = { mode };
  const connected = await outcome(file.probe(version(1)));
  result.connect = connected.failed ?? "ok";
  result.safe = connected.safe ?? null;
  const read = await outcome(file.read());
  result.read = read.failed ?? "ok";
  const attempt = await outcome(file.replace(version(2), read.etag ?? '"none"'));
  result.attempt = attempt.state ?? attempt.failed;

  // 被拒绝的话，目标必须还是种子内容：这才是“不覆盖”。可靠服务器上才会变成新版本。
  let remote = "读不到";
  const after = await outcome(file.read());
  if (!after.failed) {
    remote = after.sha256 === seedSha256 ? "没变" : after.sha256 === await sha256(version(2)) ? "新版" : "别的内容";
  }
  result.remote = remote;
  if (result.safe === false) {
    const copy = await outcome(file.writeConflictCopy(version(2)));
    result.conflictCopy = Boolean(copy.url) || copy.failed;
  }

  if (expected.varies) {
    result.ok = remote === "新版" || remote === "读不到";
    return result;
  }
  const fine = [
    expected.safe === undefined || result.safe === expected.safe,
    expected.connect === undefined || result.connect === expected.connect,
    result.read === expected.read,
    result.attempt === expected.attempt,
    expected.missing === undefined || connected[expected.missing] === false,
    expected.remoteAfter ? remote === expected.remoteAfter
      : expected.attempt === REMOTE_COMMITTED ? remote === "新版" : remote === "没变" || remote === "读不到",
    result.safe !== false || result.conflictCopy === true,
  ];
  result.ok = fine.every(Boolean);
  return result;
}

async function cspBlocked({ url, authorization }) {
  const violation = new Promise((resolve) => {
    addEventListener("securitypolicyviolation", (event) => resolve(event.blockedURI), { once: true });
    setTimeout(() => resolve(null), 2000);
  });
  const read = await outcome(new WebDavFile({ url, authorization }).read());
  const blockedURI = await violation;
  // CORS 和 CSP 在 fetch 里是同一个错误；只有这个事件能告诉用户“是部署没放行这个地址”。
  return { ok: read.failed === "unreachable" && Boolean(blockedURI), read: read.failed, reported: Boolean(blockedURI) };
}

function plainHttpRefused() {
  const results = ["http://nas.example/vault.kdbx", "http://nas.example:8080/vault.kdbx"].map((url) => {
    try {
      new WebDavFile({ url });
      return "accepted";
    } catch (error) {
      return error.kind;
    }
  });
  return { ok: results.every((r) => r === "insecure"), results };
}

async function secretsNotPersisted() {
  const databases = await indexedDB.databases?.() ?? [];
  const stored = [...Object.keys(localStorage), ...Object.keys(sessionStorage), ...databases.map((d) => d.name)];
  const caches_ = await caches.keys();
  return { ok: stored.length === 0 && caches_.length === 0, stored, caches: caches_ };
}

async function run(label) {
  const config = await (await fetch("/webdav-config.json")).json();
  const targets = {};
  const results = { plainHttpRefused: plainHttpRefused() };
  for (const target of config.real) {
    say(`真实服务器 ${target.name}…`);
    targets[target.name] = await realServer(target).catch((error) => ({ ok: false, error: `${error.name}: ${error.message}` }));
  }
  for (const target of config.scripted) {
    say(`脚本服务器 ${target.mode}…`);
    targets[target.mode] = await scriptedServer(target).catch((error) => ({ ok: false, error: `${error.name}: ${error.message}` }));
  }
  say("CSP…");
  results.cspBlocked = await cspBlocked(config.cspBlocked);
  const { leaks } = await (await fetch("/webdav-leaks.json")).json();
  // 跳转目标不能收到任何请求；收到了也绝不能带认证头。
  results.noCredentialLeak = { ok: leaks.length === 0, requests: leaks.length, withAuthorization: leaks.filter((l) => l.authorization).length };
  results.secretsNotPersisted = await secretsNotPersisted();
  const failed = [
    ...Object.entries(targets).filter(([, r]) => !r.ok).map(([name]) => name),
    ...Object.entries(results).filter(([, r]) => !r.ok).map(([name]) => name),
  ];
  await fetch("/report", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label, userAgent: navigator.userAgent, targets, results, failed }),
  });
  say(failed.length ? `失败：${failed.join("、")}` : "全部完成，可以关闭此页。");
  document.title = "K072 完成";
}

const label = new URLSearchParams(location.search).get("auto");
if (label) run(label);
