import { cleanup, effect, lifecycle, Scroll, signal, Text, View, wakeCount } from "nsh";
import { Input } from "nsh/base";
import { VaultSession } from "keex/vault";

export function VaultPanel({ controls = false, onAudit = (_code: string) => {} }: {
  controls?: boolean; onAudit?: (code: string) => void;
} = {}) {
  const session = new VaultSession();
  const password = signal("");
  const query = signal("");
  const value = signal("");
  const status = signal("合成样本待解锁");
  const rows = signal<{ id: string; title: string }[]>([]);
  const sample = signal("baseline");
  const timing = signal("");
  const race = signal("");
  const clipboard = signal("empty");
  let retainedTicket: { binding: number; epoch: number } | undefined;
  let retainedEntry = "";
  let firstCopy: number | undefined;
  let previousTicket: { binding: number; epoch: number } | undefined;
  let previousEntry = "";
  let ticket: { binding: number; epoch: number } | undefined;
  let selected = "";
  let offset = 0;
  let uiEpoch = 0;
  const pageSize = () => sample() === "baseline" ? 2 : 50;

  function errorCode(error: unknown) {
    const code = (error as Error).message;
    return ["STALE_SESSION", "SESSION_INACTIVE", "FIELD_NOT_FOUND", "LOCKED_OR_BUSY", "UNLOCK_FAILED", "NO_EDIT"].includes(code) ? code : "OPERATION_FAILED";
  }

  async function run(action: () => Promise<void>) {
    const epoch = uiEpoch;
    try { await action(); }
    catch (error) { if (epoch === uiEpoch) status.set(errorCode(error)); }
  }
  async function page() {
    if (!ticket) return;
    const epoch = uiEpoch;
    status.set("加载中");
    const started = Date.now();
    const result = await session.page(ticket, query(), offset, pageSize());
    const bridge = Date.now() - started;
    if (epoch !== uiEpoch) return;
    rows.set(result.rows);
    selected = result.rows[0]?.id ?? "";
    retainedTicket = ticket;
    retainedEntry = selected;
    timing.set(`计时 ${sample()} offset=${offset} core_ms=${result.coreMs.toFixed(3)} bridge_ms=${bridge}`);
    status.set(result.rows.length ? "摘要已加载" : "无匹配摘要");
  }
  function clearUi() {
    uiEpoch++;
    ticket = undefined;
    selected = "";
    rows.set([]);
    value.set("");
    password.set("");
    timing.set("");
    status.set("已锁库");
    clipboard.set(session.clipboardStatus());
  }
  function lock() {
    session.lock();
    clearUi();
  }
  function selectSample(name: string) {
    previousTicket = ticket;
    previousEntry = selected;
    lock();
    session.selectSample(name);
    sample.set(name);
    query.set("");
    offset = 0;
    status.set("样本已切换");
  }
  let lastWake = wakeCount();
  effect(() => {
    const active = lifecycle() === "active";
    session.setActive(active);
    if (!active) clearUi();
    const wake = wakeCount();
    if (wake !== lastWake) { lastWake = wake; lock(); }
  });
  cleanup(() => { lock(); session.releaseBarrier(); });

  function audit(code: string) { race.set(code); onAudit(code); }
  async function startRace(kind: string) {
    if (kind !== "unlock" && (!ticket || !selected)) { audit("LOCKED_OR_BUSY"); return; }
    try {
      session.armBarrier(kind);
      const pending = kind === "unlock" ? session.unlock(session.beginUnlock(), password())
        : kind === "read" ? session.readField(ticket!, selected, "UserName")
        : kind === "page" ? session.page(ticket!, "", 0, 2)
        : kind === "copy" ? session.copySecret(ticket!, selected)
        : session.saveCopy(ticket!, password());
      password.set("");
      const completion = pending.then(() => audit("RACE_DELIVERED"), error => {
        audit(errorCode(error)); session.releaseBarrier();
      });
      await session.waitBarrier();
      audit("屏障已到达");
      await completion;
    } catch (error) { audit(errorCode(error)); session.releaseBarrier(); }
  }
  return <View style={{ gap: 8 }}>
    <View testID="sample-baseline" onPress={() => selectSample("baseline")}><Text>基础合成库</Text></View>
    <View testID="sample-1000" onPress={() => selectSample("scale-1000")}><Text>一千条合成库</Text></View>
    <View testID="sample-10000" onPress={() => selectSample("scale-10000")}><Text>一万条合成库</Text></View>
    <View testID="sample-stale" onPress={() => run(async () => {
      if (!previousTicket || !previousEntry) return;
      try { await session.readField(previousTicket, previousEntry, "UserName"); status.set("错误：切库旧句柄放行"); }
      catch (error) { status.set((error as Error).message === "STALE_SESSION" ? "切库旧句柄已拒绝" : "错误：切库拒绝类型不符"); }
    })}><Text>验证切库旧句柄</Text></View>
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
    <View testID="next-page" onPress={() => run(async () => { offset += pageSize(); await page(); })}><Text>下一页</Text></View>
    <View testID="previous-page" onPress={() => run(async () => { offset = Math.max(0, offset - pageSize()); await page(); })}><Text>上一页</Text></View>
    <Scroll style={{ height: 80 }}>{rows().map(row => <Text>{row.title}</Text>)}</Scroll>
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
    <Text>{timing()}</Text>
    {controls && <View style={{ gap: 8 }}>
      {["unlock", "read", "page", "save", "copy"].map(kind => <View testID={`race-${kind}`} onPress={() => startRace(kind)}><Text>屏障实验 {kind}</Text></View>)}
      <View testID="release-barrier" onPress={() => session.releaseBarrier()}><Text>释放交付屏障</Text></View>
      <View testID="probe-retained" onPress={() => run(async () => {
        if (!retainedTicket) return;
        try { await session.readField(retainedTicket, retainedEntry, "UserName"); status.set("ERROR_AUTH"); }
        catch (error) { status.set(errorCode(error)); }
      })}><Text>验证保留票据已撤权</Text></View>
      <View testID="copy-secret" onPress={() => run(async () => {
        if (!ticket || !selected) return;
        const version = await session.copySecret(ticket, selected);
        if (firstCopy === undefined) firstCopy = version;
        clipboard.set(session.clipboardStatus());
        audit(`COPY_${version}`);
      })}><Text>核心复制到内存剪贴板</Text></View>
      <View testID="copy-sentinel" onPress={() => run(async () => {
        if (!ticket) return;
        session.copySentinel(ticket);
        clipboard.set(session.clipboardStatus());
      })}><Text>复制 Rust 私有合成哨兵</Text></View>
      <View testID="external-copy" onPress={() => { session.clipboardExternalCopy(false); clipboard.set(session.clipboardStatus()); }}><Text>模拟用户另复制内容</Text></View>
      <View testID="external-same" onPress={() => { session.clipboardExternalCopy(true); clipboard.set(session.clipboardStatus()); }}><Text>模拟用户复制相同内容</Text></View>
      <View testID="clock-600" onPress={() => { session.advanceClipboardClock(600); clipboard.set(session.clipboardStatus()); }}><Text>内存时钟前进六百毫秒</Text></View>
      <View testID="clock-400" onPress={() => { session.advanceClipboardClock(400); clipboard.set(session.clipboardStatus()); }}><Text>内存时钟前进四百毫秒</Text></View>
      <View testID="old-expiry" onPress={() => { if (firstCopy !== undefined) session.expireClipboardVersion(firstCopy); clipboard.set(session.clipboardStatus()); }}><Text>投递旧版本过期回调</Text></View>
      <View testID="sensitive-error" onPress={() => run(async () => { if (ticket) session.sensitiveError(ticket); })}><Text>私有合成哨兵错误路径</Text></View>
      <Text>{`剪贴板 ${clipboard()}`}</Text>
      <Text>{race()}</Text>
    </View>}
  </View>;
}
