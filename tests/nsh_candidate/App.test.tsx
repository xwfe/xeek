import { expect, open, test } from "nsh/test";

test("五导航和合成空态", async () => {
  const app = await open("./App.tsx");
  expect(app.texts()).toContain("演示邮箱（合成）");
  for (const [index, text] of ["暂无动态口令", "暂无证件", "暂无银行资料", "仅合成实验，未接入密码库"].entries()) {
    await app.press(`id:tab-${index + 1}`);
    expect(app.texts()).toContain(text);
  }
});
