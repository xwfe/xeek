import { Text, View } from "nsh";
import { palette } from "./theme";

type Children = { children?: unknown };

export function Card(props: Children & { title?: string }) {
  return (
    <View style={{ gap: 10, padding: 14, borderRadius: 14, borderWidth: 1, borderColor: palette().line, backgroundColor: palette().surface }}>
      {props.title && <Text role="header" style={{ fontSize: 13, fontWeight: "600", color: palette().muted }}>{props.title}</Text>}
      {props.children}
    </View>
  );
}

/** 主操作用强调色实心，其余用描边；触控高度 44。 */
export function Button(props: {
  testID: string; label: string; onPress: () => void; kind?: "primary" | "ghost" | "quiet"; grow?: boolean;
}) {
  const primary = props.kind === "primary";
  const quiet = props.kind === "quiet";
  return (
    <View testID={props.testID} role="button" accessibilityLabel={props.label} onPress={props.onPress}
      activeStyle={{ opacity: 0.6 }} focusStyle={{ borderWidth: 2, borderColor: palette().accent }} style={{
      flex: props.grow ? 1 : undefined, minHeight: quiet ? 36 : 44, paddingHorizontal: 14, borderRadius: 10,
      alignItems: "center", justifyContent: "center",
      borderWidth: primary || quiet ? 0 : 1, borderColor: palette().line,
      backgroundColor: primary ? palette().accent : quiet ? palette().raised : "transparent",
    }}>
      <Text style={{ fontSize: quiet ? 13 : 15, fontWeight: primary ? "600" : "500", color: primary ? palette().accentText : palette().text }}>{props.label}</Text>
    </View>
  );
}

export const fieldStyle = () => ({
  minHeight: 44, paddingHorizontal: 12, borderRadius: 10, borderWidth: 1, fontSize: 15,
  borderColor: palette().line, backgroundColor: palette().raised, color: palette().text,
  placeholderColor: palette().muted, caretColor: palette().accent,
});

export const fieldFocus = () => ({ borderColor: palette().accent });

export function Row(props: Children) {
  return <View style={{ flexDirection: "row", gap: 8, alignItems: "center" }}>{props.children}</View>;
}
