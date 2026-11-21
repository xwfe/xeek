import { mount, signal, Text, View } from "nsh";
import { VaultPanel } from "./VaultPanel";

function SecurityApp() {
  const shown = signal(true);
  const audit = signal("");
  return <View style={{ flex: 1, padding: 12, gap: 8 }}>
    <Text>{`审计 ${audit()}`}</Text>
    <View testID="toggle-panel" onPress={() => shown.set(!shown())}><Text>销毁或重挂实验组件</Text></View>
    {shown() && <VaultPanel controls onAudit={code => audit.set(code)} />}
  </View>;
}

mount(SecurityApp);
