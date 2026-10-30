// 手动核对页：每一步记录实际发生了什么，提交后由人对照 README 判断。
import { SaveState, SaveStateText, offerDownload, sha256, writeFileVerified } from "./cipher-cache.js";

const results = [];
const state = document.querySelector("#save-state");
const log = document.querySelector("#log");
let handle = null;
let base = null;
let kept = null;

function show(saveState) {
  state.textContent = SaveStateText[saveState];
  state.dataset.state = saveState;
}
show(SaveState.MEMORY_ONLY);

function record(step, outcome) {
  results.push({ step, outcome, shown: state.dataset.state });
  log.textContent += `${step}：${outcome}\n`;
}

async function nextBytes() {
  const bytes = await (await fetch("/fixture.kdbx")).arrayBuffer();
  new DataView(bytes).setUint32(bytes.byteLength - 4, Date.now() >>> 0);
  return bytes;
}

async function write(step) {
  show(SaveState.MEMORY_ONLY);
  try {
    const bytes = await nextBytes();
    const result = await writeFileVerified(handle, bytes, { expectedSha256: base });
    base = result.sha256;
    show(result.state);
    record(step, result.state);
  } catch (error) {
    record(step, error.kind ?? error.name);
  }
}

const actions = {
  async sample() {
    const bytes = await (await fetch("/fixture.kdbx")).arrayBuffer();
    show(offerDownload(bytes, "keex-synthetic.kdbx").state);
    record("下载合成库", state.dataset.state);
    show(SaveState.MEMORY_ONLY);
  },
  async open() {
    [handle] = await showOpenFilePicker();
    base = await sha256(await (await handle.getFile()).arrayBuffer());
    record("打开", `已读取，写权限 ${await handle.queryPermission({ mode: "readwrite" })}`);
  },
  deny: () => write("拒绝授权后写回"),
  write: () => write("允许授权后写回"),
  conflict: () => write("外部修改后写回"),
  async cancel() {
    const outcome = await showSaveFilePicker({ suggestedName: "keex-copy.kdbx" }).then(() => "没有取消", (error) => error.name);
    record("另存为取消", outcome);
  },
  async "save-as"() {
    const target = await showSaveFilePicker({ suggestedName: "keex-copy.kdbx" });
    const result = await writeFileVerified(target, await nextBytes());
    show(result.state);
    record("另存为新文件", result.state);
  },
  async pending() {
    kept = await handle.createWritable();
    await kept.write(await nextBytes());
    record("写入未完成", "等待关闭浏览器");
  },
  revoked: () => write("撤销权限后写回"),
  async report() {
    await fetch("/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label: `manual-${navigator.userAgent.match(/(Edg|Chrome|Firefox|Safari)\/[\d.]+/)?.[0]}`, userAgent: navigator.userAgent, results, failed: [] }),
    });
    record("提交", "完成");
  },
};

for (const [id, action] of Object.entries(actions)) {
  document.querySelector(`#${id}`).addEventListener("click", () => {
    Promise.resolve().then(action).catch((error) => record(id, error.kind ?? error.name));
  });
}
