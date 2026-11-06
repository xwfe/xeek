// K070 探针页：同样能自己跑完并上报。输出的库传回本机，由独立 oracle 和 KeePassXC 核对。
const log = document.querySelector("#log");
const say = (text) => { log.textContent += `${text}\n`; };
const MiB = 1024 * 1024;

class Core {
  static async start(suffix = "") {
    const worker = new Worker(`kdbx-worker.js${suffix}`, { type: "module" });
    const core = new Core(worker);
    await new Promise((resolve, reject) => {
      worker.addEventListener("message", function ready({ data }) {
        if (data.ready) {
          worker.removeEventListener("message", ready);
          resolve();
        }
      });
      worker.addEventListener("error", (event) => reject(new Error(event.message || "Worker 加载失败")));
    });
    return core;
  }

  constructor(worker) {
    this.worker = worker;
    this.pending = new Map();
    this.next = 0;
    worker.addEventListener("message", ({ data }) => {
      if (data.ready) return;
      this.pending.get(data.id)?.(data);
      this.pending.delete(data.id);
    });
  }

  call(op, args) {
    const id = (this.next += 1);
    return new Promise((resolve) => {
      this.pending.set(id, resolve);
      const transfer = args?.bytes ? [args.bytes] : [];
      this.worker.postMessage({ id, op, args }, transfer);
    });
  }

  stop() {
    this.worker.terminate();
  }
}

const samples = new Map();
async function sampleBytes(file) {
  if (!samples.has(file)) samples.set(file, await (await fetch(`/sample?file=${encodeURIComponent(file)}`)).arrayBuffer());
  return samples.get(file).slice(0);
}

async function upload(name, bytes) {
  await fetch(`/upload?name=${encodeURIComponent(name)}`, { method: "POST", body: bytes });
}

const label = new URLSearchParams(location.search).get("auto");

function brief(reply) {
  return reply.ok
    ? { ok: true, ms: Math.round(reply.ms), memoryMiB: Math.round(reply.memoryBytes / MiB) }
    : { ok: false, name: reply.name, message: reply.message?.slice(0, 160), trapped: reply.trapped, ms: Math.round(reply.ms), memoryMiB: Math.round(reply.memoryBytes / MiB) };
}

/** 开着 KDF 的同时看主线程有多卡：定时器之间最长隔了多久。 */
function watchMainThread() {
  let last = performance.now();
  let worst = 0;
  const timer = setInterval(() => {
    const now = performance.now();
    worst = Math.max(worst, now - last);
    last = now;
  }, 10);
  return () => {
    clearInterval(timer);
    return Math.round(worst);
  };
}

