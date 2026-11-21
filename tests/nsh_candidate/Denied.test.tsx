import { expect, open, test } from "nsh/test";

test("无 network/openUrl 授权必须拒绝而非网络故障", async () => {
  const app = await open("./Denied.tsx");
  await app.press("id:probe");
  await app.waitFor("text:已拒绝 / 已拒绝");
  expect(app.texts()).toContain("已拒绝 / 已拒绝");
});
