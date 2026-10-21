"""K068 行为反例：只操作硬编码合成字段，不写 KDBX 或联系任何服务。"""
import base64
import copy
import json
import unittest

from contract import (
    CONTRACT, ContractError, Field, Record, atomic_group_for, inspect_record,
    inspect_vault, record_from_pairs, requires_reveal,
)

A, B, C, D = (str(n) * 32 for n in (1, 2, 3, 4))
R1, R2, E1, E2 = (str(n) * 32 for n in (5, 6, 7, 8))
PROV = {"recordedAt": "2026-10-18T00:00:00Z", "source": "user_entry", "confidence": "user_asserted"}


def encoded(value, protected=True):
    return Field(json.dumps(value, ensure_ascii=False, separators=(",", ":")), protected)


def record(kind="payment_card", entry_id=A, extra=None):
    return Record(entry_id, {
        "Title": Field("合成资料"),
        "keex.record.schema": Field("1"),
        "keex.record.type": Field(kind),
        **(extra or {}),
    })


def relation(kind="paidBy", target=B, state="active", **kwargs):
    return encoded({"type": kind, "target": target, "state": state, **kwargs})


def rule(kind="calendar", **changes):
    data = {
        "version": 1, "revision": 1, "kind": kind, "enabled": True,
        "timeZone": "Asia/Tokyo", **PROV,
    }
    if kind == "calendar":
        data.update(anchor={"precision": "date", "value": "2026-01-31"}, unit="month", interval=1, overflow="clamp")
    elif kind == "once":
        data["due"] = {"precision": "date", "value": "2026-10-31"}
    elif kind == "rolling":
        data.update(unit="day", interval=90)
    data.update(changes)
    return data


def event(kind="completed", **changes):
    data = {"version": 1, "kind": kind, "ruleId": R1, "ruleRevision": 1,
            "occurredAt": "2026-10-17T08:00:00Z", **PROV}
    data.update({"effective": True} if kind == "completed" else {"targetEventId": E1})
    data.update(changes)
    return data


class ContractAssertions(unittest.TestCase):
    def check(self, sample, status="valid", code=None, targets=None):
        before = copy.deepcopy(sample)
        result = inspect_record(sample, targets)
        self.assertEqual(result.status, status, result)
        if code:
            self.assertIn(code, [item.code for item in result.issues])
        self.assertEqual(sample, before, "检查不能规范化、清除或修正原始输入")
        return result


