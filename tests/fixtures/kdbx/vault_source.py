"""K069 确定性合成领域 XML；复用 K002，不读取真实资料，不写 KDBX。"""
from __future__ import annotations

import base64
import gzip
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import source

FORMATS = ("3.1", "4.0", "4.1")
EDIT_NAME = "service-login"
EDIT_PATH = "合成资料/合成服务账户"
EDIT_VALUES = ("synthetic-user-edit-1", "synthetic-user-edit-2")
RECORDED_AT = "2026-10-18T00:00:00Z"
DOCUMENT_BYTES = "合成证明附件：不代表真实身份或机构证明。\n".encode("utf-8")


def ref(name):
    return base64.b64decode(source.uid("vault/" + name)).hex()


def field(key, value, protected=False):
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return key, value, protected


def fact(**values):
    return dict(values, recordedAt=RECORDED_AT, source="user_entry", confidence="user_asserted")


def date(value, precision="date", **extra):
    return {"precision": precision, "value": value, **extra}


def relation(name, kind, target, state="active"):
    return field("keex.relation." + ref("relation/" + name),
                 {"type": kind, "target": ref(target), "state": state}, True)


def records():
    """源描述独立于 contract.py；没有列出的业务字段保持缺失。"""
    items = []

    def add(name, kind, title, fields=(), **extra):
        items.append(dict(name=name, type=kind,
                          fields=[field("Title", title), field("keex.record.schema", "1"),
                                  field("keex.record.type", kind), *fields], **extra))

    add("service-login", "login", "合成服务账户", [
        field("UserName", "synthetic-user-original"), field("Password", "合成领域密码-公开测试", True),
        field("URL", "https://service.example.com"), relation("login-recovery", "recoveredBy", "line")])
    add("bank-account", "finance_account", "合成金融账户", [
        field("keex.finance.institution", "合成金融机构"), field("keex.finance.accountHolder", "合成持有人", True),
        field("keex.finance.accountId", "TEST-ACCOUNT-001", True), field("keex.finance.accountKind", "bank"),
        field("keex.finance.currencies", ["USD", "JPY"], True),
        field("keex.finance.balance", fact(amount="1234.50", currency="USD"), True),
        relation("account-login", "serviceAccount", "service-login"),
        relation("account-proof", "documentedBy", "document")])
    for name, form in (("card-old", "physical"), ("card-new", "virtual")):
        fields = [
            field("keex.finance.form", form), field("keex.finance.number", "SYNTHETIC-" + name.upper(), True),
            field("keex.finance.holder", "合成持卡人", True),
            field("keex.finance.expires", date("2030-02", "month"), True),
            field("keex.finance.limit", fact(amount="100.00", currency="USD"), True),
            relation(name + "-account", "belongsTo", "bank-account"),
            field("X-Vault-Protected", "合成未知保护值-" + name, True)]
        if name == "card-new":
            fields.append(relation("card-replacement", "replaces", "card-old"))
        else:
            fields.append(field("keex.record.status", "archived"))
        add(name, "payment_card", "合成旧卡" if name == "card-old" else "合成新卡",
            fields, history=name == "card-old")
    for index, card in ((1, "card-old"), (2, "card-new")):
        add("subscription-" + str(index), "subscription", "合成订阅" + str(index), [
            field("keex.subscription.plan", "合成月付套餐"),
            field("keex.subscription.billing", fact(
                amount="9.90", currency="USD", period={
                    "unit": "month", "interval": 1, "anchor": date("2026-01-31"),
                    "timeZone": "Asia/Tokyo", "overflow": "clamp"}), True),
            field("keex.subscription.nextDue", date("2026-02-28"), True),
            field("keex.subscription.renewalIntent", "unknown"),
            relation("subscription-" + str(index) + "-card", "paidBy", card),
            relation("subscription-" + str(index) + "-login", "serviceAccount", "service-login")])
    add("line", "telecom_line", "合成通信线路", [
        field("keex.telecom.number", "SYNTHETIC-LINE-001", True),
        relation("line-current-profile", "usesProfile", "profile-new"),
        relation("line-old-profile", "usesProfile", "profile-old", "historical"),
        relation("line-plan", "usesPlan", "plan"),
        relation("line-service", "serviceAccount", "service-login")])
    add("profile-old", "sim_profile", "合成旧配置", [
        field("keex.telecom.profileKind", "esim"), field("keex.telecom.iccid", "TEST-ICCID-OLD", True),
        field("keex.telecom.activationCode", "LPA:1$activation.example.invalid$SYNTHETIC-OLD", True),
        field("keex.record.status", "archived")])
    add("profile-new", "sim_profile", "合成新配置", [
        field("keex.telecom.profileKind", "esim"), field("keex.telecom.iccid", "TEST-ICCID-NEW", True),
        field("keex.telecom.eid", "TEST-EID-NEW", True),
        field("keex.telecom.activationCode", "LPA:1$activation.example.invalid$SYNTHETIC-NEW", True),
        relation("profile-replacement", "replaces", "profile-old")])
    add("profile-uninstalled", "sim_profile", "合成未安装数据配置", [
        field("keex.telecom.profileKind", "esim"),
        field("keex.telecom.activationCode", "LPA:1$activation.example.invalid$SYNTHETIC-UNINSTALLED", True),
        field("keex.telecom.installState", fact(value="not_installed"), True),
        relation("uninstalled-plan", "usesPlan", "plan")])
    add("plan", "telecom_plan", "合成通信套餐", [
        field("keex.telecom.operator", "合成通信供应商"), field("keex.telecom.coverage", ["JP", "US"], True),
        field("keex.telecom.allowances", "合成数据流量；短信与验证用途未知"),
        field("keex.telecom.remaining", fact(value="2048", unit="byte"), True),
        field("keex.telecom.smsCapability", fact(value="unknown"), True),
        field("keex.telecom.price", fact(amount="19.90", currency="USD"), True),
        field("keex.telecom.validFrom", date("2026-11-01T01:30:00", "local",
              timeZone="America/New_York", fold=1), True),
        field("keex.telecom.validUntil", date("2026-12-31T00:00:00Z", "instant"), True)])
    add("identity", "identity_document", "合成证件", [
        field("keex.document.kind", "合成护照"), field("keex.document.identifier", "TEST-PASSPORT-001", True),
        field("keex.document.holder", "合成人物", True),
        field("keex.document.expires", date("2028-02-29"), True)], attachment=True)
    add("document", "document", "合成地址证明", [
        field("keex.document.kind", "合成地址证明"), field("keex.document.identifier", "TEST-DOCUMENT-001", True),
        field("keex.document.issued", date("2026-10-18"), True)], attachment=True)
    add("membership", "membership_card", "合成会员卡", [
        field("keex.document.identifier", "TEST-MEMBER-001", True),
        field("keex.document.barcode", "SYNTHETIC-BARCODE", True)])
    add("gift", "gift_card", "合成礼品卡", [
        field("keex.document.identifier", "TEST-GIFT-001", True),
        field("keex.finance.balance", fact(amount="50", currency="JPY"), True)])

    rule_id, event_id = ref("rule/monthly"), ref("event/completed")
    add("maintenance", "maintenance", "合成维护事项", [
        field("keex.maintenance.kind", "renew"),
        relation("maintenance-subscription", "maintains", "subscription-1"),
        field("keex.lifecycle.rule." + rule_id, fact(
            version=1, revision=1, kind="calendar", enabled=True, timeZone="Asia/Tokyo",
            anchor=date("2026-01-31"), unit="month", interval=1, overflow="clamp",
            lead={"unit": "calendar_day", "value": 7}), True),
        field("keex.lifecycle.event." + event_id, fact(
            version=1, kind="completed", ruleId=rule_id, ruleRevision=1,
            occurredAt="2026-02-28T00:00:00Z", effective=True,
            evidence={"entry": ref("document"), "attachment": "合成凭据.txt"}), True),
        field("keex.lifecycle.event." + ref("event/retracted"), fact(
            version=1, kind="retracted", ruleId=rule_id, ruleRevision=1,
            occurredAt="2026-03-01T00:00:00Z", targetEventId=event_id), True)])
    add("secure-note", "secure_note", "合成安全备注", [field("Notes", "合成内容，无自动操作", True)])
    add("cycle-a", "secure_note", "合成循环甲", [relation("cycle-a", "replaces", "cycle-b")])
    add("cycle-b", "secure_note", "合成循环乙", [relation("cycle-b", "replaces", "cycle-a")])
    add("missing-link", "login", "合成缺失引用", [
        relation("missing-recovery", "recoveredBy", "missing-target", "review")])
    add("future-schema", "secure_note", "合成未来版本", [
        field("X-Future-Protected", "合成未来版本未知值", True)])
    items[-1]["fields"][1] = field("keex.record.schema", "99")
    add("future-field", "secure_note", "合成未来字段", [
        field("keex.future.protected", '{"opaque":"synthetic-future"}', True)])
    add("legacy-conflict", "login", "合成旧关联冲突", [
        field("keex.parentEntryUuid", ref("service-login"), True),
        relation("conflicting-parent", "credentialOf", "missing-link")])
    add("trash-card", "payment_card", "合成回收卡片", [
        field("keex.finance.number", "SYNTHETIC-TRASH-CARD", True),
        relation("trash-account", "belongsTo", "bank-account", "historical")], recycle=True)
    return items


