// 把 Flutter Web 的简体中文回退字体镜像到本地，供严格 CSP 下自托管。
//
//   node tests/forui_candidate/mirror_fonts.mjs
//
// Flutter Web 不能用系统字体，遇到中文就按引擎里写死的清单去 fonts.gstatic.com 下载 Noto Sans SC 的分片。
// keex 的 CSP 不放第三方字体，不自托管的话中文全显示成方块。分片清单从本机 Flutter SDK 读，
// 所以 SDK 升级后要重跑。字体是 SIL OFL 1.1 许可，允许自托管和随应用分发。
import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, ".fallback-fonts");
const flutter = execFileSync("which", ["flutter"], { encoding: "utf8" }).trim();
const root = join(dirname(execFileSync("readlink", ["-f", flutter], { encoding: "utf8" }).trim()), "..");
const manifest = join(root, "bin/cache/flutter_web_sdk/lib/_engine/engine/font_fallback_data.dart");
const paths = [...new Set((await readFile(manifest, "utf8")).match(/notosanssc\/v\d+\/[\w-]+\.\d+\.woff2/g))];

let total = 0;
for (const path of paths) {
  const file = join(OUT, path);
  const existing = await stat(file).catch(() => null);
  if (!existing) {
    const response = await fetch(`https://fonts.gstatic.com/s/${path}`);
    const bytes = Buffer.from(await response.arrayBuffer());
    // 拿到的不是 woff2（比如被拦截页面替换）就停下，免得把错误内容当字体发出去。
    if (!response.ok || bytes.subarray(0, 4).toString("latin1") !== "wOF2") throw new Error(`${path}: ${response.status}`);
    await mkdir(dirname(file), { recursive: true });
    await writeFile(file, bytes);
  }
  total += (await stat(file)).size;
}
console.log(`${paths.length} 个分片，共 ${(total / 1048576).toFixed(1)} MiB，在 ${OUT}`);
