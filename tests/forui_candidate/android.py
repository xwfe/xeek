"""forui 预实验的 Android 部分：生成工程、在模拟器或手机上看系统真正拿到的东西。

    python3 -B tests/forui_candidate/android.py prepare          # 生成 Android 工程并换成镜像源
    python3 -B tests/forui_candidate/android.py drive 设备序列号   # 装 App、导出无障碍树和输入法配置

drive 检查三件事：无障碍树（TalkBack 读的就是它）里中文标签、点击区域和秘密有没有漏；
点进输入框后系统输入法拿到的 inputType/imeOptions；200% 字号下的样子。结果和截图写进 results/。
会临时改设备的字号设置，跑完改回原值；只读模式的模拟器关机后连 App 带设置一起丢弃。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
APP = HERE / "app"
RESULTS = HERE / "results"
PACKAGE = "dev.keex.experiment.keex_forui_candidate"
APK = APP / "build/app/outputs/flutter-apk/app-release.apk"
HIDDEN_VALUE = "Kx-synth-00000!"
TABS = ["密码", "验证", "证件", "银行", "设置"]
# Android EditorInfo 的标志位。
IME_FLAG_NO_PERSONALIZED_LEARNING = 0x1000000
TYPE_MASK_VARIATION = 0xFF0
VARIATIONS = {0x80: "password", 0x90: "visiblePassword", 0xE0: "webPassword", 0x00: "normal", 0x20: "emailAddress"}


def prepare() -> None:
    if not (APP / "android").exists():
        subprocess.run(["flutter", "create", "--platforms=android,web", "--org", "dev.keex.experiment",
                        "--project-name", "keex_forui_candidate", "--no-pub", "."], cwd=APP, check=True,
                       capture_output=True)
    # 和 K004 一样：本机到 dl.google.com 时通时不通，项目级仓库直接换成阿里云镜像。
    gradle = APP / "android/build.gradle.kts"
    gradle.write_text(gradle.read_text().replace(
        "        google()\n        mavenCentral()\n",
        '        maven { url = uri("https://maven.aliyun.com/repository/google") }\n'
        '        maven { url = uri("https://maven.aliyun.com/repository/public") }\n'))
    print(APP / "android")


class Device:
    def __init__(self, serial: str) -> None:
        self.serial = serial
        self.density = int(re.search(r"(\d+)\s*$", self.shell("wm", "density")).group(1)) / 160

    def adb(self, *args: str, binary: bool = False):
        result = subprocess.run(["adb", "-s", self.serial, *args], check=True, capture_output=True)
        return result.stdout if binary else result.stdout.decode("utf-8", "replace")

    def shell(self, *args: str) -> str:
        return self.adb("shell", *args)

    def dump(self) -> ET.Element:
        # uiautomator 连上来时 Flutter 会把语义树交给系统，导出的就是 TalkBack 能读到的节点。
        for _ in range(3):
            out = self.shell("uiautomator", "dump", "/sdcard/keex-ui.xml")
            if "dumped" in out:
                return ET.fromstring(self.shell("cat", "/sdcard/keex-ui.xml"))
            time.sleep(1)
        raise RuntimeError(f"uiautomator dump 失败：{out}")

    def wait_for(self, predicate, timeout: float = 30) -> ET.Element:
        deadline = time.time() + timeout
        while time.time() < deadline:
            tree = self.dump()
            if predicate(tree):
                return tree
            time.sleep(1)
        raise TimeoutError("等不到目标界面")

    def tap(self, node: ET.Element) -> None:
        left, top, right, bottom = bounds(node)
        self.shell("input", "tap", str((left + right) // 2), str((top + bottom) // 2))

    def editor_info(self) -> dict:
        # 输入法服务的 dump 里有当前输入框的 EditorInfo，这是系统输入法真正拿到的配置。
        text = self.shell("dumpsys", "input_method")
        found = re.findall(r"inputType=0x([0-9a-f]+)\s+imeOptions=0x([0-9a-f]+)", text)
        if not found:
            raise RuntimeError("dumpsys input_method 里没有 EditorInfo")
        input_type, ime_options = (int(v, 16) for v in found[-1])
        return {
            "inputType": hex(input_type),
            "variation": VARIATIONS.get(input_type & TYPE_MASK_VARIATION, hex(input_type & TYPE_MASK_VARIATION)),
            "imeOptions": hex(ime_options),
            "noPersonalizedLearning": bool(ime_options & IME_FLAG_NO_PERSONALIZED_LEARNING),
        }

    def screenshot(self, name: str) -> None:
        (RESULTS / f"{name}.png").write_bytes(self.adb("exec-out", "screencap", "-p", binary=True))


def bounds(node: ET.Element) -> tuple[int, int, int, int]:
    return tuple(int(v) for v in re.findall(r"\d+", node.get("bounds")))  # type: ignore[return-value]


def nodes(tree: ET.Element) -> list[ET.Element]:
    return list(tree.iter("node"))


def spoken(node: ET.Element) -> str:
    return f"{node.get('text', '')}|{node.get('content-desc', '')}"


def find(tree: ET.Element, needle: str) -> ET.Element:
    for node in nodes(tree):
        if needle in spoken(node):
            return node
    raise LookupError(needle)


def small_targets(tree: ET.Element, density: float) -> list[str]:
    """可点节点里短边不到 48dp 的。被列表视口边缘裁掉一截的行不算，那是滚动位置，不是控件太小。"""
    viewports = [bounds(n) for n in nodes(tree) if n.get("scrollable") == "true"]
    issues = []
    for node in nodes(tree):
        if node.get("clickable") != "true":
            continue
        left, top, right, bottom = bounds(node)
        if top <= 0 or any(top == v[1] or bottom == v[3] for v in viewports):
            continue
        width, height = (right - left) / density, (bottom - top) / density
        if min(width, height) < 47.5:
            issues.append(f"{spoken(node).strip('|')[:24]} {width:.0f}×{height:.0f}dp")
    return issues


def focusable_without_click(tree: ET.Element, density: float) -> list[str]:
    """能被读屏聚焦、却不能“点击”的节点。读屏用户双击它时系统没有点击动作可发。"""
    return [f"{spoken(n).strip('|')[:24] or '（标签在提示文字里）'} y={bounds(n)[1] / density:.0f}dp"
            for n in nodes(tree) if n.get("focusable") == "true" and n.get("clickable") != "true"]


def screen_summary(tree: ET.Element, device: Device) -> dict:
    texts = [spoken(n) for n in nodes(tree)]
    return {
        "tabs": {tab: any(tab in t for t in texts) for tab in TABS},
        "secretLeaked": any(HIDDEN_VALUE in t for t in texts),
        "smallTargets": small_targets(tree, device.density),
        "focusableWithoutClick": focusable_without_click(tree, device.density),
        "passwordNodes": sum(n.get("password") == "true" for n in nodes(tree)),
    }


def launch(device: Device) -> ET.Element:
    device.shell("am", "force-stop", PACKAGE)
    device.shell("am", "start", "-W", "-n", f"{PACKAGE}/.MainActivity")
    return device.wait_for(lambda t: any("示例银行 00000" in spoken(n) for n in nodes(t)))


def drive(serial: str) -> int:
    RESULTS.mkdir(exist_ok=True)
    device = Device(serial)
    device.adb("install", "-r", str(APK))
    original_scale = device.shell("settings", "get", "system", "font_scale").strip()
    report: dict = {"device": device.shell("getprop", "ro.product.model").strip(),
                    "android": device.shell("getprop", "ro.build.version.release").strip(),
                    "density": device.density, "originalFontScale": original_scale}
    try:
        for scale in ("1.0", "2.0"):
            device.shell("settings", "put", "system", "font_scale", scale)
            tree = launch(device)
            device.screenshot(f"android-list-{scale}")
            entry = {"list": screen_summary(tree, device)}

            device.tap(find(tree, "示例银行 00000"))
            tree = device.wait_for(lambda t: any("返回" in spoken(n) for n in nodes(t)))
            device.screenshot(f"android-detail-{scale}")
            entry["detail"] = screen_summary(tree, device)
            # 大字时详情页超过一屏，屏幕外的节点不在导出里，往下滑到动态口令出现为止。
            below = tree
            for _ in range(4):
                if any("动态口令" in spoken(n) for n in nodes(below)):
                    break
                device.shell("input", "swipe", "700", "2300", "700", "1000", "400")
                time.sleep(1)
                below = device.dump()
            device.screenshot(f"android-detail-bottom-{scale}")
            entry["detail"]["otpHidden"] = any("动态口令，已隐藏" in spoken(n) for n in nodes(below))
            entry["detail"]["secretLeaked"] |= any(HIDDEN_VALUE in spoken(n) for n in nodes(below))
            entry["detailBelow"] = screen_summary(below, device)
            if below is not tree:
                tree = launch(device)
                device.tap(find(tree, "示例银行 00000"))
                tree = device.wait_for(lambda t: any("返回" in spoken(n) for n in nodes(t)))

            if scale == "1.0":
                secret = next(n for n in nodes(tree) if n.get("password") == "true")
                device.tap(secret)
                time.sleep(1.5)
                entry["keexSecretEditor"] = device.editor_info()
                # 输入框的标签在 Android 上是提示文字，Android 11 的 uiautomator 导出里没有这一栏，只能按控件类型找。
                title = next(n for n in nodes(tree) if n.get("class") == "android.widget.EditText" and n.get("password") != "true")
                device.tap(title)
                time.sleep(1.5)
                entry["titleEditor"] = device.editor_info()
            report[f"fontScale{scale}"] = entry

        # forui 自带密码框在设置页里的对照页。
        device.shell("settings", "put", "system", "font_scale", "1.0")
        tree = launch(device)
        device.tap(find(tree, "设置"))
        tree = device.wait_for(lambda t: any("实验对照" in spoken(n) for n in nodes(t)) or
                               any("forui 自带密码框" in spoken(n) for n in nodes(t)))
        for _ in range(5):
            if any("forui 自带密码框" in spoken(n) for n in nodes(tree)):
                break
            device.shell("input", "swipe", "500", "2200", "500", "900", "300")
            tree = device.dump()
        device.tap(find(tree, "forui 自带密码框"))
        tree = device.wait_for(lambda t: any(n.get("password") == "true" for n in nodes(t)))
        device.tap(next(n for n in nodes(tree) if n.get("password") == "true"))
        time.sleep(1.5)
        report["foruiBuiltinEditor"] = device.editor_info()
        report["foruiBuiltin"] = screen_summary(device.dump(), device)
    finally:
        device.shell("settings", "put", "system", "font_scale", original_scale if original_scale != "null" else "1.0")
        device.shell("am", "force-stop", PACKAGE)
    (RESULTS / "android.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["prepare"]:
        prepare()
    elif sys.argv[1:2] == ["drive"] and len(sys.argv) == 3:
        sys.exit(drive(sys.argv[2]))
    else:
        sys.exit(__doc__)
