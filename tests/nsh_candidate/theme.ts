import { colorScheme } from "nsh";

// 颜色取自 adr/design/zh-CN/styles.css 的深浅两套语义变量。
const dark = {
  bg: "#0f131c", side: "#111620", surface: "#181e29", raised: "#202835", text: "#e6eaf2",
  muted: "#a0acbd", line: "#2b3544", accent: "#4edea3", accentText: "#06291b", soft: "#18382f", warning: "#f2c681",
};
const light = {
  bg: "#f5f7f9", side: "#ffffff", surface: "#ffffff", raised: "#edf1f5", text: "#1b2838",
  muted: "#566577", line: "#dce3e9", accent: "#096b48", accentText: "#ffffff", soft: "#e0f2e9", warning: "#805113",
};

export const palette = () => (colorScheme() === "dark" ? dark : light);