class RecordContractTest(ContractAssertions):
    def test_all_types_allow_minimum_incomplete_record(self):
        for kind in CONTRACT["types"]:
            with self.subTest(kind=kind):
                self.check(record(kind))

    def test_data_only_esim_needs_no_number_iccid_eid_or_line(self):
        self.check(record("sim_profile", extra={"keex.telecom.profileKind": Field("esim")}))

    def test_line_identity_does_not_depend_on_number(self):
        self.check(record("telecom_line"))
        self.check(record("telecom_line", extra={"keex.telecom.number": Field("", True)}))

    def test_no_marker_is_legacy_and_mixed_credentials_are_preserved(self):
        self.check(Record(A, {"Title": Field("合成混合条目"), "Password": Field("synthetic-password", True),
                             "KPEX_PASSKEY_PRIVATE_KEY_PEM": Field("synthetic-preservation-only", True),
                             "keex.parentEntryUuid": Field(B)}), "legacy")

    def test_partial_marker_is_read_only(self):
        for key in ("keex.record.schema", "keex.record.type"):
            sample = record()
            del sample.fields[key]
            self.check(sample, "read_only", "missing_marker")

    def test_future_and_malformed_schema_are_read_only(self):
        for value in ("2", "01", "", "1.0", "synthetic-future", 1, []):
            sample = record(extra={"keex.record.schema": Field(value)})
            self.check(sample, "read_only", "unknown_schema")

    def test_unknown_and_non_text_type_are_read_only_without_crash(self):
        for value in ("future_type", [], {}, None, 1):
            self.check(record(extra={"keex.record.type": Field(value)}), "read_only", "unknown_type")

    def test_missing_title_does_not_fabricate_one(self):
        sample = record()
        del sample.fields["Title"]
        self.check(sample, "read_only", "missing_title")

    def test_explicit_empty_text_is_not_missing_but_empty_struct_is_invalid(self):
        self.check(record(extra={"keex.finance.number": Field("", True)}))
        self.check(record(extra={"keex.finance.balance": Field("", True)}), "read_only", "empty_value")

    def test_foreign_extensions_preserve_original_protection(self):
        self.check(record(extra={"future.vendor": Field("合成未知原文", True)}))
        self.check(record(extra={"future.vendor": Field("", False)}))

    def test_unknown_keex_field_or_enum_is_read_only(self):
        self.check(record(extra={"keex.finance.future": Field("合成未来字段", True)}), "read_only", "unknown_keex_field")
        self.check(record(extra={"keex.finance.form": Field("future_form")}), "read_only", "unknown_enum")

    def test_type_change_does_not_silently_reinterpret_foreign_domain(self):
        self.check(record("sim_profile", extra={"keex.finance.number": Field("synthetic-card", True)}),
                   "read_only", "field_type_mismatch")

    def test_known_sensitive_field_cannot_become_summary(self):
        sample = record(extra={"keex.finance.number": Field("synthetic-card", False)})
        self.check(sample, "read_only", "protection_required")
        self.assertTrue(requires_reveal("keex.finance.number", sample.fields["keex.finance.number"]))
        self.assertTrue(requires_reveal("Password", Field("synthetic", False)))
        self.assertTrue(requires_reveal("unknown.extension", Field("synthetic", False)))
        self.assertTrue(requires_reveal("Title", Field("合成隐藏标题", True)))

    def test_fields_are_independent_reveal_units(self):
        sample = record(extra={"keex.finance.number": Field("synthetic-number", True),
                               "keex.finance.cvv": Field("synthetic-cvv", True),
                               "keex.finance.pin": Field("synthetic-pin", True)})
        self.check(sample)
        self.assertEqual(atomic_group_for("keex.finance.number"), ("keex.finance.number",))
        self.assertNotIn("keex.finance.cvv", atomic_group_for("keex.finance.number"))

    def test_duplicate_xml_string_key_is_rejected_before_map(self):
        with self.assertRaisesRegex(ContractError, "^duplicate_field$"):
            record_from_pairs(A, [("keex.finance.number", Field("synthetic-a", True)),
                                  ("keex.finance.number", Field("synthetic-b", True))])

    def test_invalid_uuid_and_duplicate_entry_id_are_read_only(self):
        for value in ("0" * 32, "bad", "A" * 32, "../synthetic"):
            self.check(record(entry_id=value), "read_only", "invalid_uuid")
        results = inspect_vault([record(entry_id=A), record(entry_id=A)])
        self.assertTrue(all(r.status == "read_only" and IssueCodes(r, "duplicate_entry_uuid") for r in results))

    def test_error_codes_contain_no_synthetic_secret_or_unknown_key(self):
        secret = "SYNTHETIC-NEVER-IN-DIAGNOSTIC"
        result = self.check(record(extra={"keex." + secret: Field(secret, True)}), "read_only")
        self.assertNotIn(secret, repr(result))
        self.assertFalse(hasattr(result, "fields"))

    def test_field_and_json_resource_limits(self):
        self.check(record(extra={"keex.finance.number": Field("x" * 65537, True)}), "read_only", "field_limit")
        self.check(record(extra={"keex.finance.balance": Field("[" * 18 + "0" + "]" * 18, True)}), "read_only", "json_limit")

    def test_unicode_nul_and_invalid_protection_are_read_only(self):
        for value, code in (("\ud800", "invalid_unicode"), ("synthetic\0x", "nul_value")):
            self.check(record(extra={"keex.finance.number": Field(value, True)}), "read_only", code)
        self.check(record(extra={"keex.finance.number": Field("synthetic", "True")}), "read_only", "invalid_field")


def IssueCodes(result, code):
    return any(i.code == code for i in result.issues)


