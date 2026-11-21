import { mount, openUrl, signal, Text, View } from "nsh";

function App() {
  const result = signal("等待权限反例");
  async function probe() {
    const results: string[] = [];
    for (const action of [() => fetch("https://example.invalid/"), () => openUrl("https://example.invalid/")]) {
      try {
        await action();
        results.push("意外放行");
      } catch (error) {
        results.push((error as { code?: string }).code === "ERR_ACCESS_DENIED" ? "已拒绝" : "错误不符");
      }
    }
    result.set(results.join(" / "));
  }
  return <View><View testID="probe" onPress={probe}><Text>验证拒绝</Text></View><Text>{result()}</Text></View>;
}

mount(App);
