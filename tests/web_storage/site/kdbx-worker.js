// K070：KDF 和解析都放这里，主线程不被卡住；取消就是直接 terminate 整个 Worker。
// Worker 和 WASM 都不是秘密隔离边界，同源脚本照样能和它通信（ADR-0007 §2）。
import init, { Vault } from "./wasm/keex_wasm_core.js";

const started = performance.now();
let exports_;
let failure = null;
try {
  exports_ = await init();
} catch (error) {
  failure = `${error.name}: ${error.message}`;
}
const instantiateMs = performance.now() - started;

const WASM_KDF_LIMIT = 2047 * 1024 * 1024;
let vault = null;
const memory = () => exports_?.memory.buffer.byteLength ?? 0;

const operations = {
  status: () => ({ loaded: !failure, failure, instantiateMs, hasVault: Boolean(vault) }),
  open: ({ bytes, password, keyfile, memoryBudget }) => {
    vault?.free();
    vault = null;
    // 不传预算时按 WASM 的硬上限：单次分配不能到 2 GiB，超了不如先报错，别等崩溃。
    vault = Vault.open(new Uint8Array(bytes), password, keyfile ? new Uint8Array(keyfile) : undefined, memoryBudget || WASM_KDF_LIMIT);
    return JSON.parse(vault.summary());
  },
  summary: () => JSON.parse(vault.summary()),
  setUsername: ({ entry, username }) => vault.set_username(entry, username),
  setKdf: ({ name, memoryMiB, iterations, parallelism }) => vault.set_kdf(name, memoryMiB, iterations, parallelism),
  save: ({ password, keyfile }) => vault.save(password, keyfile ? new Uint8Array(keyfile) : undefined).buffer,
};

onmessage = ({ data: { id, op, args } }) => {
  const begin = performance.now();
  try {
    const value = operations[op](args);
    const transfer = value instanceof ArrayBuffer ? [value] : [];
    postMessage({ id, ok: true, value, ms: performance.now() - begin, memoryBytes: memory() }, transfer);
  } catch (error) {
    // WebAssembly.RuntimeError 是 panic 或内存不够：实例已经不可信，调用方必须丢弃这个 Worker。
    postMessage({
      id,
      ok: false,
      name: error.name,
      message: String(error.message),
      trapped: error instanceof WebAssembly.RuntimeError,
      ms: performance.now() - begin,
      memoryBytes: memory(),
    });
  }
};
postMessage({ ready: true });