class MoneyAndProvenanceTest(ContractAssertions):
    def balance(self, amount="19.90", **changes):
        return record(extra={"keex.finance.balance": encoded({"amount": amount, "currency": "USD", **PROV, **changes})})

    def test_decimal_is_exact_even_beyond_binary_float_integer_precision(self):
        for amount in ("0", "0.00", "19.90", "-19.90", "9007199254740993.123456789012345678"):
            with self.subTest(amount=amount):
                self.check(self.balance(amount))

    def test_exponent_float_nonfinite_and_noncanonical_decimal_are_rejected(self):
        for amount in ("1e3", "NaN", "Infinity", "01.20", "+1", "1.", ".5", "-0", "-0.00", 0.1):
            with self.subTest(amount=repr(amount)):
                self.check(self.balance(amount), "read_only")

    def test_unknown_currency_and_excess_precision_preserve_raw(self):
        self.check(self.balance(currency="ZZZ"), "read_only", "unsupported_currency")
        self.check(self.balance("0." + "1" * 19), "read_only", "unsupported_decimal_precision")

    def test_provenance_is_required_with_money(self):
        sample = self.balance()
        data = json.loads(sample.fields["keex.finance.balance"].value)
        for name in ("recordedAt", "source", "confidence", "currency"):
            broken = data.copy()
            del broken[name]
            self.check(record(extra={"keex.finance.balance": encoded(broken)}), "read_only", "missing_member")
        self.assertEqual(atomic_group_for("keex.finance.balance"), ("keex.finance.balance",))

    def test_false_verification_is_not_upgraded(self):
        self.check(self.balance(source="user_entry", confidence="user_verified"), "read_only", "unverified_source")
        self.check(self.balance(source="user_verified", confidence="user_verified"))

    def test_unknown_json_member_duplicate_key_and_null_cannot_be_dropped(self):
        self.check(self.balance(futureEvidence={"synthetic": True}), "read_only", "unknown_member")
        raw = '{"amount":"1","amount":"2","currency":"USD","source":"user_entry","confidence":"unknown","recordedAt":"2026-10-18T00:00:00Z"}'
        self.check(record(extra={"keex.finance.balance": Field(raw, True)}), "read_only", "duplicate_member")
        self.check(record(extra={"keex.finance.balance": Field("null", True)}), "read_only", "expected_object")

    def test_amount_and_billing_period_share_one_group(self):
        billing = {"amount": "9.90", "currency": "USD", "period": {
            "unit": "month", "interval": 1, "anchor": {"precision": "date", "value": "2026-01-31"},
            "timeZone": "Asia/Tokyo", "overflow": "clamp",
        }, **PROV}
        self.check(record("subscription", extra={"keex.subscription.billing": encoded(billing)}))
        self.assertEqual(atomic_group_for("keex.subscription.billing"), ("keex.subscription.billing",))

    def test_unverified_sms_claim_is_not_supported_state(self):
        self.check(record("telecom_plan", extra={"keex.telecom.smsCapability": encoded({"value": "unknown", **PROV})}))
        self.check(record("telecom_plan", extra={"keex.telecom.smsCapability": encoded({"value": "yes", **PROV})}),
                   "read_only", "capability_not_verified")

    def test_snapshot_does_not_conflate_source_with_real_time_service(self):
        self.check(record("finance_account", extra={"keex.record.serviceState": encoded({"value": "inactive", **PROV})}))
        self.check(record("finance_account", extra={"keex.record.serviceState": encoded({"value": "confirmed_by_bank", **PROV})}),
                   "read_only", "unknown_enum")

    def test_remaining_units_are_explicit_and_exact(self):
        self.check(record("telecom_plan", extra={"keex.telecom.remaining": encoded({"value": "1024", "unit": "byte", **PROV})}))
        self.check(record("telecom_plan", extra={"keex.telecom.remaining": encoded({"value": "1", "unit": "MB", **PROV})}),
                   "read_only", "unknown_enum")


