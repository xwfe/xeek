#!/usr/bin/env python3
"""在已连接的模拟器上解锁合成库，触发一次系统事件，回前台后报告是否已撤权。

用法：probe.py <包名> <home|recents|screen|shade|rotate> [截图目录]
只读取界面文本和公开合成口令；结果是模拟器结果，不是真机结果。
"""
import pathlib, re, subprocess, sys, time
import xml.etree.ElementTree as ET

package, case = sys.argv[1:3]
shots = pathlib.Path(sys.argv[3]) if len(sys.argv) > 3 else None


def adb(*args):
    return subprocess.run(["adb", *args], capture_output=True, text=True, check=True).stdout


def nodes():
    for _ in range(5):
        adb("shell", "uiautomator", "dump", "/sdcard/keex-probe.xml")
        xml = adb("shell", "cat", "/sdcard/keex-probe.xml")
        if xml.startswith("<?xml"):
            return [node.attrib for node in ET.fromstring(xml).iter("node")]
        time.sleep(0.5)
    raise SystemExit("界面树读取失败")


def label(node):
    return node.get("text") or node.get("content-desc") or ""


def texts():
    return [label(node) for node in nodes() if label(node)]


def tap(name, kind):
    for node in nodes():
        if label(node) == name and kind in node["class"]:
            left, top, right, bottom = map(int, re.findall(r"\d+", node["bounds"]))
            adb("shell", "input", "tap", str((left + right) // 2), str((top + bottom) // 2))
            time.sleep(0.6)
            return
    raise SystemExit(f"找不到 {name}：{texts()}")


def wait(name, seconds=30):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if name in texts():
            return
        time.sleep(0.5)
    raise SystemExit(f"等不到 {name}：{texts()}")


def hide_keyboard():
    if "mInputShown=true" in adb("shell", "dumpsys", "input_method"):
        adb("shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(1.5)


def shot(name):
    if shots:
        png = subprocess.run(["adb", "exec-out", "screencap", "-p"], capture_output=True, check=True).stdout
        (shots / f"{package.rsplit('.', 1)[-1]}-{case}-{name}.png").write_bytes(png)


def launch():
    adb("shell", "monkey", "-p", package, "1")
    time.sleep(2)


adb("shell", "am", "force-stop", package)
launch()
tap("合成口令", "EditText")
adb("shell", "input", "text", "keex-synthetic-V41-VAULT")
time.sleep(1)
hide_keyboard()
tap("解锁", "Button")
wait("摘要已加载")
tap("读取", "Button")
wait("单字段已读取")
adb("logcat", "-b", "events", "-c")

if case == "home":
    adb("shell", "input", "keyevent", "KEYCODE_HOME")
    time.sleep(2)
    launch()
elif case == "recents":
    adb("shell", "input", "keyevent", "KEYCODE_APP_SWITCH")
    time.sleep(2.5)
    shot("overview")
    launch()
elif case == "screen":
    adb("shell", "input", "keyevent", "KEYCODE_SLEEP")
    time.sleep(3)
    adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
    time.sleep(1)
    adb("shell", "wm", "dismiss-keyguard")
    time.sleep(2)
elif case == "shade":
    adb("shell", "cmd", "statusbar", "expand-notifications")
    time.sleep(2)
    adb("shell", "cmd", "statusbar", "collapse")
    time.sleep(2)
elif case == "rotate":
    adb("shell", "settings", "put", "system", "accelerometer_rotation", "0")
    for rotation in ("1", "0"):
        adb("shell", "settings", "put", "system", "user_rotation", rotation)
        time.sleep(3)
    adb("shell", "settings", "put", "system", "accelerometer_rotation", "1")
else:
    raise SystemExit(f"未知事件 {case}")

activity = adb("shell", "cmd", "package", "resolve-activity", "--brief", package).split()[-1].rsplit(".", 1)[-1]
events = [line.split(": ", 1)[0].split()[-1] for line in adb("logcat", "-b", "events", "-d").splitlines()
          if "wm_on_" in line and f".{activity}," in line]
locked = "已锁库" in texts()
shot("return")
hide_keyboard()
for _ in range(4):
    if "保留票据" in texts():
        break
    adb("shell", "input", "swipe", "540", "1700", "540", "900", "500")
    time.sleep(1.2)
tap("保留票据", "Button")
time.sleep(1)
for _ in range(4):
    adb("shell", "input", "swipe", "540", "900", "540", "1900", "300")
    time.sleep(0.8)
retained = [text for text in texts() if text in ("STALE_SESSION", "ERROR_AUTH")]
print(f"{package} {case} 活动回调={events} 回前台已锁库={locked} 保留票据={retained}")
