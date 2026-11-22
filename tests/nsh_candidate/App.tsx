import { mount, safeArea, Scroll, signal, Text, View, windowSize } from "nsh";
import { palette } from "./theme";
import { VaultPanel } from "./VaultPanel";

const tabs = ["密码", "验证", "证件", "银行", "设置"];
const summaries = ["演示邮箱（合成）", "暂无动态口令", "暂无证件", "暂无银行资料", "仅合成实验，未接入密码库"];

function App() {
  const selected = signal(0);
  const wide = () => windowSize().width >= 760;
  const nav = (
    <View role="tablist" style={{
      flexDirection: wide() ? "column" : "row", gap: wide() ? 4 : 0,
      width: wide() ? 200 : undefined, padding: wide() ? 12 : 0,
      paddingTop: wide() ? safeArea().top + 20 : 6, paddingBottom: safeArea().bottom + (wide() ? 12 : 6),
      borderColor: palette().line, borderTopWidth: wide() ? 0 : 1, borderRightWidth: wide() ? 1 : 0,
      backgroundColor: palette().side,
    }}>
      {wide() && <Text style={{ fontSize: 22, fontWeight: "700", color: palette().text, paddingHorizontal: 12, paddingBottom: 16 }}>keex</Text>}
      {tabs.map((tab, index) => (
        <View testID={`tab-${index}`} role="tab" accessibilityLabel={tab} accessibilityState={{ selected: selected() === index }} activeStyle={{ opacity: 0.6 }} onPress={() => selected.set(index)} style={{
          flex: wide() ? undefined : 1, minHeight: 48, paddingHorizontal: 12, borderRadius: 10, justifyContent: "center",
          alignItems: wide() ? "flex-start" : "center",
          backgroundColor: wide() && selected() === index ? palette().soft : "transparent",
        }}>
          <Text style={{ fontSize: wide() ? 15 : 13, fontWeight: selected() === index ? "600" : "400", color: selected() === index ? palette().accent : palette().muted }}>{tab}</Text>
        </View>
      ))}
    </View>
  );
  return (
    <View style={{ flex: 1, flexDirection: wide() ? "row-reverse" : "column", backgroundColor: palette().bg }}>
      <View style={{ flex: 1, paddingTop: safeArea().top }}>
        <View style={{ width: "100%", maxWidth: 680, alignSelf: "center", flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingVertical: 12 }}>
          {!wide() && <Text style={{ fontSize: 22, fontWeight: "700", color: palette().text }}>keex</Text>}
          <View style={{ flex: 1 }}>
            <Text role="header" style={{ fontSize: wide() ? 22 : 15, fontWeight: wide() ? "700" : "500", color: wide() ? palette().text : palette().muted }}>{tabs[selected()]}</Text>
          </View>
          <View style={{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, backgroundColor: palette().soft }}>
            <Text style={{ fontSize: 12, fontWeight: "500", color: palette().accent }}>L0 合成数据</Text>
          </View>
        </View>
        <Scroll style={{ flex: 1 }} keyboardDismissMode="on-drag" keyboardShouldPersistTaps="handled">
          <View style={{ width: "100%", maxWidth: 680, alignSelf: "center", gap: 12, paddingHorizontal: 16, paddingBottom: "env(keyboard-inset-height)" }}>
            {selected() === 0 && <Text style={{ fontSize: 13, color: palette().muted }}>{summaries[0]}</Text>}
            {selected() === 0 ? <VaultPanel /> : (
              <View style={{ paddingVertical: 64, alignItems: "center" }}>
                <Text style={{ fontSize: 15, color: palette().muted }}>{summaries[selected()]}</Text>
              </View>
            )}
            <View style={{ height: 4 }} />
          </View>
        </Scroll>
      </View>
      {nav}
    </View>
  );
}

mount(App);