class DateContractTest(ContractAssertions):
    def date_sample(self, value):
        return record("document", extra={"keex.document.expires": encoded(value)})

    def test_extreme_local_dates_are_diagnosed_without_overflow(self):
        for value, zone in (("0001-01-01T00:00:00", "Asia/Tokyo"),
                            ("9999-12-31T23:59:59", "America/New_York")):
            self.check(self.date_sample({"precision": "local", "value": value, "timeZone": zone}),
                       "read_only", "unsupported_time_range")

    def test_month_date_and_instant_keep_distinct_precision(self):
        for value in ({"precision": "month", "value": "2030-02"},
                      {"precision": "date", "value": "2028-02-29"},
                      {"precision": "instant", "value": "2026-10-18T00:00:00.001Z"}):
            self.check(self.date_sample(value))
        self.check(record(extra={"keex.finance.expires": encoded({"precision": "date", "value": "2030-02-28"})}),
                   "read_only", "month_precision_required")

    def test_invalid_calendar_date_is_not_normalized(self):
        for precision, value in (("month", "2026-13"), ("date", "2026-02-29"), ("date", "2026-1-1"),
                                 ("instant", "2026-10-18T00:00:60Z"), ("instant", "2026-10-18T00:00:00+00:00")):
            self.check(self.date_sample({"precision": precision, "value": value}), "read_only")

    def test_nonexistent_dst_time_is_rejected(self):
        self.check(self.date_sample({"precision": "local", "value": "2026-03-08T02:30:00", "timeZone": "America/New_York"}),
                   "read_only", "nonexistent_local_time")

    def test_ambiguous_dst_time_needs_explicit_fold(self):
        value = {"precision": "local", "value": "2026-11-01T01:30:00", "timeZone": "America/New_York"}
        self.check(self.date_sample(value), "read_only", "ambiguous_local_time")
        self.check(self.date_sample({**value, "fold": 0}))
        self.check(self.date_sample({**value, "fold": 1}))

    def test_missing_unknown_timezone_or_fold_not_guessed(self):
        self.check(self.date_sample({"precision": "local", "value": "2026-10-18T09:00:00"}), "read_only", "missing_timezone")
        self.check(self.date_sample({"precision": "local", "value": "2026-10-18T09:00:00", "timeZone": "Synthetic/Unknown"}),
                   "read_only", "unknown_timezone")
        self.check(self.date_sample({"precision": "local", "value": "2026-10-18T09:00:00", "timeZone": "Asia/Tokyo", "fold": 1}),
                   "read_only", "invalid_fold")

    def test_card_month_cannot_gain_utc_midnight(self):
        self.check(record(extra={"keex.finance.expires": encoded({"precision": "month", "value": "2030-02", "timeZone": "UTC"})}),
                   "read_only", "precision_parameters")