const probes = {
  async cspRequiresWasmUnsafeEval() {
    // 同一个 Worker，响应头里没有 'wasm-unsafe-eval' 时不能编译。这是唯一需要放开的指令，不需要 'unsafe-eval'。
    const strict = await Core.start("?no-wasm-csp").then(async (core) => {
      const reply = await core.call("status");
      core.stop();
      return reply.value;
    }).catch((error) => ({ loaded: false, failure: error.message }));
    const normal = await Core.start();
    const reply = await normal.call("status");
    normal.stop();
    return {
      ok: !strict.loaded && reply.value.loaded,
      withoutDirective: strict.failure?.slice(0, 160),
      instantiateMs: Math.round(reply.value.instantiateMs),
    };
  },

  async roundTrips({ roundTrips }) {
    const results = {};
    for (const sample of roundTrips) {
      say(`  往返 ${sample.name}`);
      const core = await Core.start();
      const opened = await core.call("open", { bytes: await sampleBytes(sample.file), password: sample.password });
      if (!opened.ok) {
        results[sample.name] = { ok: false, open: brief(opened) };
        core.stop();
        continue;
      }
      const edited = await core.call("setUsername", { entry: opened.value.target, username: "synthetic-browser-edit" });
      const saved = await core.call("save", { password: sample.password });
      if (saved.ok) await upload(`${label}--${sample.name}.kdbx`, saved.value);
      results[sample.name] = {
        ok: edited.ok && saved.ok,
        target: opened.value.target,
        summary: opened.value,
        open: brief(opened),
        save: brief(saved),
      };
      core.stop();
    }
    return { ok: Object.values(results).every((r) => r.ok), results };
  },

  async readsEveryRegisteredSample({ allSamples }) {
    const core = await Core.start();
    const results = [];
    for (const sample of allSamples) {
      const keyfile = sample.keyfile ? await sampleBytes(sample.keyfile) : undefined;
      const opened = await core.call("open", { bytes: await sampleBytes(sample.file), password: sample.password ?? "", keyfile });
      results.push({
        file: sample.file,
        ok: opened.ok,
        entries: opened.value?.entries,
        history: opened.value?.history,
        attachments: opened.value?.attachments,
        unknown: opened.value?.unknownContent?.length,
        ms: Math.round(opened.ms),
        error: opened.ok ? undefined : opened.message?.slice(0, 120),
      });
      if (opened.ok === false && opened.trapped) break;
    }
    core.stop();
    const failed = results.filter((r) => !r.ok);
    return { ok: failed.length === 0 && results.length === allSamples.length, count: results.length, failed, results };
  },

  async wrongPasswordKeepsWorkerUsable({ roundTrips: [sample] }) {
    const core = await Core.start();
    const wrong = await core.call("open", { bytes: await sampleBytes(sample.file), password: crypto.randomUUID() });
    const right = await core.call("open", { bytes: await sampleBytes(sample.file), password: sample.password });
    core.stop();
    return { ok: !wrong.ok && !wrong.trapped && right.ok, wrong: wrong.message?.slice(0, 120) };
  },

  async randomValuesChangeOnEverySave({ roundTrips: [sample] }) {
    const core = await Core.start();
    await core.call("open", { bytes: await sampleBytes(sample.file), password: sample.password });
    for (const n of [1, 2]) {
      const saved = await core.call("save", { password: sample.password });
      await upload(`${label}--random-${n}.kdbx`, saved.value);
    }
    core.stop();
    return { ok: true, note: "种子、IV、盐是否不同由 oracle 核对" };
  },

  async unknownContentStaysGuarded({ guarded }) {
    const core = await Core.start();
    const readable = await core.call("open", { bytes: await sampleBytes(guarded.unknown), password: guarded.password });
    const saved = await core.call("save", { password: guarded.password });
    const refused = await core.call("open", { bytes: await sampleBytes(guarded.protected), password: guarded.password });
    core.stop();
    return {
      ok: readable.ok && readable.value.unknownContent.length > 0 && !saved.ok && !saved.trapped && !refused.ok && !refused.trapped,
      save: saved.message?.slice(0, 120),
      open: refused.message?.slice(0, 120),
    };
  },

  /** KDF 阶梯：真实参数，不降低。每档用新 Worker，从小到大，失败也记录页面还活着。 */
  async kdfLadder({ ladder, roundTrips: [sample] }) {
    const results = [];
    for (const step of ladder) {
      say(`  KDF ${step.name} ${step.memoryMiB}MiB i=${step.iterations} p=${step.parallelism}`);
      const core = await Core.start();
      await core.call("open", { bytes: await sampleBytes(sample.file), password: sample.password });
      await core.call("setKdf", step);
      const watch = watchMainThread();
      const saved = await core.call("save", { password: sample.password });
      const worstGapMs = watch();
      const record = { ...step, save: brief(saved), worstGapMs };
      if (saved.ok) {
        await upload(`${label}--kdf-${step.name}-${step.memoryMiB}-${step.iterations}-${step.parallelism}.kdbx`, saved.value.slice(0));
        const fresh = await Core.start();
        const reopened = await fresh.call("open", { bytes: saved.value, password: sample.password });
        record.reopen = brief(reopened);
        fresh.stop();
      }
      core.stop();
      results.push(record);
    }
    // 能力上限可以因浏览器而异，这里不判失败；判失败的是“崩了但页面也跟着挂”，那样根本走不到这里。
    return { ok: true, results };
  },

  /** 文件要的 KDF 内存超预算时，不分配直接报错，Worker 还能继续用。 */
  async budgetRefusesBeforeAllocating({ argon2Sample, roundTrips: [sample] }) {
    const core = await Core.start();
    const refused = await core.call("open", { bytes: await sampleBytes(argon2Sample.file), password: argon2Sample.password, memoryBudget: MiB });
    const right = await core.call("open", { bytes: await sampleBytes(sample.file), password: sample.password });
    core.stop();
    return { ok: !refused.ok && !refused.trapped && refused.message.includes("KDF_BUDGET") && right.ok, message: refused.message?.slice(0, 80), ms: refused.ms };
  },

  /** 取消：KDF 跑着时直接 terminate，立刻能开新 Worker，旧状态不在了。 */
  async cancelDuringKdf({ roundTrips: [sample] }) {
    const core = await Core.start();
    await core.call("open", { bytes: await sampleBytes(sample.file), password: sample.password });
    await core.call("setKdf", { name: "argon2id", memoryMiB: 256, iterations: 200, parallelism: 1 });
    const watch = watchMainThread();
    let finished = false;
    core.call("save", { password: sample.password }).then(() => { finished = true; });
    await new Promise((resolve) => setTimeout(resolve, 500));
    const beforeStop = finished;
    const begin = performance.now();
    core.stop();
    const stopMs = performance.now() - begin;
    const fresh = await Core.start();
    const status = await fresh.call("status");
    const reopened = await fresh.call("open", { bytes: await sampleBytes(sample.file), password: sample.password });
    fresh.stop();
    const worstGapMs = watch();
    return {
      ok: !beforeStop && !status.value.hasVault && reopened.ok,
      stopMs: Math.round(stopMs),
      worstGapMs,
      freshHadVault: status.value.hasVault,
    };
  },

  /** 超出能力的参数（比如恶意文件要 8 GiB）：只能坏 Worker，页面和下一个 Worker 都要正常。 */
  async impossibleKdfOnlyKillsTheWorker({ roundTrips: [sample] }) {
    const core = await Core.start();
    await core.call("open", { bytes: await sampleBytes(sample.file), password: sample.password });
    await core.call("setKdf", { name: "argon2id", memoryMiB: 8192, iterations: 1, parallelism: 1 });
    const reply = await Promise.race([
      core.call("save", { password: sample.password }),
      new Promise((resolve) => setTimeout(() => resolve({ ok: false, name: "timeout" }), 60_000)),
    ]);
    core.stop();
    const next = await Core.start();
    const reopened = await next.call("open", { bytes: await sampleBytes(sample.file), password: sample.password });
    next.stop();
    return { ok: !reply.ok && reopened.ok, reply: brief(reply) };
  },
};

async function run() {
  const config = await (await fetch("/core-config.json")).json();
  const results = {};
  for (const [name, probe] of Object.entries(probes)) {
    say(`${name}…`);
    try {
      results[name] = await probe(config);
    } catch (error) {
      results[name] = { ok: false, error: `${error.name}: ${error.message}` };
    }
  }
  const failed = Object.entries(results).filter(([, r]) => !r.ok).map(([name]) => name);
  await fetch("/report", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label, userAgent: navigator.userAgent, results, failed }),
  });
  say(failed.length ? `失败：${failed.join("、")}` : "全部完成，可以关闭此页。");
  document.title = "K070 完成";
}

if (label) run();
