import { cleanup, effect, lifecycle, Scroll, signal, Text, View, wakeCount } from "nsh";
import { Input } from "nsh/base";
import { VaultSession } from "keex/vault";
import { palette } from "./theme";
import { Button, Card, fieldFocus, fieldStyle, Row } from "./ui";

export function VaultPanel(props: { controls?: boolean; onAudit?: (code: string) => void } = {}) {
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

  function audit(code: string) { race.set(code); props.onAudit?.(code); }
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
  // 状态点：失败（错误文案或 Rust 错误码）用警示色，进行中和待解锁用弱化色，其余用强调色。
  const statusColor = () => /^(错误|[A-Z_]+$)/.test(status()) ? palette().warning
    : /中$|待解锁$/.test(status()) ? palette().muted : palette().accent;
  return <View style={{ gap: 12 }}>
    <Card title="密码库">
      <View style={{ flexDirection: "row", padding: 3, borderRadius: 10, backgroundColor: palette().raised }}>
        <View testID="sample-baseline" role="button" accessibilityState={{ selected: sample() === "baseline" }} activeStyle={{ opacity: 0.6 }} accessibilityLabel="基础库" onPress={() => selectSample("baseline")} style={{ flex: 1, minHeight: 36, borderRadius: 8, alignItems: "center", justifyContent: "center", backgroundColor: sample() === "baseline" ? palette().surface : "transparent" }}>
          <Text style={{ fontSize: 13, fontWeight: sample() === "baseline" ? "600" : "400", color: sample() === "baseline" ? palette().text : palette().muted }}>基础库</Text>
        </View>
        <View testID="sample-1000" role="button" accessibilityState={{ selected: sample() === "scale-1000" }} activeStyle={{ opacity: 0.6 }} accessibilityLabel="一千条" onPress={() => selectSample("scale-1000")} style={{ flex: 1, minHeight: 36, borderRadius: 8, alignItems: "center", justifyContent: "center", backgroundColor: sample() === "scale-1000" ? palette().surface : "transparent" }}>
          <Text style={{ fontSize: 13, fontWeight: sample() === "scale-1000" ? "600" : "400", color: sample() === "scale-1000" ? palette().text : palette().muted }}>一千条</Text>
        </View>
        <View testID="sample-10000" role="button" accessibilityState={{ selected: sample() === "scale-10000" }} activeStyle={{ opacity: 0.6 }} accessibilityLabel="一万条" onPress={() => selectSample("scale-10000")} style={{ flex: 1, minHeight: 36, borderRadius: 8, alignItems: "center", justifyContent: "center", backgroundColor: sample() === "scale-10000" ? palette().surface : "transparent" }}>
          <Text style={{ fontSize: 13, fontWeight: sample() === "scale-10000" ? "600" : "400", color: sample() === "scale-10000" ? palette().text : palette().muted }}>一万条</Text>
        </View>
      </View>
      <Input testID="vault-password" masked value={password()} onChange={({ value }) => password.set(value)} placeholder="合成口令" accessibilityLabel="口令" style={fieldStyle()} focusStyle={fieldFocus()} />
      <Row>
        <Button testID="unlock" label="解锁" kind="primary" grow onPress={() => run(async () => {
      status.set("解锁中");
      const epoch = uiEpoch;
      const pending = session.unlock(session.beginUnlock(), password());
      password.set("");
      const opened = await pending;
      if (epoch !== uiEpoch) return;
      ticket = opened;
      offset = 0;
      await page();
    })} />
        <Button testID="save" label="另存副本" kind="ghost" grow onPress={() => run(async () => {
      if (!ticket) return;
      const epoch = uiEpoch;
      const pending = session.saveCopy(ticket, password());
      password.set("");
      await pending;
      if (epoch !== uiEpoch) return;
      status.set("已保存新副本");
    })} />
        <Button testID="lock" label="锁库" kind="ghost" onPress={lock} />
      </Row>
      <Row>
        <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: statusColor() }} />
        <Text style={{ fontSize: 13, color: palette().text }}>{status()}</Text>
      </Row>
    </Card>
    <Card title="条目">
      <Row>
        <View style={{ flex: 1 }}>
          <Input testID="search" value={query()} onChange={({ value }) => query.set(value)} placeholder="搜索标题" accessibilityLabel="搜索标题" autoCapitalize="none" autoCorrect={false} style={fieldStyle()} focusStyle={fieldFocus()} />
        </View>
        <Button testID="search-submit" label="搜索" kind="ghost" onPress={() => run(async () => { offset = 0; await page(); })} />
      </Row>
      <Scroll style={{ height: rows().length ? 132 : 44, borderRadius: 10, backgroundColor: palette().raised }}>
        {rows().length === 0 && <Text style={{ padding: 12, fontSize: 13, color: palette().muted }}>解锁后显示标题摘要</Text>}
        {rows().map(row => (
          <View style={{ flexDirection: "row", alignItems: "center", gap: 10, minHeight: 44, paddingHorizontal: 12, borderBottomWidth: 1, borderColor: palette().line }}>
            <View style={{ width: 28, height: 28, borderRadius: 14, alignItems: "center", justifyContent: "center", backgroundColor: palette().soft }}>
              <Text accessibilityElementsHidden style={{ fontSize: 13, fontWeight: "600", color: palette().accent }}>{row.title.slice(0, 1) || "·"}</Text>
            </View>
            <View style={{ flex: 1 }}><Text style={{ fontSize: 15, color: palette().text }}>{row.title}</Text></View>
          </View>
        ))}
      </Scroll>
      <Row>
        <Button testID="previous-page" label="上一页" kind="ghost" grow onPress={() => run(async () => { offset = Math.max(0, offset - pageSize()); await page(); })} />
        <Button testID="next-page" label="下一页" kind="ghost" grow onPress={() => run(async () => { offset += pageSize(); await page(); })} />
      </Row>
    </Card>
    <Card title="首条用户名">
      <Input testID="field" value={value()} onChange={({ value: text }) => value.set(text)} placeholder="读取后可编辑" accessibilityLabel="用户名" autoCapitalize="none" autoCorrect={false} style={fieldStyle()} focusStyle={fieldFocus()} />
      <Row>
        <Button testID="read" label="读取" kind="ghost" grow onPress={() => run(async () => {
      if (!ticket || !selected) return;
      const epoch = uiEpoch;
      const field = await session.readField(ticket, selected, "UserName");
      if (epoch !== uiEpoch) return;
      value.set(field);
      status.set("单字段已读取");
    })} />
        <Button testID="edit" label="修改" kind="primary" grow onPress={() => run(async () => {
      if (!ticket || !selected) return;
      const epoch = uiEpoch;
      await session.setUsername(ticket, selected, value());
      if (epoch !== uiEpoch) return;
      status.set("单字段已修改");
    })} />
      </Row>
    </Card>
    <Card title="实验检查">
      <Row>
        <Button testID="cancel-unlock" label="立即取消" kind="quiet" grow onPress={() => run(async () => {
      const pending = session.unlock(session.beginUnlock(), password());
      lock();
      try { await pending; status.set("错误：取消后仍解锁"); }
      catch (error) { status.set((error as Error).message === "STALE_SESSION" ? "取消回调已拒绝" : "错误：取消类型不符"); }
    })} />
        <Button testID="stale" label="锁库后旧句柄" kind="quiet" grow onPress={() => run(async () => {
      if (!ticket || !selected) return;
      const old = ticket;
      const entry = selected;
      lock();
      const pending = session.readField(old, entry, "UserName");
      try { await pending; status.set("错误：旧句柄放行"); }
      catch (error) { status.set((error as Error).message === "STALE_SESSION" ? "旧句柄已拒绝" : "错误：拒绝类型不符"); }
    })} />
        <Button testID="sample-stale" label="切库旧句柄" kind="quiet" grow onPress={() => run(async () => {
      if (!previousTicket || !previousEntry) return;
      try { await session.readField(previousTicket, previousEntry, "UserName"); status.set("错误：切库旧句柄放行"); }
      catch (error) { status.set((error as Error).message === "STALE_SESSION" ? "切库旧句柄已拒绝" : "错误：切库拒绝类型不符"); }
    })} />
      </Row>
      {timing() ? <Text style={{ fontSize: 11, color: palette().muted }}>{timing()}</Text> : null}
    </Card>
    {props.controls && <Card title="生命周期与剪贴板实验">
      <Row>
        {["unlock", "read", "page", "save", "copy"].map(kind => <Button testID={`race-${kind}`} label={`屏障 ${kind}`} kind="quiet" grow onPress={() => startRace(kind)} />)}
      </Row>
      <Row>
        <Button testID="release-barrier" label="释放屏障" kind="quiet" grow onPress={() => session.releaseBarrier()} />
        <Button testID="probe-retained" label="保留票据" kind="quiet" grow onPress={() => run(async () => {
          if (!retainedTicket) return;
          try { await session.readField(retainedTicket, retainedEntry, "UserName"); status.set("ERROR_AUTH"); }
          catch (error) { status.set(errorCode(error)); }
        })} />
        <Button testID="sensitive-error" label="哨兵错误" kind="quiet" grow onPress={() => run(async () => { if (ticket) session.sensitiveError(ticket); })} />
      </Row>
      <Row>
        <Button testID="copy-secret" label="复制密码" kind="quiet" grow onPress={() => run(async () => {
          if (!ticket || !selected) return;
          const version = await session.copySecret(ticket, selected);
          if (firstCopy === undefined) firstCopy = version;
          clipboard.set(session.clipboardStatus());
          audit(`COPY_${version}`);
        })} />
        <Button testID="copy-sentinel" label="复制哨兵" kind="quiet" grow onPress={() => run(async () => {
          if (!ticket) return;
          session.copySentinel(ticket);
          clipboard.set(session.clipboardStatus());
        })} />
        <Button testID="old-expiry" label="旧版过期" kind="quiet" grow onPress={() => { if (firstCopy !== undefined) session.expireClipboardVersion(firstCopy); clipboard.set(session.clipboardStatus()); }} />
      </Row>
      <Row>
        <Button testID="external-copy" label="外部另复制" kind="quiet" grow onPress={() => { session.clipboardExternalCopy(false); clipboard.set(session.clipboardStatus()); }} />
        <Button testID="external-same" label="外部同内容" kind="quiet" grow onPress={() => { session.clipboardExternalCopy(true); clipboard.set(session.clipboardStatus()); }} />
        <Button testID="clock-600" label="+600ms" kind="quiet" grow onPress={() => { session.advanceClipboardClock(600); clipboard.set(session.clipboardStatus()); }} />
        <Button testID="clock-400" label="+400ms" kind="quiet" grow onPress={() => { session.advanceClipboardClock(400); clipboard.set(session.clipboardStatus()); }} />
      </Row>
      <Text style={{ fontSize: 12, color: palette().muted }}>{`剪贴板 ${clipboard()}`}</Text>
      <Text style={{ fontSize: 12, color: palette().muted }}>{race()}</Text>
    </Card>}
  </View>;
}
