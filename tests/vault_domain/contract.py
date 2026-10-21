"""K068 的可执行合成字段契约；不解密、不写库、不授予任何生产能力。

输入保留原字段和 Protected 属性，检查只返回无载荷的问题码。
valid 只表示通过本版本的测试规格，不表示 G0/GV0、写入或授权通过。
"""
from __future__ import annotations

import base64
import binascii
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

CONTRACT = json.loads(Path(__file__).with_name("contract.json").read_text(encoding="utf-8"))
FIELDS = CONTRACT["fields"]
UUID = re.compile(r"[0-9a-f]{32}\Z")
DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
INSTANT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z\Z")
LOCAL = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?\Z")
PROVENANCE = {"recordedAt", "source", "confidence"}
PROVENANCE_OPTIONAL = {"sourceReference"}
PREFIXES = ("keex.relation.", "keex.lifecycle.rule.", "keex.lifecycle.event.")
STANDARD = {"Title", "UserName", "Password", "URL", "Notes"}


@dataclass(frozen=True)
class Field:
    value: str
    protected: bool = False


@dataclass(frozen=True)
class Record:
    uuid: str
    fields: Mapping[str, Field]


@dataclass(frozen=True)
class Issue:
    code: str
    severity: str = "error"


@dataclass(frozen=True)
class Result:
    status: str
    issues: tuple[Issue, ...]
    record_type: str | None = None


class ContractError(ValueError):
    """只含稳定的问题码，不包含不可信字段名或字段值。"""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ContractError(code)


def _uuid(value) -> None:
    _require(isinstance(value, str) and bool(UUID.fullmatch(value)) and value != "0" * 32, "invalid_uuid")


def _text(value, *, empty=False) -> None:
    _require(isinstance(value, str), "expected_text")
    _require(empty or bool(value), "empty_value")
    _require("\0" not in value, "nul_value")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError:
        raise ContractError("invalid_unicode") from None
    _require(size <= CONTRACT["limits"]["fieldBytes"], "field_limit")


def _struct(value, required, optional=()) -> None:
    _require(type(value) is dict, "expected_object")
    _require(set(required) <= value.keys(), "missing_member")
    _require(value.keys() <= set(required) | set(optional), "unknown_member")


def _enum(value, allowed) -> None:
    _require(isinstance(value, str) and value in allowed, "unknown_enum")


def _integer(value, minimum=1, maximum=1000000) -> None:
    _require(type(value) is int and minimum <= value <= maximum, "invalid_integer")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate_member")
        result[key] = value
    return result


def _reject_number(_):
    raise ContractError("non_integer_json_number")


def _json(raw):
    _text(raw)
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_float=_reject_number, parse_constant=_reject_number)
    except (json.JSONDecodeError, RecursionError, ValueError) as error:
        if isinstance(error, ContractError):
            raise
        raise ContractError("invalid_json") from None
    pending = [(value, 0)]
    count = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        _require(depth <= CONTRACT["limits"]["jsonDepth"] and count <= CONTRACT["limits"]["jsonNodes"], "json_limit")
        if isinstance(item, dict):
            for key in item:
                _text(key)
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
        elif isinstance(item, str):
            _text(item, empty=True)
    return value


def _instant(value) -> None:
    _require(isinstance(value, str) and bool(INSTANT.fullmatch(value)), "invalid_instant")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ContractError("invalid_instant") from None


def _zone(value) -> ZoneInfo:
    _text(value)
    _require(value == "UTC" or ("/" in value and all(part not in ("", ".", "..") for part in value.split("/"))), "unknown_timezone")
    try:
        return ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError):
        raise ContractError("unknown_timezone") from None


