"""K004：生成 Flutter 的 Android、iOS 工程，再放进实验代码。

生成的工程不进版本库，这里只保留自己写的部分：Kotlin 探针、清单改动、Rust 库。
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
APP = ROOT / "tests/flutter_bridge/app"
ANDROID_SDK = HERE / ".android-sdk"


def prepare():
    subprocess.run(["flutter", "create", "--platforms=android,ios", "--org", "dev.keex", "--project-name", "keex_bridge_app",
                    "--no-pub", "."], cwd=APP, check=True, capture_output=True,
                   env={**os.environ, "ANDROID_HOME": str(ANDROID_SDK)})
    init = HERE / ".gradle-home/init.d"
    init.mkdir(parents=True, exist_ok=True)
    shutil.copy(HERE / "gradle-mirrors.gradle", init)
    # 项目级的 google() 优先于 init 脚本加的仓库，生成的工程里要直接换掉。
    gradle = APP / "android/build.gradle.kts"
    gradle.write_text(gradle.read_text().replace(
        "        google()\n        mavenCentral()\n",
        '        maven { url = uri("https://maven.aliyun.com/repository/google") }\n'
        '        maven { url = uri("https://maven.aliyun.com/repository/public") }\n'))
    main = APP / "android/app/src/main"
    shutil.copytree(HERE / "android-overlay/kotlin", main / "kotlin", dirs_exist_ok=True)
    manifest = main / "AndroidManifest.xml"
    text = manifest.read_text()
    if "ProbeActivity" not in text:
        # 探针跑在独立进程。明文只用于 adb reverse 到本机服务，生产不会这样配。
        text = text.replace("<application", '<uses-permission android:name="android.permission.INTERNET"/>\n    <application android:usesCleartextTraffic="true"', 1)
        text = text.replace("</application>", '''    <activity android:name="dev.keex.experiment.ProbeActivity" android:process=":probe" android:exported="true"
            android:theme="@android:style/Theme.Translucent.NoTitleBar"/>
    </application>''', 1)
        manifest.write_text(text)
    # iOS 没有动态加载：把静态库整个链进主程序，Dart 才能用 DynamicLibrary.process() 找到符号。
    library = ROOT / "tests/wasm_core/target"
    lines = (f'\nOTHER_LDFLAGS[sdk=iphoneos*] = $(inherited) -force_load {library}/aarch64-apple-ios/release/libkeex_wasm_core.a\n'
             f'OTHER_LDFLAGS[sdk=iphonesimulator*] = $(inherited) -force_load {library}/aarch64-apple-ios-sim/release/libkeex_wasm_core.a\n'
             'STRIP_STYLE = non-global\n')
    for name in ("Debug", "Release"):
        config = APP / f"ios/Flutter/{name}.xcconfig"
        if "force_load" not in config.read_text():
            config.write_text(config.read_text() + lines)
    print(APP / "android", APP / "ios")


if __name__ == "__main__":
    prepare()