class RelationContractTest(ContractAssertions):
    def test_legacy_parent_alone_is_checked_without_rewriting(self):
        self.check(Record(A, {"keex.parentEntryUuid": Field(A)}), "read_only", "self_relation")
        self.check(Record(A, {"keex.parentEntryUuid": Field(B)}), "legacy", "missing_target", {})
        self.check(Record(A, {"keex.parentEntryUuid": Field(B)}),
                   "read_only", "legacy_parent_type_mismatch", {B: "payment_card"})

    def test_non_text_keys_and_vault_shapes_return_controlled_diagnostics(self):
        with self.assertRaisesRegex(ContractError, "^expected_text$"):
            record_from_pairs(A, [([], Field("synthetic"))])
        results = inspect_vault([Record([], {}), Record(B, []),
                                 record(extra={"keex.record.type": Field([])})])
        self.assertTrue(all(result.status == "read_only" for result in results))

    def test_two_new_ids_cannot_create_two_current_payment_cards(self):
        sample = record("subscription", extra={"keex.relation." + R1: relation(target=B),
                                               "keex.relation." + R2: relation(target=C)})
        self.check(sample, "read_only", "relation_slot_conflict", {B: "payment_card", C: "payment_card"})

    def test_old_payment_history_and_one_current_card_are_valid(self):
        self.check(record("subscription", extra={"keex.relation." + R1: relation(target=B, state="historical"),
                                                 "keex.relation." + R2: relation(target=C)}),
                   targets={B: "payment_card", C: "payment_card"})

    def test_independent_slots_and_multiple_verification_sources(self):
        self.check(record("login", extra={"keex.relation." + R1: relation("recoveredBy", B),
                                         "keex.relation." + R2: relation("recoveredBy", C)}),
                   targets={B: "telecom_line", C: "telecom_line"})

    def test_relation_source_target_direction_and_self_reference(self):
        self.check(record("sim_profile", extra={"keex.relation." + R1: relation("usesProfile", B)}),
                   "read_only", "relation_source_type", {B: "telecom_line"})
        self.check(record("subscription", extra={"keex.relation." + R1: relation(target=B)}),
                   "read_only", "relation_target_type", {B: "sim_profile"})
        self.check(record("login", extra={"keex.relation." + R1: relation("credentialOf", A)}),
                   "read_only", "self_relation")

    def test_missing_target_is_retained_without_rebinding(self):
        result = self.check(record("subscription", extra={"keex.relation." + R1: relation()}),
                            code="missing_target", targets={})
        self.assertEqual(result.issues[0].severity, "warning")

    def test_cross_vault_reference_member_is_not_accepted(self):
        self.check(record("subscription", extra={"keex.relation." + R1: relation(vaultId="synthetic-other")}),
                   "read_only", "unknown_member")

    def test_relation_id_and_unknown_state_are_read_only(self):
        self.check(record("subscription", extra={"keex.relation.synthetic": relation()}), "read_only", "invalid_uuid")
        self.check(record("subscription", extra={"keex.relation." + R1: relation(state="future")}), "read_only", "unknown_enum")

    def test_relation_interval_compares_instants_numerically(self):
        beginning = {"precision": "instant", "value": "2026-10-18T00:00:00Z"}
        later = {"precision": "instant", "value": "2026-10-18T00:00:00.1Z"}
        self.check(record("subscription", extra={"keex.relation." + R1: relation(validFrom=beginning, validUntil=later)}))
        self.check(record("subscription", extra={"keex.relation." + R1: relation(validFrom=later, validUntil=beginning)}),
                   "read_only", "invalid_validity")

    def test_old_parent_supported_encodings_and_conflict_are_preserved(self):
        forms = (B, B.upper(), f"{B[:8]}-{B[8:12]}-{B[12:16]}-{B[16:20]}-{B[20:]}",
                 base64.b64encode(bytes.fromhex(B)).decode())
        for alias in forms:
            self.check(record("login", extra={"keex.parentEntryUuid": Field(alias),
                                              "keex.relation." + R1: relation("credentialOf", B)}))
        self.check(record("login", extra={"keex.parentEntryUuid": Field(B),
                                         "keex.relation." + R1: relation("credentialOf", C)}),
                   "read_only", "legacy_parent_conflict")

    def test_typed_alias_has_same_source_scope_as_credential_relation(self):
        self.check(record("payment_card", extra={"keex.parentEntryUuid": Field(B)}),
                   "read_only", "legacy_parent_source_type_mismatch", {B: "login"})
        self.check(record("login", extra={"keex.parentEntryUuid": Field(B)}), targets={B: "login"})

    def test_unknown_keex_prefix_without_markers_is_read_only(self):
        sample = Record(A, {"Title": Field("synthetic"), "keex.future.opaque": Field("synthetic", True)})
        self.check(sample, "read_only", "unknown_keex_field")
        self.check(Record(A, {"Title": Field("synthetic"), "Plugin.Future": Field("synthetic", True)}), "legacy")
        self.check(Record(A, {"Title": Field("synthetic"), "keex.parentEntryUuid": Field(B)}),
                   "legacy", targets={B: "login"})

    def test_finite_reference_cycle_needs_no_recursive_resolution(self):
        samples = [record("document", A, {"keex.relation." + R1: relation("documentedBy", B)}),
                   record("document", B, {"keex.relation." + R2: relation("documentedBy", A)})]
        self.assertEqual([r.status for r in inspect_vault(samples)], ["valid", "valid"])