def _date(value) -> None:
    _struct(value, {"precision", "value"}, {"timeZone", "fold"})
    precision = value["precision"]
    _enum(precision, ("month", "date", "instant", "local"))
    text = value["value"]
    _text(text)
    if precision == "month":
        _require(re.fullmatch(r"[0-9]{4}-[0-9]{2}", text) is not None, "invalid_month")
        _require(not ({"timeZone", "fold"} & value.keys()), "precision_parameters")
        try:
            date.fromisoformat(text + "-01")
        except ValueError:
            raise ContractError("invalid_month") from None
    elif precision == "date":
        _require(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text) is not None, "invalid_date")
        _require("fold" not in value, "precision_parameters")
        try:
            date.fromisoformat(text)
        except ValueError:
            raise ContractError("invalid_date") from None
        if "timeZone" in value:
            _zone(value["timeZone"])
    elif precision == "instant":
        _require(not ({"timeZone", "fold"} & value.keys()), "precision_parameters")
        _instant(text)
    else:
        _require(bool(LOCAL.fullmatch(text)), "invalid_local_time")
        _require("timeZone" in value, "missing_timezone")
        zone = _zone(value["timeZone"])
        try:
            naive = datetime.fromisoformat(text)
        except ValueError:
            raise ContractError("invalid_local_time") from None
        offsets = set()
        for fold in (0, 1):
            aware = naive.replace(tzinfo=zone, fold=fold)
            try:
                if aware.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == naive:
                    offsets.add(aware.utcoffset())
            except (OverflowError, ValueError):
                raise ContractError("unsupported_time_range") from None
        _require(bool(offsets), "nonexistent_local_time")
        if "fold" in value:
            _integer(value["fold"], 0, 1)
        if len(offsets) == 2:
            _require("fold" in value, "ambiguous_local_time")
        else:
            _require(value.get("fold", 0) == 0, "invalid_fold")


def _decimal(value) -> None:
    _require(isinstance(value, str) and bool(DECIMAL.fullmatch(value)), "invalid_decimal")
    unsigned = value.removeprefix("-")
    digits = unsigned.replace(".", "")
    scale = len(unsigned.partition(".")[2])
    _require(len(digits) <= CONTRACT["limits"]["decimalDigits"] and scale <= CONTRACT["limits"]["decimalScale"], "unsupported_decimal_precision")
    _require(not value.startswith("-") or any(ch != "0" for ch in digits), "negative_zero")


def _currency(value) -> None:
    _require(isinstance(value, str) and value in CONTRACT["currencies"], "unsupported_currency")


def _provenance(value, *, shape=True) -> None:
    if shape:
        _struct(value, PROVENANCE, PROVENANCE_OPTIONAL)
    _instant(value["recordedAt"])
    _enum(value["source"], CONTRACT["sources"])
    _enum(value["confidence"], CONTRACT["confidence"])
    _require(value["confidence"] != "user_verified" or value["source"] == "user_verified", "unverified_source")
    if "sourceReference" in value:
        _text(value["sourceReference"])


def _money(value, *, fact=False) -> None:
    required = {"amount", "currency"} | (PROVENANCE if fact else set())
    _struct(value, required, PROVENANCE_OPTIONAL if fact else ())
    _decimal(value["amount"])
    _currency(value["currency"])
    if fact:
        _provenance(value, shape=False)


def _period(value) -> None:
    _struct(value, {"unit", "interval", "anchor", "overflow"}, {"timeZone"})
    _enum(value["unit"], ("day", "month", "year"))
    _integer(value["interval"], 1, 10000)
    _date(value["anchor"])
    _require(value["anchor"]["precision"] in ("date", "month"), "invalid_anchor")
    _require(value["unit"] != "day" or value["anchor"]["precision"] == "date", "invalid_anchor")
    _enum(value["overflow"], ("clamp",))
    if "timeZone" in value:
        _zone(value["timeZone"])
        if "timeZone" in value["anchor"]:
            _require(value["timeZone"] == value["anchor"]["timeZone"], "conflicting_timezone")


def _compound(kind, value) -> None:
    if kind == "date" or kind == "year_month":
        _date(value)
        if kind == "year_month":
            _require(value["precision"] == "month", "month_precision_required")
    elif kind == "provenance":
        _provenance(value)
    elif kind == "money_fact":
        _money(value, fact=True)
    elif kind in ("text_list", "currencies"):
        _require(type(value) is list and len(value) <= 256, "invalid_list")
        _require(all(isinstance(x, str) for x in value), "invalid_list")
        _require(len(set(value)) == len(value), "duplicate_list_item")
        for item in value:
            (_currency if kind == "currencies" else _text)(item)
    elif kind == "billing":
        _struct(value, {"amount", "currency", "period"} | PROVENANCE, PROVENANCE_OPTIONAL)
        _decimal(value["amount"])
        _currency(value["currency"])
        _period(value["period"])
        _provenance(value, shape=False)
    elif kind == "quantity_fact":
        _struct(value, {"value", "unit"} | PROVENANCE, PROVENANCE_OPTIONAL)
        _decimal(value["value"])
        _require(not value["value"].startswith("-"), "negative_quantity")
        _enum(value["unit"], ("byte", "minute", "message"))
        _provenance(value, shape=False)
    elif kind == "activation":
        _struct(value, {"trigger"} | PROVENANCE, {"durationDays"} | PROVENANCE_OPTIONAL)
        _enum(value["trigger"], ("unknown", "manual", "first_use", "installation"))
        if "durationDays" in value:
            _integer(value["durationDays"], 1, 10000)
        _provenance(value, shape=False)
    elif kind.endswith("_fact"):
        _struct(value, {"value"} | PROVENANCE, PROVENANCE_OPTIONAL)
        options = {
            "service_fact": ("unknown", "active", "inactive", "suspended", "pending"),
            "install_fact": ("unknown", "not_installed", "installed", "disabled"),
            "capability_fact": ("unknown", "yes", "no"),
            "cancellation_fact": ("unknown", "requested", "user_confirmed"),
        }
        _enum(value["value"], options[kind])
        _provenance(value, shape=False)
        if kind == "capability_fact" and value["value"] != "unknown":
            _require(value["confidence"] == "user_verified", "capability_not_verified")
    else:
        raise ContractError("unknown_kind")


