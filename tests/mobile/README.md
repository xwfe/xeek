# K004 移动端桥接实验

同一份 Rust 核心接到 Flutter、Kotlin、Swift。只处理公开合成库，不是产品代码。结论见 [K004 证据](../../adr/evidence/K004.md)。

## Android 真机

工具都装在这个目录，不动全局环境。下载源用 `googledownloads.cn`，因为 `dl.google.com` 在本机经常连不上。从仓库根目录执行：

~~~sh
L="$PWD/tests/mobile/.android-sdk"; G=/opt/homebrew/share/android-commandlinetools
mkdir -p "$L" && cp -R "$G/licenses" "$L/" && ln -sfn "$G/cmdline-tools" "$L/cmdline-tools"
SDK_TEST_BASE_URL=https://googledownloads.cn/android/repository/ sdkmanager --sdk_root="$L" "platforms;android-36" "build-tools;36.0.0" "platform-tools" "ndk;28.2.13676358"
RUSTUP_HOME="$PWD/tests/wasm_core/.toolchain/rustup" rustup target add --toolchain 1.98.0 aarch64-linux-android aarch64-apple-ios aarch64-apple-ios-sim

export ANDROID_HOME="$L" GRADLE_USER_HOME="$PWD/tests/mobile/.gradle-home" JAVA_HOME="$(mise where java)"
python3 -B tests/mobile/prepare.py
python3 -B tests/wasm_core/build.py android
(cd tests/flutter_bridge/app && flutter build apk --release --target-platform android-arm64 --dart-define=KEEX_AUTO=flutter-android)
node tests/mobile/drive-android.mjs 设备序列号
~~~

`drive-android.mjs` 会装上测试 App，跑完卸载。它不启用自动填充或通行密钥，只用合成库，结果写进 `tests/web_storage/results/android-device.json`。

## Swift 和 iOS

~~~sh
python3 -B tests/wasm_core/build.py native ios
I=tests/mobile/ios; L=tests/wasm_core/target
xcrun swiftc -parse-as-library -O -I $I/include $I/KeexProbe/Sources/KeexProbe/KeexVault.swift $I/KeexProbe/main_helper.swift -L $L/release -lkeex_wasm_core -Xlinker -rpath -Xlinker "$PWD/$L/release" -o tests/mobile/build/swift-helper
python3 -B tests/wasm_core/compare_candidates.py keex-patched swift-c-rust
~~~

这条只在 Mac 上跑 Swift。iOS 上目前只验证编译和链接，因为本机没有模拟器运行时，iPhone 也没连上。

## 常见报错

- `Failed to find package 'platforms;android-36'`：`dl.google.com` 连不上，加上面的 `SDK_TEST_BASE_URL`。
- NDK 下载 `Premature EOF`：包有 950 MB，断了要重来。用 `curl -C -` 续传 `android-ndk-r28c-darwin.zip`，核对 SHA-1 后解压到 `ndk/28.2.13676358`。
- 手机上报 `dlopen failed`：看 .so 是否进了 `jniLibs/arm64-v8a`，`prepare.py` 重新生成工程不会删它，但 `flutter clean` 不影响它，手动删过要重新编。
- 探针连不上本机：看 `adb reverse --list`，端口固定 47120。
