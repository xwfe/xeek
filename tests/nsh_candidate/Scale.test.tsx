import { expect, open, test } from "nsh/test";

test("规模样本经 TSX Rust 桥分页搜索编辑并拒绝切库旧票据", async () => {
  const app = await open("./App.tsx", { width: 1024, height: 1600 });
  for (const count of [1000, 10000]) {
    await app.press(`id:sample-${count}`);
    await app.type("id:vault-password", `keex-synthetic-M41-SCALE-${count}-SMALL`);
    await app.press("id:unlock");
    await app.waitFor("text:摘要已加载", { timeout: 120000 });
    const first = app.texts().filter(text => !text.startsWith("计时 "));
    const started = Date.now();
    await app.press("id:next-page");
    await app.waitUntil(() => app.texts().some(text => text.includes("offset=50 ")));
    const visible = Date.now() - started;
    console.log(`K091 entries=${count} render_visible_ms=${visible} ${app.texts().find(text => text.startsWith("计时 "))}`);
    expect(app.texts().filter(text => !text.startsWith("计时 "))).not.toEqual(first);
    await app.press("id:previous-page");
    await app.waitUntil(() => app.texts().some(text => text.includes("offset=0 ")));
    expect(app.texts().filter(text => !text.startsWith("计时 "))).toEqual(first);
    await app.type("id:search", "impossible-title-k091");
    await app.press("id:search-submit");
    await app.waitFor("text:无匹配摘要");
    await app.clear("id:search");
    await app.type("id:search", "合成集中关联账户");
    await app.press("id:search-submit");
    await app.waitFor("text:摘要已加载");
    expect(app.texts().some(text => text.includes("合成集中关联账户"))).toBe(true);
    await app.press("id:read");
    await app.waitFor("text:单字段已读取");
    await app.clear("id:field");
    await app.type("id:field", "synthetic-nsh-edit");
    await app.press("id:edit");
    await app.waitFor("text:单字段已修改");
    await app.type("id:vault-password", `keex-synthetic-M41-SCALE-${count}-SMALL`);
    await app.press("id:save");
    await app.waitFor("text:已保存新副本", { timeout: 120000 });
    await app.press("id:sample-baseline");
    await app.press("id:sample-stale");
    await app.waitFor("text:切库旧句柄已拒绝");
    expect(app.value("id:field")).toBe("");
    expect(app.value("id:vault-password")).toBe("");
  }
}, 180000);