class LifecycleContractTest(ContractAssertions):
    def test_rule_and_date_cannot_disagree_about_business_timezone(self):
        self.check(record("maintenance", extra={"keex.lifecycle.rule." + R1:
                   encoded(rule("once", due={"precision": "date", "value": "2026-10-31", "timeZone": "UTC"}))}),
                   "read_only", "conflicting_timezone")
        self.check(record("maintenance", extra={"keex.lifecycle.rule." + R1:
                   encoded(rule(anchor={"precision": "date", "value": "2026-01-31", "timeZone": "UTC"}))}),
                   "read_only", "conflicting_timezone")

    def test_calendar_keeps_original_month_end_and_leap_anchor(self):
        for value in ("2026-01-31", "2028-02-29"):
            self.check(record("maintenance", extra={"keex.lifecycle.rule." + R1:
                                                    encoded(rule(anchor={"precision": "date", "value": value}))}))
        self.assertEqual(atomic_group_for("keex.lifecycle.rule." + R1), ("keex.lifecycle.rule." + R1,))

    def test_no_timezone_and_no_rolling_basis_stay_explicitly_unknown(self):
        data = rule("rolling")
        del data["timeZone"]
        result = self.check(record("maintenance", extra={"keex.lifecycle.rule." + R1: encoded(data)}))
        self.assertTrue(IssueCodes(result, "schedule_timezone_missing"))
        self.assertTrue(IssueCodes(result, "rolling_basis_unknown"))

    def test_manual_date_unset_is_not_fabricated(self):
        self.check(record("maintenance", extra={"keex.lifecycle.rule." + R1: encoded(rule("manual_next"))}),
                   code="schedule_due_unknown")

    def test_lead_is_calendar_days_and_no_24h_conversion(self):
        self.check(record("maintenance", extra={"keex.lifecycle.rule." + R1: encoded(rule(lead={"unit": "calendar_day", "value": 1}))}))
        self.check(record("maintenance", extra={"keex.lifecycle.rule." + R1: encoded(rule(lead={"unit": "hour", "value": 24}))}),
                   "read_only", "unknown_enum")

    def test_notification_click_is_not_a_completion_event(self):
        self.check(record("maintenance", extra={"keex.lifecycle.event." + E1: encoded(event(kind="notification_clicked"))}),
                   "read_only", "unknown_event_kind")

    def test_event_occurrence_and_recording_times_are_independent(self):
        sample = record("maintenance", extra={
            "keex.lifecycle.rule." + R1: encoded(rule("rolling", basisEventId=E1)),
            "keex.lifecycle.event." + E1: encoded(event()),
        })
        self.check(sample)
        decoded = json.loads(sample.fields["keex.lifecycle.event." + E1].value)
        self.assertNotEqual(decoded["occurredAt"], decoded["recordedAt"])

    def test_retraction_preserves_original_completion_and_disables_basis(self):
        self.check(record("maintenance", extra={
            "keex.lifecycle.rule." + R1: encoded(rule("rolling", basisEventId=E1)),
            "keex.lifecycle.event." + E1: encoded(event()),
            "keex.lifecycle.event." + E2: encoded(event("retracted")),
        }), code="rolling_basis_inactive")

    def test_basis_cannot_be_borrowed_from_another_rule(self):
        self.check(record("maintenance", extra={
            "keex.lifecycle.rule." + R1: encoded(rule("rolling", basisEventId=E1)),
            "keex.lifecycle.rule." + R2: encoded(rule("once")),
            "keex.lifecycle.event." + E1: encoded(event(ruleId=R2)),
        }), "read_only", "rolling_basis_rule_mismatch")

    def test_retraction_must_reference_same_rule_and_revision(self):
        self.check(record("maintenance", extra={
            "keex.lifecycle.rule." + R1: encoded(rule()),
            "keex.lifecycle.event." + E1: encoded(event()),
            "keex.lifecycle.event." + E2: encoded(event("retracted", ruleRevision=2)),
        }), "read_only", "invalid_retraction")

    def test_rule_versions_boolean_numbers_and_unknown_members_do_not_sneak_through(self):
        for changes in ({"version": 2}, {"version": True}, {"interval": True}, {"revision": 0}, {"futureAction": "synthetic"}):
            self.check(record("maintenance", extra={"keex.lifecycle.rule." + R1: encoded(rule(**changes))}), "read_only")

    def test_event_evidence_is_an_attachment_reference_not_external_path(self):
        self.check(record("maintenance", extra={
            "keex.lifecycle.rule." + R1: encoded(rule()),
            "keex.lifecycle.event." + E1: encoded(event(evidence={"entry": B, "attachment": "合成凭据.txt"})),
        }))
        self.check(record("maintenance", extra={
            "keex.lifecycle.event." + E1: encoded(event(evidence={"url": "https://synthetic.example/proof"})),
        }), "read_only", "missing_member")

    def test_lifecycle_fields_cannot_be_attached_to_arbitrary_record_type(self):
        self.check(record("payment_card", extra={"keex.lifecycle.rule." + R1: encoded(rule())}),
                   "read_only", "field_type_mismatch")


if __name__ == "__main__":
    unittest.main()
