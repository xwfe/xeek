import { mount, signal, Text, View, windowSize } from "nsh";
import { VaultPanel } from "./VaultPanel";

const tabs = ["密码", "验证", "证件", "银行", "设置"];
const summaries = ["演示邮箱（合成）", "暂无动态口令", "暂无证件", "暂无银行资料", "仅合成实验，未接入密码库"];

function App() {
  const selected = signal(0);
  const wide = () => windowSize().width >= 760;
  return (
    <View style={{ flex: 1, padding: 20, gap: 16, backgroundColor: "#f5f7fa" }}>
      <Text style={{ fontSize: 24, fontWeight: "bold", color: "#172b4d" }}>keex</Text>
      <Text style={{ fontSize: 14 }}>合成数据 · 仅连接 L0 样本</Text>
      <View style={{ flex: 1, gap: 16, flexDirection: wide() ? "row-reverse" : "column" }}>
      <View style={{ flex: 1, gap: 12 }}>
        <Text style={{ fontSize: 20 }}>{tabs[selected()]}</Text>
        <Text>{summaries[selected()]}</Text>
        {selected() === 0 && <VaultPanel />}
      </View>
      <View style={{ flexDirection: wide() ? "column" : "row", gap: 12 }}>
        {tabs.map((tab, index) => (
          <View testID={`tab-${index}`} onPress={() => selected.set(index)}
            style={{ paddingVertical: 12, paddingHorizontal: 6, alignItems: "center" }}>
            <Text style={{ color: selected() === index ? "#175cd3" : "#475467" }}>{tab}</Text>
          </View>
        ))}
      </View>
      </View>
    </View>
  );
}

mount(App);