def _relation(value, record_type, own_uuid, target_types) -> None:
    _struct(value, {"type", "target", "state"}, {"validFrom", "validUntil"})
    _enum(value["type"], CONTRACT["relations"])
    definition = CONTRACT["relations"][value["type"]]
    _require(record_type in definition["sources"], "relation_source_type")
    _uuid(value["target"])
    _require(value["target"] != own_uuid, "self_relation")
    _enum(value["state"], ("active", "historical", "review"))
    if target_types is not None and value["target"] in target_types:
        allowed = definition["targets"]
        target = target_types[value["target"]]
        _require(target == record_type if "$same" in allowed else target in allowed, "relation_target_type")
    for key in ("validFrom", "validUntil"):
        if key in value:
            _date(value[key])
    if "validFrom" in value and "validUntil" in value:
        start, end = value["validFrom"], value["validUntil"]
        _require(start["precision"] == end["precision"] and start.get("timeZone") == end.get("timeZone"), "incomparable_validity")
        _require(start["precision"] != "local", "incomparable_validity")
        if start["precision"] == "instant":
            before = datetime.fromisoformat(start["value"].replace("Z", "+00:00"))
            after = datetime.fromisoformat(end["value"].replace("Z", "+00:00"))
            _require(before <= after, "invalid_validity")
        else:
            _require(start["value"] <= end["value"], "invalid_validity")


def _rule(value) -> None:
    base = {"version", "revision", "kind", "enabled"} | PROVENANCE
    options = {"timeZone", "lead"} | PROVENANCE_OPTIONAL
    _require(type(value) is dict and isinstance(value.get("kind"), str), "invalid_rule")
    kind = value["kind"]
    if kind == "once":
        _struct(value, base | {"due"}, options)
        _date(value["due"])
    elif kind == "manual_next":
        _struct(value, base, options | {"due"})
        if "due" in value:
            _date(value["due"])
    elif kind == "calendar":
        _struct(value, base | {"anchor", "unit", "interval", "overflow"}, options)
        _period({key: value[key] for key in ("anchor", "unit", "interval", "overflow")} |
                ({"timeZone": value["timeZone"]} if "timeZone" in value else {}))
        _enum(value["unit"], ("month", "year"))
    elif kind == "rolling":
        _struct(value, base | {"unit", "interval"}, options | {"basisEventId"})
        _enum(value["unit"], ("day", "month", "year"))
        _integer(value["interval"], 1, 10000)
        if "basisEventId" in value:
            _uuid(value["basisEventId"])
    else:
        raise ContractError("unknown_rule_kind")
    _require(type(value["version"]) is int and value["version"] == 1, "unknown_rule_version")
    _integer(value["revision"])
    _require(type(value["enabled"]) is bool, "invalid_enabled")
    _provenance(value, shape=False)
    if "timeZone" in value:
        _zone(value["timeZone"])
        if "due" in value and "timeZone" in value["due"]:
            _require(value["timeZone"] == value["due"]["timeZone"], "conflicting_timezone")
    if "lead" in value:
        _struct(value["lead"], {"unit", "value"})
        _enum(value["lead"]["unit"], ("calendar_day",))
        _integer(value["lead"]["value"], 0, 3660)


