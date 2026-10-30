# K071 浏览器存储实验

验证浏览器里的文件、密文缓存、配额、单写者和恢复路径。只处理公开合成库，不是生产代码。结论和各浏览器结果见 [K071 证据](../../adr/evidence/K071.md)。

## 怎么跑

需要 Node 24 和 pnpm。在这个目录执行：

~~~sh
pnpm install --ignore-scripts
PLAYWRIGHT_BROWSERS_PATH="$PWD/.browsers" ./node_modules/.bin/playwright install firefox webkit
node drive.mjs                 # 全部可驱动的浏览器；结果写进 results/
node drive.mjs chrome firefox  # 只跑指定浏览器
~~~

第二条下载约 300 MB 到 `.browsers/`，不动全局环境。Chrome 和 Edge 用本机安装的官方版，没装时对应浏览器报错。不变量失败时退出码非 0；能力缺失只记成“受限”，不算失败。

**不能驱动的浏览器**（Safari、真机）用同一份探针：

~~~sh
node server.mjs 47110   # 另开终端，结果写进 results/
open -a Safari "http://127.0.0.1:47110/index.html?auto=safari&cap=512"
~~~

页面跑完标题变成“K071 完成”。`cap` 是配额探针最多写入的 MiB，不写就不做。Safari 的隐私模式没法自动打开，要手动开隐私窗口再粘贴这个地址，把 `auto=` 后面的标签改掉（比如 `safari-private`）。

**授权后的文件写回**只能人点，打开 `/manual.html` 按页面步骤走，用页面下载的合成库，不要选真实密码库。

## K072：WebDAV

结论见 [K072 证据](../../adr/evidence/K072.md)。先装测试服务器（只装在这个目录），再跑：

~~~sh
python3 -m venv .wsgidav
.wsgidav/bin/python -m pip install --only-binary=:all: -r webdav-requirements.txt
node drive-webdav.mjs                 # 全部可驱动的浏览器
node drive-webdav.mjs --serve 47111   # 只起服务，把打印的地址贴进 Safari 或真机
~~~

Apache 用 macOS 自带的 `/usr/sbin/httpd`，别的系统要改 `webdav-servers.mjs`。测试密码每次运行随机生成，只在本机回环地址上用，运行结束就没了。

## 文件

| 文件 | 作用 |
| --- | --- |
| [site/cipher-cache.js](site/cipher-cache.js) | 被测实现：密文缓存、写锁、文件写回、保存状态 |
| [site/lab.js](site/lab.js) | 探针页，能自己跑完并上报 |
| [site/manual.js](site/manual.js) | 手动核对页 |
| [site/webdav-client.js](site/webdav-client.js) | 被测实现：WebDAV 能力探针和条件提交 |
| [site/webdav-lab.js](site/webdav-lab.js) | WebDAV 探针页 |
| [webdav-servers.mjs](webdav-servers.mjs) | 测试服务器：Apache、WsgiDAV、故意出错的脚本服务器 |
| [drive-webdav.mjs](drive-webdav.mjs) | WebDAV 驱动，并用裸 socket 测服务器本身的行为 |
| [drive.mjs](drive.mjs) | 做页面做不到的事：杀进程、调配额、取消下载、重启浏览器 |
| [server.mjs](server.mjs) | 本机静态服务，带 ADR-0007 要求的严格 CSP |

## 看结果时要注意

- `firefox` 是 Playwright 打过补丁的版本，`webkit` 是 Playwright 的 WebKit 构建，**不是 Safari**。两者的结论不能直接算到官方版头上。
- `killDuringCommit` 杀的是进程，操作系统的页缓存还在，证明不了断电后数据还在。
- `evictionIsNotMistakenForANewVault` 用页面脚本删除来模拟驱逐，不是浏览器真实驱逐。

## 常见报错

- `Executable doesn't exist at .../.browsers/...`：没跑上面第二条，或 Playwright 版本变了要重新下载。
- `探针两分钟内没有上报`：页面卡住了。这一项会记成失败，别的场景继续跑。
- 驱动没有任何输出就退出：看是不是自己改过 `spawnGroup`。Apache 停止时向整个进程组发 SIGTERM，同组会把驱动一起杀掉。
- 开着真实 Chrome 时运行不受影响：每个场景都用临时配置目录，结束后删除。
