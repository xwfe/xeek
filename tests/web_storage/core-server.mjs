// K070 共用：准备样本和配置、起本机服务、把写出的库交给独立核对。纯 JS 探针和 Flutter 页面都走这里。
import { execFileSync } from "node:child_process";
import { mkdir, readFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { RESULTS, startServer } from "./server.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const FIXTURES = join(HERE, "..", "fixtures", "kdbx");
const PYTHON = process.env.PYTHON ?? "python3";
const CHECK = join(HERE, "..", "wasm_core", "check_outputs.py");
const OUTPUTS = join(RESULTS, "wasm-out");
const CONFIG_DIRECTORY = join(HERE, "..", "wasm_core", "target", "inputs");

export async function serve(options) {
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

export function runCheck(label, configPath) {
  const report = join(RESULTS, `${label}.json`);
  try {
    const output = execFileSync(PYTHON, ["-B", CHECK, "check", report, OUTPUTS, configPath], { encoding: "utf8", maxBuffer: 1 << 24 });
    return JSON.parse(output);
  } catch (error) {
    // 核对脚本发现问题时退出码是 1，并正常打印结果；没有输出说明它自己崩了，错误要留全。
    if (error.stdout) return JSON.parse(error.stdout);
    throw new Error(`核对脚本崩溃：${String(error.stderr).slice(-600)}`);
  }
}

