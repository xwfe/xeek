import { expect, open, test } from "nsh/test";

async function unlocked() {
  const app = await open("./SecurityApp.tsx", { width: 1024, height: 4000 });
  await app.type("id:vault-password", "keex-synthetic-V41-VAULT");
  await app.press("id:unlock");
  await app.waitFor("text:摘要已加载");
  return app;
}

test("非活动后台唤醒均撤销 Rust 权限且恢复不复活", async () => {
  for (const event of ["inactive", "background", "wake"]) {
    const app = await unlocked();
    await app.press("id:read");
    await app.waitFor("text:单字段已读取");
    if (event === "wake") await app.wake();
    else await app.setLifecycle(event as "inactive" | "background");
    await app.waitFor("text:已锁库");
    expect(app.value("id:field")).toBe("");
    await app.setLifecycle("active");
    await app.press("id:probe-retained");
    await app.waitFor("text:STALE_SESSION");
    expect(app.texts()).not.toContain("摘要已加载");
  }
});

test("确定性屏障拒绝锁库后解锁读取分页保存复制交付", async () => {
  for (const kind of ["unlock", "read", "page", "save", "copy"]) {
    const app = await unlocked();
    if (kind === "save") {
      await app.type("id:field", "synthetic-nsh-edit");
      await app.press("id:edit");
      await app.waitFor("text:单字段已修改");
    }
    await app.type("id:vault-password", "keex-synthetic-V41-VAULT");
    await app.press(`id:race-${kind}`);
    await app.waitFor("text:屏障已到达");
    await app.press("id:lock");
    await app.press("id:release-barrier");
    await app.waitFor("text:审计 STALE_SESSION");
    expect(app.texts()).not.toContain("RACE_DELIVERED");
    expect(app.value("id:field")).toBe("");
    expect(app.texts()).toContain("剪贴板 empty");
  }
});

test("屏障正对照与组件销毁撤权重挂", async () => {
  const app = await unlocked();
  await app.press("id:race-read");
  await app.waitFor("text:屏障已到达");
  await app.press("id:release-barrier");
  await app.waitFor("text:审计 RACE_DELIVERED");
  await app.press("id:race-read");
  await app.waitFor("text:屏障已到达");
  await app.press("id:toggle-panel");
  await app.waitFor("text:审计 STALE_SESSION");
  await app.press("id:toggle-panel");
  await app.waitFor("text:合成样本待解锁");
  expect(app.value("id:field")).toBe("");
});

test("剪贴板版本到期和锁库不清掉用户后复制内容", async () => {
  const app = await unlocked();
  await app.press("id:copy-secret");
  await app.waitFor("text:剪贴板 owned");
  await app.press("id:clock-600");
  await app.press("id:copy-secret");
  await app.waitFor("text:审计 COPY_2");
  await app.press("id:clock-400");
  await app.press("id:old-expiry");
  expect(app.texts()).toContain("剪贴板 owned");
  await app.press("id:clock-600");
  expect(app.texts()).toContain("剪贴板 empty");
  await app.press("id:copy-secret");
  await app.waitFor("text:剪贴板 owned");
  await app.press("id:external-copy");
  await app.press("id:lock");
  expect(app.texts()).toContain("剪贴板 external");
});

test("Rust 私有哨兵只留内存错误脱敏普通 Storage 为空", async () => {
  const app = await unlocked();
  await app.press("id:copy-sentinel");
  await app.waitFor("text:剪贴板 owned");
  await app.press("id:sensitive-error");
  await app.waitFor("text:FIELD_NOT_FOUND");
  expect(app.storage()).toEqual({});
  await app.press("id:external-same");
  await app.press("id:lock");
  await app.press("id:clock-600");
  await app.press("id:clock-400");
  expect(app.texts()).toContain("剪贴板 external");
  expect(app.storage()).toEqual({});
});

test("公开负控制证明 TSX 输入的原始 trace 仍会暴露输入", async () => {
  const app = await open("./SecurityApp.tsx", { width: 1024, height: 4000 });
  await app.type("id:vault-password", "SYNTHETIC-K092-INPUT-NEGATIVE");
  await app.press("id:lock");
  expect(app.value("id:vault-password")).toBe("");
  expect(app.storage()).toEqual({});
});