def build(format="4.1", sample_id="V41-VAULT"):
    if format not in FORMATS:
        raise ValueError("unsupported fixture format")
    root = ET.fromstring(source.build("rich", format, sample_id))
    meta = root.find("Meta")
    meta.find("DatabaseDescription").text = "keex K069 合成资料样本；未通过生产写入门槛"
    pool, old_pool = source.Pool(), meta.find("Binaries")
    for binary in old_pool:
        payload = base64.b64decode(binary.text or "")
        pool.items.append(gzip.decompress(payload) if binary.get("Compressed", "").lower() == "true" else payload)
    entries, recycled = [], []
    for item in records():
        history = []
        if item.get("history"):
            historical = [f for f in item["fields"] if f[0] != "X-Vault-Protected"]
            historical.append(field("X-Vault-History-Only", "合成仅历史保护值", True))
            history = [source.entry(format, pool, "vault/" + item["name"], historical,
                                    created=source.day(1), modified=source.day(2))]
        entry = source.entry(format, pool, "vault/" + item["name"], item["fields"],
                             created=source.day(1), modified=source.day(4), history=history,
                             attachments={"合成凭据.txt": DOCUMENT_BYTES} if item.get("attachment") else None)
        (recycled if item.get("recycle") else entries).append(entry)
    root.find("Root/Group").append(source.group(format, "vault/group", "合成资料", entries))
    recycle = next(g for g in root.iter("Group") if g.findtext("UUID") == source.uid("group/recycle"))
    recycle.extend(recycled)
    # 只改新语料的源 XML；保留旧混合 Passkey 的全部字段和身份。
    passkey = next(e for e in root.iter("Entry") if e.findtext("UUID") == source.uid("passkey"))
    passkey.append(source.field("keex.parentEntryUuid", source.uid("vault/service-login"), True))
    meta.remove(old_pool)
    meta.append(pool.element())
    ET.indent(root, space="\t")
    return (b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            + ET.tostring(root, encoding="utf-8") + b"\n")
