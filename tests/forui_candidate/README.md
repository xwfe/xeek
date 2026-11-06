# forui 预实验

用 forui 0.27.7 搭一个只有合成数据的小页面：五项导航、1 万条条目列表、详情页、秘密输入框、设置页。用来测读屏、200% 大字、中文输入和 Web 严格 CSP。不是产品界面，也不是 K011 的交付。结论见 [证据](../../adr/evidence/K011_FORUI.md)。

## 怎么跑

依赖都装在这个目录，不动全局环境。从仓库根目录执行：

~~~sh
cd tests/forui_candidate/app
PUB_CACHE="$PWD/../.pub-cache" flutter pub get
PUB_CACHE="$PWD/../.pub-cache" flutter test
~~~

组件测试 28 项，几秒跑完。测试字体把每个字画成 1em 宽的方块，中文宽度和真机接近，英文偏宽，所以“不溢出”对中文是可信的。但测试字体行高偏大，按钮在测试里会比真机高，点击区域以 Android 实测为准。

**Android**：沿用 K004 装在 `tests/mobile/` 里的 SDK 和 Gradle 缓存，见 [K004 说明](../mobile/README.md)。

~~~sh
python3 -B tests/forui_candidate/android.py prepare
(cd tests/forui_candidate/app && ANDROID_HOME="$PWD/../../mobile/.android-sdk" GRADLE_USER_HOME="$PWD/../../mobile/.gradle-home" \
  JAVA_HOME="$(mise where java)" PUB_CACHE="$PWD/../.pub-cache" flutter build apk --release --target-platform android-arm64)
python3 -B tests/forui_candidate/android.py drive 设备序列号
~~~

`drive` 会临时把设备字号改成 200%，跑完改回原值。用模拟器时加 `-read-only` 启动，关机后 App 和设置一起丢弃，不动虚拟机本身。

**Web**：沿用 K071 的 Playwright，见 [K071 说明](../web_storage/README.md)。

~~~sh
node tests/forui_candidate/mirror_fonts.mjs
cd tests/web_storage && node drive-forui.mjs
~~~

第一条从 fonts.gstatic.com 下载简体中文回退字体的 97 个分片，共 2.3 MiB，放进 `.fallback-fonts/`。不跑它，严格 CSP 下中文全显示成方块。第二条打 JS 和 Wasm 两种包，在 ADR-0007 的严格 CSP 下跑 Chrome、Firefox、WebKit。Chrome 另用调试协议发输入法组合事件，模拟打拼音还没选词，普通路径和读屏路径各测一次。

## 常见报错

- `Unknown AVD name`：虚拟机目录在，但 `~/.android/avd/` 下缺同名 `.ini`。不想改用户目录，就另建一个目录放 `.ini`，`path=` 指向原虚拟机目录，再用 `ANDROID_AVD_HOME` 指过去。
- 测试报 `ambiguously found multiple matching widgets`：页面上有两个同名的读屏标签，按控件类型缩小范围再点。
- Android 上 `dumpsys input_method 里没有 EditorInfo`：输入框没拿到焦点，点完多等一会儿再读。
- Web 截图里中文是方块，CSP 报 `fonts.gstatic.com` 被拦：没先跑 `mirror_fonts.mjs`，或者 Flutter SDK 升级后分片清单变了，重跑一次。

## 文件

| 文件 | 作用 |
| --- | --- |
| [app/lib/src/theme.dart](app/lib/src/theme.dart) | 原型颜色到 forui 语义色的映射、系统字体、补到 48dp 的三处尺寸 |
| [app/lib/src/secret_field.dart](app/lib/src/secret_field.dart) | keex 自己的秘密输入框和动态口令显示 |
| [app/lib/src/detail_page.dart](app/lib/src/detail_page.dart) | 详情页、按平台分开的操作面板、forui 自带密码框对照页 |
| [app/lib/src/date_field.dart](app/lib/src/date_field.dart) | 补上读屏点击动作的日期框 |
| [app/web/flutter_bootstrap.js](app/web/flutter_bootstrap.js) | Web 启动配置：中文回退字体改从本站取 |
| [mirror_fonts.mjs](mirror_fonts.mjs) | 镜像简体中文回退字体 |
| [app/test/](app/test/) | 无障碍准则、200% 字号、输入法组合态、秘密字段配置、平台差异 |
| [android.py](android.py) | Android 工程准备和设备上的实测 |
| [../web_storage/drive-forui.mjs](../web_storage/drive-forui.mjs) | Web 构建和三个浏览器的实测 |