def _event(value) -> None:
    _require(type(value) is dict and isinstance(value.get("kind"), str), "invalid_event")
    base = {"version", "kind", "ruleId", "ruleRevision", "occurredAt"} | PROVENANCE
    optional = {"evidence"} | PROVENANCE_OPTIONAL
    if value["kind"] == "completed":
        _struct(value, base | {"effective"}, optional)
        _require(type(value["effective"]) is bool, "invalid_effective")
    elif value["kind"] == "retracted":
        _struct(value, base | {"targetEventId"}, optional)
        _uuid(value["targetEventId"])
    else:
        raise ContractError("unknown_event_kind")
    _require(type(value["version"]) is int and value["version"] == 1, "unknown_event_version")
    _uuid(value["ruleId"])
    _integer(value["ruleRevision"])
    _instant(value["occurredAt"])
    _provenance(value, shape=False)
    if "evidence" in value:
        _struct(value["evidence"], {"entry", "attachment"})
        _uuid(value["evidence"]["entry"])
        _text(value["evidence"]["attachment"])


def _legacy_uuid(value):
    _text(value)
    if re.fullmatch(r"[0-9A-Fa-f]{32}", value):
        normalized = value.lower()
    elif re.fullmatch(r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}", value):
        normalized = value.replace("-", "").lower()
    else:
        try:
            raw = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError):
            raise ContractError("invalid_legacy_parent") from None
        _require(len(raw) == 16 and base64.b64encode(raw).decode() == value, "invalid_legacy_parent")
        normalized = raw.hex()
    _uuid(normalized)
    return normalized


def record_from_pairs(entry_uuid: str, pairs: Sequence[tuple[str, Field]]) -> Record:
    """XML 适配必须在转成 map 之前检查重复 String Key，不能最后一个值胜出。"""
    fields = {}
    for key, field in pairs:
        _text(key)
        _require(isinstance(field, Field), "invalid_field")
        _require(key not in fields, "duplicate_field")
        fields[key] = field
    return Record(entry_uuid, fields)


def requires_reveal(key: str, field: Field) -> bool:
    """显示策略更严格，不修改原保护位；未知扩展不自动进入摘要。"""
    if field.protected or key == "Password":
        return True
    if key in STANDARD:
        return False
    definition = FIELDS.get(key)
    return definition["protected"] if definition else True


def atomic_group_for(key: str) -> tuple[str, ...]:
    """供规格测试使用；不是合并器或保存事务。"""
    if key in CONTRACT["atomicGroups"]["recordIdentity"]:
        return tuple(CONTRACT["atomicGroups"]["recordIdentity"])
    return (key,)


