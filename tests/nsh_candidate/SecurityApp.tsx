import { mount, safeArea, Scroll, signal, Text, View } from "nsh";
import { VaultPanel } from "./VaultPanel";
import { palette } from "./theme";
import { Button } from "./ui";

function SecurityApp() {
  const shown = signal(true);
  const audit = signal("");
  return (
    <View style={{ flex: 1, paddingTop: safeArea().top, paddingBottom: safeArea().bottom, backgroundColor: palette().bg }}>
      <Scroll style={{ flex: 1 }} keyboardDismissMode="on-drag" keyboardShouldPersistTaps="handled">
        <View style={{ padding: 12, gap: 12, paddingBottom: "env(keyboard-inset-height)" }}>
          <Text style={{ fontSize: 12, color: palette().muted }}>{`审计 ${audit()}`}</Text>
          <Button testID="toggle-panel" label="销毁或重挂" kind="quiet" onPress={() => shown.set(!shown())} />
          {shown() && <VaultPanel controls onAudit={code => audit.set(code)} />}
        </View>
      </Scroll>
    </View>
  );
}

mount(SecurityApp);
