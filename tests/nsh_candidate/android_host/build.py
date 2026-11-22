#!/usr/bin/env python3
"""把 `nsh package --target android` 的产物重新装进 keex 实验宿主（debug 签名，不是发行包）。

用法：build.py <nsh 产出的 apk> <NSH 运行时 classes.jar> <输出 apk>
需要 ANDROID_HOME、JDK 与 ~/.android/debug.keystore。
"""
import os, pathlib, shutil, subprocess, sys, tempfile, zipfile

here = pathlib.Path(__file__).resolve().parent
source, runtime_jar, output = map(pathlib.Path, sys.argv[1:4])
sdk = pathlib.Path(os.environ["ANDROID_HOME"])
tools = sorted((sdk / "build-tools").iterdir())[-1]
platform = sorted((sdk / "platforms").iterdir())[-1] / "android.jar"


def run(*command):
    subprocess.run([str(part) for part in command], check=True)


with tempfile.TemporaryDirectory() as temp:
    work = pathlib.Path(temp)
    run("javac", "--release", "11", "-cp", f"{platform}:{runtime_jar}", "-d", work / "classes", here / "KeexActivity.java")
    run(tools / "d8", "--min-api", "26", "--lib", platform, "--classpath", runtime_jar, "--output", work,
        *sorted((work / "classes").rglob("*.class")))
    run(tools / "aapt2", "compile", "--dir", here / "res", "-o", work / "res.zip")
    run(tools / "aapt2", "link", "--manifest", here / "AndroidManifest.xml", "-I", platform,
        "--min-sdk-version", "26", "--target-sdk-version", "35", "-o", work / "base.apk", work / "res.zip")
    with zipfile.ZipFile(source) as packaged, zipfile.ZipFile(work / "base.apk", "a") as apk:
        for name in packaged.namelist():
            if name == "classes.dex" or name.startswith(("lib/", "assets/nsh/")):
                stored = name.endswith(".so")
                apk.writestr(name, packaged.read(name), zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED)
        apk.write(work / "classes.dex", "classes2.dex")
    run(tools / "zipalign", "-f", "-P", "16", "4", work / "base.apk", work / "aligned.apk")
    run(tools / "apksigner", "sign", "--ks", pathlib.Path.home() / ".android/debug.keystore",
        "--ks-pass", "pass:android", "--out", output, work / "aligned.apk")
