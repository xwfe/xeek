import { expect, open, test } from "nsh/test";

test("合成 Rust 核心纵向流程", async () => {
  const app = await open("./App.tsx", { width: 1024, height: 1600 });
  await app.type("id:vault-password", "keex-synthetic-V41-VAULT");
  await app.press("id:unlock");
  await app.waitFor("text:摘要已加载");
  expect(app.value("id:vault-password")).toBe("");
  const firstPage = app.texts();
  await app.press("id:next-page");
  await app.waitFor("text:摘要已加载");
  expect(app.texts()).not.toEqual(firstPage);
  await app.type("id:search", "impossible-title-k091");
  await app.press("id:search-submit");
  await app.waitFor("text:无匹配摘要");
  await app.clear("id:search");
  await app.type("id:search", "登录 Login");
  await app.press("id:search-submit");
  await app.waitFor("text:摘要已加载");
  expect(app.texts()).toContain("登录 Login");
  await app.press("id:read");
  await app.waitFor("text:单字段已读取");
  expect(app.value("id:field")).toBe("synthetic-user");
  await app.clear("id:field");
  await app.type("id:field", "synthetic-nsh-edit");
  await app.press("id:edit");
  await app.waitFor("text:单字段已修改");
  await app.type("id:vault-password", "keex-synthetic-V41-VAULT");
  await app.press("id:save");
  await app.waitFor("text:已保存新副本");
  await app.press("id:stale");
  await app.waitFor("text:旧句柄已拒绝");
  expect(app.value("id:field")).toBe("");
  expect(app.value("id:vault-password")).toBe("");
  expect(app.texts()).not.toContain("synthetic-nsh-edit");
});

test("错误密码不产生会话", async () => {
  const app = await open("./App.tsx");
  await app.type("id:vault-password", "wrong-synthetic");
  await app.press("id:unlock");
  await app.waitFor("text:UNLOCK_FAILED");
});

test("尚未调度的解锁也必须能取消", async () => {
  const app = await open("./App.tsx");
  await app.type("id:vault-password", "keex-synthetic-V41-VAULT");
  await app.press("id:cancel-unlock");
  await app.waitFor("text:取消回调已拒绝");
  expect(app.texts()).not.toContain("摘要已加载");
});
