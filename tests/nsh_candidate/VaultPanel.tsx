import { signal, Text, View } from "nsh";
import { Input } from "nsh/base";
import { VaultSession } from "keex/vault";

export function VaultPanel() {
  const session = new VaultSession();
  const password = signal("");
  const query = signal("");
  const value = signal("");
  const status = signal("合成样本待解锁");
  const rows = signal<{ id: string; title: string }[]>([]);
  let ticket: { binding: number; epoch: number } | undefined;
  let selected = "";
  let offset = 0;
  let uiEpoch = 0;

  async function run(action: () => Promise<void>) {
    const epoch = uiEpoch;
    try { await action(); }
    catch (error) { if (epoch === uiEpoch) status.set(String((error as Error).message)); }
  }
  async function page() {
    if (!ticket) return;
    const epoch = uiEpoch;
    status.set("加载中");
    const result = await session.page(ticket, query(), offset, 2);
    if (epoch !== uiEpoch) return;
    rows.set(result);
    selected = result[0]?.id ?? "";
    status.set(result.length ? "摘要已加载" : "无匹配摘要");
  }
  function lock() {
    uiEpoch++;
    session.lock();
    ticket = undefined;
    selected = "";
    rows.set([]);
    value.set("");
    password.set("");
    status.set("已锁库");
  }
  return <View style={{ gap: 8 }}>
    <Input testID="vault-password" masked value={password()} onChange={({ value }) => password.set(value)} placeholder="仅输入公开合成口令" />
    <View testID="unlock" onPress={() => run(async () => {
      status.set("解锁中");
      const epoch = uiEpoch;
      const pending = session.unlock(session.beginUnlock(), password());
      password.set("");
      const opened = await pending;
      if (epoch !== uiEpoch) return;
      ticket = opened;
      offset = 0;
      await page();
    })}><Text>打开并解锁合成样本</Text></View>
    <View testID="cancel-unlock" onPress={() => run(async () => {
      const pending = session.unlock(session.beginUnlock(), password());
      lock();
      try { await pending; status.set("错误：取消后仍解锁"); }
      catch (error) { status.set((error as Error).message === "STALE_SESSION" ? "取消回调已拒绝" : "错误：取消类型不符"); }
    })}><Text>解锁并立即取消（合成反例）</Text></View>
    <Input testID="search" value={query()} onChange={({ value }) => query.set(value)} placeholder="只搜索标题" />
    <View testID="search-submit" onPress={() => run(async () => { offset = 0; await page(); })}><Text>搜索摘要</Text></View>
    <View testID="next-page" onPress={() => run(async () => { offset += 2; await page(); })}><Text>下一页</Text></View>
    {rows().map(row => <Text>{row.title}</Text>)}
    <View testID="read" onPress={() => run(async () => {
      if (!ticket || !selected) return;
      const epoch = uiEpoch;
      const field = await session.readField(ticket, selected, "UserName");
      if (epoch !== uiEpoch) return;
      value.set(field);
      status.set("单字段已读取");
    })}><Text>读取首条用户名</Text></View>
    <Input testID="field" value={value()} onChange={({ value: text }) => value.set(text)} placeholder="仅编辑一个用户名字段" />
    <View testID="edit" onPress={() => run(async () => {
      if (!ticket || !selected) return;
      const epoch = uiEpoch;
      await session.setUsername(ticket, selected, value());
      if (epoch !== uiEpoch) return;
      status.set("单字段已修改");
    })}><Text>修改单字段</Text></View>
    <View testID="save" onPress={() => run(async () => {
      if (!ticket) return;
      const epoch = uiEpoch;
      const pending = session.saveCopy(ticket, password());
      password.set("");
      await pending;
      if (epoch !== uiEpoch) return;
      status.set("已保存新副本");
    })}><Text>再次输入合成口令后保存新副本</Text></View>
    <View testID="stale" onPress={() => run(async () => {
      if (!ticket || !selected) return;
      const old = ticket;
      const entry = selected;
      lock();
      const pending = session.readField(old, entry, "UserName");
      try { await pending; status.set("错误：旧句柄放行"); }
      catch (error) { status.set((error as Error).message === "STALE_SESSION" ? "旧句柄已拒绝" : "错误：拒绝类型不符"); }
    })}><Text>锁库并验证旧句柄</Text></View>
    <View testID="lock" onPress={lock}><Text>取消或锁库</Text></View>
    <Text>{status()}</Text>
  </View>;
}
