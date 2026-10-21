"""新增矩阵的不变量和有限差异规则；只读测试工具，不提供写入能力。"""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent.parent / "kdbx_oracle"),
               str(HERE.parent.parent / "vault_domain")]
import matrix_source as source
import vault_generate
from contract import Field, inspect_vault, record_from_pairs
from kdbx_oracle.semantic import canonicalize, diff, summarize, uuid_hex

VOLATILE = tuple(vault_generate.VOLATILE)
STANDARD = {"Title", "UserName", "Password", "URL", "Notes"}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def current_entries(decoded):
    items = [entry for group in decoded.root.iter("Group") for entry in group.findall("Entry")]
    result = {uuid_hex(entry.findtext("UUID")): entry for entry in items}
    require(len(result) == len(items), "duplicate current UUID")
    return result


def fields(entry):
    result = {}
    for string in entry.findall("String"):
        key, value = string.findtext("Key"), string.find("Value")
        require(key not in result and value is not None, "duplicate or malformed field")
        result[key] = Field(value.text or "", any(value.get(a, "").lower() == "true"
                           for a in ("Protected", "ProtectInMemory")))
    return result


def domain_results(decoded):
    records = [record_from_pairs(identifier, list(fields(entry).items()))
               for identifier, entry in current_entries(decoded).items()]
    return inspect_vault(records)


def summary(decoded):
    result = summarize(decoded)
    # 规模库的动态字段名可由源重建；清单存数量与摘要，避免数万 UUID 名称重复四遍。
    for key in ("custom_fields", "protected_custom_fields"):
        values = result.pop(key)
        result[key + "_count"] = len(values)
        result[key + "_sha256"] = digest(json.dumps(values, ensure_ascii=False).encode())
    entries = list(current_entries(decoded).values())
    maps = [fields(entry) for entry in entries]
    result["type_counts"] = dict(sorted(Counter(m.get("keex.record.type", Field("legacy")).value for m in maps).items()))
    result["relations"] = sum(key.startswith("keex.relation.") for m in maps for key in m)
    result["rules"] = sum(key.startswith("keex.lifecycle.rule.") for m in maps for key in m)
    result["events"] = sum(key.startswith("keex.lifecycle.event.") for m in maps for key in m)
    result["attachments"]["current_references"] = sum(len(e.findall("Binary")) for e in entries)
    result["attachments"]["history_references"] = sum(len(e.findall("History/Entry/Binary")) for e in entries)
    result["diagnostics"] = dict(sorted(Counter(
        r.status + ":" + ",".join(sorted(issue.code for issue in r.issues))
        for r in domain_results(decoded)).items()))
    return result


def paths(decoded):
    result = {}

    def walk(group, path):
        for entry in group.findall("Entry"):
            result[uuid_hex(entry.findtext("UUID"))] = path + "/Entry=" + uuid_hex(entry.findtext("UUID"))
        for child in group.findall("Group"):
            walk(child, path + "/Group=" + uuid_hex(child.findtext("UUID")))
    for root in decoded.root.findall("Root/Group"):
        walk(root, "KeePassFile/Root/Group=" + uuid_hex(root.findtext("UUID")))
    return result


def attachment_paths(decoded):
    out = []
    locations = paths(decoded)
    for identifier, entry in current_entries(decoded).items():
        snapshots = [(locations[identifier], entry)]
        snapshots.extend((locations[identifier] + "/History/Entry" + (f"#{i}" if i else ""), h)
                         for i, h in enumerate(entry.findall("History/Entry")))
        for path, snapshot in snapshots:
            for binary in snapshot.findall("Binary"):
                name = binary.findtext("Key").replace("%", "%25").replace("/", "%2F").replace("#", "%23")
                out.append(path + "/Binary=" + name + "/Value")
    return out


def expected_import(case, original):
    result = set()
    if case["kind"] == "passkey":
        web = ("KeePassFile/Root/Group=" + source.hex_uid("group/root")
               + "/Group=" + source.hex_uid("group/web"))
        result.add("changed/value " + web + "/IconID")
        if case["format"] == "4.1":
            result.add("removed " + web + "/CustomData/Item=keex.fixture.group/LastModificationTime")
            result.add("removed " + web + "/Entry=" + source.hex_uid("login")
                       + "/CustomData/Item=keex.fixture.entry/LastModificationTime")
    if case["format"] == "3.1":
        result.add("added KeePassFile/Meta/CustomData")
    else:
        result.add("added KeePassFile/Meta/SettingsChanged")
        result.update("changed/attrs " + path for path in attachment_paths(original))
    return result


def labels(before, after, ignore=VOLATILE):
    return sorted(item.label for item in diff(before, after, ignore=ignore))


def snapshot(decoded, entry):
    root = ET.Element("KeePassFile")
    group = ET.SubElement(ET.SubElement(root, "Root"), "Group")
    ET.SubElement(group, "UUID").text = source.xml_uuid("1" * 32)
    copied = copy.deepcopy(entry)
    for history in copied.findall("History"):
        copied.remove(history)
    group.append(copied)
    return canonicalize(replace(decoded, root=root))


def verify_original_fields(original, decoded, case, stage_index):
    before, after = current_entries(original), current_entries(decoded)
    require(before.keys() == after.keys(), "current UUID set changed")
    target, _ = source.edit_target(case)
    for identifier, entry in before.items():
        expected, actual = fields(entry), fields(after[identifier])
        if stage_index and identifier == target:
            expected["UserName"] = Field(source.EDIT_VALUES[stage_index - 1])
        require(all(actual.get(key) == value for key, value in expected.items()),
                "source field or protection changed: " + identifier)
        require(all(key in STANDARD and actual[key].value == "" for key in actual.keys() - expected.keys()),
                "unexpected field added: " + identifier)


def verify_transition(before, after, case, before_node=None, after_node=None):
    identifier, _ = source.edit_target(case)
    old = current_entries(before)[identifier]
    new = current_entries(after)[identifier]
    path = paths(before)[identifier]
    old_history, new_history = old.findall("History/Entry"), new.findall("History/Entry")
    require(len(new_history) == len(old_history) + 1, "history not appended exactly once")
    expected_history = path + ("/History" if not old_history else f"/History/Entry#{len(old_history)}")
    allowed = {path + "/String=UserName/Value", path + "/Times/LastAccessTime", path + "/Times/LastModificationTime"}
    changes = diff(before_node or canonicalize(before), after_node or canonicalize(after), ignore=VOLATILE)
    require(sum(c.path == path + "/String=UserName/Value" for c in changes) == 1, "edit missing")
    require(sum(c.path == expected_history and c.kind == "added" for c in changes) == 1, "history diff missing")
    require(all((c.kind == "changed" and c.aspect == "value" and c.path in allowed)
                or (c.kind == "added" and c.path == expected_history) for c in changes),
            "unexpected save differences: " + "; ".join(c.label for c in changes[:12]))
    require(not diff(snapshot(before, old), snapshot(after, new_history[-1])), "history is not previous current snapshot")