def inspect_record(record: Record, target_types: Mapping[str, str] | None = None) -> Result:
    issues = []
    relations, rules, events = {}, {}, {}
    def issue(code, severity="error"):
        item = Issue(code, severity)
        if item not in issues:
            issues.append(item)
    try:
        _uuid(record.uuid)
    except ContractError as error:
        issue(str(error))
    fields = record.fields
    if not isinstance(fields, Mapping):
        return Result("read_only", tuple(issues) + (Issue("invalid_record_fields"),))
    schema = fields.get("keex.record.schema")
    kind_field = fields.get("keex.record.type")
    record_type = kind_field.value if isinstance(kind_field, Field) and isinstance(kind_field.value, str) else None
    has_domain = any(key.startswith("keex.") and key != "keex.parentEntryUuid"
                     for key in fields if isinstance(key, str))
    legacy = not has_domain
    if has_domain:
        if not isinstance(schema, Field) or not isinstance(kind_field, Field):
            issue("missing_marker")
        else:
            if schema.value != "1":
                issue("unknown_schema")
            if record_type not in CONTRACT["types"]:
                issue("unknown_type")
        title = fields.get("Title")
        if not isinstance(title, Field) or not isinstance(title.value, str) or not title.value.strip():
            issue("missing_title")
    for key, field in fields.items():
        try:
            _text(key)
            _require(isinstance(field, Field) and type(field.protected) is bool, "invalid_field")
            _text(field.value, empty=True)
            if key in FIELDS:
                definition = FIELDS[key]
                scope = definition["types"]
                _require("*" in scope or record_type in scope, "field_type_mismatch")
                _require(not definition["protected"] or field.protected, "protection_required")
                kind = definition["kind"]
                if kind == "schema":
                    _require(field.value == "1", "unknown_schema")
                elif kind == "enum":
                    _enum(field.value, definition["values"])
                elif kind != "text":
                    _compound(kind, _json(field.value))
            elif key.startswith(PREFIXES):
                prefix = next(p for p in PREFIXES if key.startswith(p))
                identifier = key[len(prefix):]
                _uuid(identifier)
                _require(field.protected, "protection_required")
                value = _json(field.value)
                if prefix == PREFIXES[0]:
                    _relation(value, record_type, record.uuid, target_types)
                    relations[identifier] = value
                else:
                    _require(record_type == "maintenance", "field_type_mismatch")
                    if prefix == PREFIXES[1]:
                        _rule(value)
                        rules[identifier] = value
                    else:
                        _event(value)
                        events[identifier] = value
            elif key == "keex.parentEntryUuid":
                _legacy_uuid(field.value)
            elif key.startswith("keex.") and not legacy:
                issue("unknown_keex_field")
        except ContractError as error:
            issue(str(error))
    active = Counter(value["type"] for value in relations.values() if value["state"] == "active")
    for kind, count in active.items():
        maximum = CONTRACT["relations"][kind]["maxActive"]
        if maximum is not None and count > maximum:
            issue("relation_slot_conflict")
    if len(relations) > CONTRACT["limits"]["relationsPerEntry"]:
        issue("relation_limit")
    if len(events) > CONTRACT["limits"]["eventsPerEntry"]:
        issue("event_limit")
    for value in relations.values():
        if target_types is not None and value["target"] not in target_types:
            issue("missing_target", "warning")
    alias = fields.get("keex.parentEntryUuid")
    if isinstance(alias, Field):
        try:
            parent = _legacy_uuid(alias.value)
            if not legacy and record_type not in CONTRACT["relations"]["credentialOf"]["sources"]:
                issue("legacy_parent_source_type_mismatch")
            if parent == record.uuid:
                issue("self_relation")
            if target_types is not None:
                if parent not in target_types:
                    issue("missing_target", "warning")
                elif target_types[parent] == "$legacy":
                    issue("legacy_parent_type_unknown", "warning")
                elif target_types[parent] != "login":
                    issue("legacy_parent_type_mismatch")
            parents = {v["target"] for v in relations.values()
                       if v["type"] == "credentialOf" and v["state"] == "active"}
            if parents and parents != {parent}:
                issue("legacy_parent_conflict")
        except ContractError:
            pass
    retracted = {v["targetEventId"] for v in events.values() if v["kind"] == "retracted"}
    for identifier, value in events.items():
        if value["ruleId"] not in rules:
            issue("missing_rule", "warning")
        if value["kind"] == "retracted":
            target = events.get(value["targetEventId"])
            if not target:
                issue("missing_event", "warning")
            elif (target["kind"] != "completed" or target["ruleId"] != value["ruleId"]
                  or target["ruleRevision"] != value["ruleRevision"] or identifier == value["targetEventId"]):
                issue("invalid_retraction")
    for identifier, value in rules.items():
        if value["enabled"] and "timeZone" not in value:
            issue("schedule_timezone_missing", "warning")
        if value["kind"] == "manual_next" and "due" not in value:
            issue("schedule_due_unknown", "warning")
        if value["kind"] == "rolling":
            basis = value.get("basisEventId")
            event = events.get(basis)
            if event is None:
                issue("rolling_basis_unknown", "warning")
            elif event["ruleId"] != identifier:
                issue("rolling_basis_rule_mismatch")
            elif event["kind"] != "completed" or not event["effective"] or basis in retracted:
                issue("rolling_basis_inactive", "warning")
    status = "read_only" if any(i.severity == "error" for i in issues) else "legacy" if legacy else "valid"
    return Result(status, tuple(issues), record_type if record_type in CONTRACT["types"] else None)


def inspect_vault(records: Sequence[Record]) -> tuple[Result, ...]:
    """只建立当前传入合成条目的类型索引；不搜索其它文件或修复缺失引用。"""
    counts = Counter(record.uuid for record in records if isinstance(record.uuid, str))
    target_types = {}
    for record in records:
        if not isinstance(record.uuid, str) or not isinstance(record.fields, Mapping):
            continue
        marker = record.fields.get("keex.record.type")
        schema = record.fields.get("keex.record.schema")
        target_types[record.uuid] = (marker.value if isinstance(marker, Field) and isinstance(marker.value, str)
                                    and isinstance(schema, Field) and schema.value == "1"
                                    and marker.value in CONTRACT["types"] else "$legacy")
    results = []
    for record in records:
        result = inspect_record(record, target_types)
        if isinstance(record.uuid, str) and counts[record.uuid] > 1:
            result = Result("read_only", result.issues + (Issue("duplicate_entry_uuid"),), result.record_type)
        results.append(result)
    return tuple(results)
