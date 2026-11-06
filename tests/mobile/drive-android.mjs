// K004：在连着的 Android 真机上跑。Flutter 主进程走 Dart FFI，:probe 进程走 Kotlin JNI，同一个 .so。
// adb reverse 把手机的 127.0.0.1:47120 接到本机服务；写出的库传回来由独立 oracle 核对。结束后卸载。
//
//   node drive-android.mjs 设备序列号
import { execFileSync } from "node:child_process";
import { writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { runCheck, serve } from "../web_storage/core-server.mjs";
import { RESULTS } from "../web_storage/server.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const APP = join(HERE, "..", "flutter_bridge", "app");
const PACKAGE = "dev.keex.keex_bridge_app";
const SERIAL = process.argv[2];
const PORT = 47120;
const ADB = join(HERE, ".android-sdk", "platform-tools", "adb");
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const adb = (...args) => execFileSync(ADB, ["-s", SERIAL, ...args], { encoding: "utf8", timeout: 120_000 }).trim();
const quiet = (...args) => { try { return adb(...args); } catch { return ""; } };
const pid = (name) => quiet("shell", "pidof", name);

const LADDER = [
  "aes-kdf:0:1000000:0", "argon2id:16:2:1", "argon2id:64:2:1", "argon2id:64:3:2", "argon2id:64:3:4",
  "argon2id:256:2:1", "argon2id:1024:2:1",
];

async function main() {
  if (!SERIAL) throw new Error("要给设备序列号");
  // 核心库编译失败时 APK 照样能打出来，只是少了它；这里先拦住，别装到手机上白跑。
  const apk = join(APP, "build/app/outputs/flutter-apk/app-release.apk");
  if (!execFileSync("unzip", ["-l", apk], { encoding: "utf8" }).includes("libkeex_wasm_core.so")) {
    throw new Error("APK 里没有 libkeex_wasm_core.so，先跑 python3 -B tests/wasm_core/build.py android");
  }
  const steps = [];
  let stepDone = null;
  let flutterDone = null;
  const flutterReport = new Promise((resolve) => { flutterDone = resolve; });
  const site = await serve({
    port: PORT,
    saveReports: true,
    onReport: (report) => flutterDone(report),
    routes: {},
    onProbeStep: (result) => { steps.push(result); stepDone?.(result); },
  });
  const results = { device: { model: adb("shell", "getprop", "ro.product.model"), android: adb("shell", "getprop", "ro.build.version.release"), sdk: adb("shell", "getprop", "ro.build.version.sdk") } };
  adb("reverse", `tcp:${PORT}`, `tcp:${PORT}`);
  adb("install", "-r", apk);
  adb("logcat", "-c");
  const runStep = async (step, timeout = 180_000) => {
    const finished = new Promise((resolve) => { stepDone = resolve; });
    adb("shell", "am", "force-stop", PACKAGE);
    await sleep(500);
    adb("shell", "am", "start", "-n", `${PACKAGE}/dev.keex.experiment.ProbeActivity`, "--es", "step", step);
    return Promise.race([finished, sleep(timeout).then(() => ({ step, error: "timeout" }))]);
  };
  try {
    // 1. 主程序根本没开时，Kotlin 进程自己能完成读改写，也没有加载 Flutter。
    adb("shell", "am", "force-stop", PACKAGE);
    results.environment = await runStep("environment");
    results.mainProcessDuringProbe = pid(PACKAGE) || "没有运行";
    const samples = ["vault", "passkey", "golden", "scale-1k", "scale-10k"];
    const roundTrips = {};
    for (const name of samples) {
      const result = await runStep(`roundtrip:${name}`);
      console.log(JSON.stringify(result));
      roundTrips[name] = result;
    }
    results.wrongPassword = await runStep("wrong");
    results.panic = await runStep("panic");
    results.budget = await runStep("budget");
    const ladder = [];
    for (const step of LADDER) {
      const result = await runStep(`ladder:${step}`);
      console.log(JSON.stringify(result));
      ladder.push(result);
    }
    const label = "kotlin-android";
    await writeFile(join(RESULTS, `${label}.json`), JSON.stringify({ label, results: {
      roundTrips: { results: roundTrips },
      kdfLadder: { results: ladder.filter((s) => s.ok).map((s) => ({ ...s, name: s.name })) },
      readsEveryRegisteredSample: { results: [] },
    } }, null, 2));
    results.kotlinCheck = runCheck(label, site.configPath);

    // 2. Flutter 主进程走 Dart FFI，通过同样的核对。
    adb("shell", "am", "force-stop", PACKAGE);
    adb("shell", "am", "start", "-n", `${PACKAGE}/.MainActivity`);
    const report = await Promise.race([flutterReport, sleep(240_000).then(() => { throw new Error("Flutter 没有按时上报"); })]);
    results.flutter = { wrongPassword: report.wrongPassword, budget: report.budget, worstFrameGapMs: report.worstFrameGapMs,
      timings: Object.fromEntries(Object.entries(report.results.roundTrips.results).map(([k, v]) => [k, [v.openMs, v.totalMs]])) };
    results.flutterCheck = runCheck("flutter-android", site.configPath);

    // 3. 主程序开着时，探针进程在 KDF 中途被结束，主程序不受影响。
    const before = pid(PACKAGE);
    adb("shell", "am", "start", "-n", `${PACKAGE}/dev.keex.experiment.ProbeActivity`, "--es", "step", "cancel:argon2id:1024:40:1");
    await sleep(800);
    const probeDuring = pid(`${PACKAGE}:probe`);
    await sleep(4000);
    results.cancel = { mainBefore: before, mainAfter: pid(PACKAGE), probeDuring, probeAfter: pid(`${PACKAGE}:probe`) };
    results.crashLog = quiet("logcat", "-d", "-b", "crash", "-v", "brief").split("\n").filter((l) => l.includes(PACKAGE) || l.includes("keex")).slice(0, 6);
  } finally {
    await writeFile(join(RESULTS, "android-device.json"), JSON.stringify({ ...results, steps }, null, 2));
    console.log(JSON.stringify(results, null, 1));
    quiet("uninstall", PACKAGE);
    quiet("reverse", "--remove", `tcp:${PORT}`);
    site.server.close();
  }
  process.exit(0);
}

await main();
