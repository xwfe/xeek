//! 仅验证公开合成库；已知生命周期缺口以明确反例保留。
use keepass::{
    config::KdfConfig,
    db::{fields, CustomIconId, EntryId, EntryMut, EntryRef, Icon, Value},
    Database, DatabaseKey,
};

fn database() -> Database {
    let mut db = Database::new();
    db.config.kdf_config = KdfConfig::Aes { rounds: 1_000 };
    db
}

fn reopen(db: &Database) -> Database {
    let key = DatabaseKey::new().with_password("synthetic-preservation-only");
    let mut bytes = Vec::new();
    db.save(&mut bytes, key.clone())
        .expect("save synthetic database");
    Database::open(&mut bytes.as_slice(), key).expect("reopen synthetic database")
}

fn usernames<'a>(entries: impl Iterator<Item = EntryRef<'a>>) -> Vec<String> {
    let mut result: Vec<_> = entries
        .map(|e| e.get_username().unwrap().to_owned())
        .collect();
    result.sort();
    result
}

fn mark(mut entry: EntryMut<'_>, field: &str) {
    assert!(entry.get(field).is_none(), "a version was visited twice");
    entry.set_unprotected(field, "synthetic-visited");
}

fn assert_indexes(db: &Database, id: EntryId, stage: &str) {
    let entry = db.entry(id).unwrap();
    let history = entry.history.as_ref().unwrap().get_entries();
    assert_eq!(
        history
            .iter()
            .map(|e| e.get_username().unwrap())
            .collect::<Vec<_>>(),
        ["v0", "v1", "v2", "v3"]
    );
    assert_eq!(entry.get_username(), Some("v3"));
    for version in history.iter().chain(std::iter::once(&*entry)) {
        assert_eq!(version.get_password(), Some("synthetic-secret"));
        assert!(version.fields[fields::PASSWORD].is_protected());
    }
    let first = entry.attachment_by_name("first.bin").unwrap();
    let second = entry.attachment_by_name("second.bin").unwrap();
    assert_eq!(
        usernames(first.entries(true)),
        ["v0", "v1", "v2", "v3", "v3"],
        "{stage}"
    );
    assert_eq!(usernames(second.entries(true)), ["v2", "v3", "v3"]);
    assert_eq!(usernames(first.entries(false)), ["v3"]);
    assert_eq!(usernames(second.entries(false)), ["v3"]);
    let old_icon = history[0].icon().unwrap().custom_id().unwrap();
    let new_icon = entry.icon().unwrap().custom_id().unwrap();
    assert_eq!(
        usernames(db.custom_icon(old_icon).unwrap().entries(true)),
        ["v0", "v1"]
    );
    assert_eq!(db.custom_icon(old_icon).unwrap().entries(false).count(), 0);
    assert_eq!(
        usernames(db.custom_icon(new_icon).unwrap().entries(true)),
        ["v3", "v3"]
    );
    assert_eq!(
        usernames(db.custom_icon(new_icon).unwrap().entries(false)),
        ["v3"]
    );
}

#[test]
fn appended_history_keeps_reference_indexes_across_edits_and_reopen() {
    let mut db = database();
    let id = db
        .root_mut()
        .add_entry()
        .edit(|e| {
            e.set_unprotected(fields::USERNAME, "v0");
            e.set_protected(fields::PASSWORD, "synthetic-secret");
            e.add_attachment("first.bin", Value::protected(vec![1, 2, 3]));
            e.set_icon_custom_new(vec![4, 5, 6]);
        })
        .id();
    db.entry_mut(id).unwrap().edit_tracking(|e| {
        e.set_unprotected(fields::USERNAME, "v1");
    });
    db.entry_mut(id).unwrap().edit_tracking(|e| {
        e.set_unprotected(fields::USERNAME, "v2");
        e.as_mut().set_icon_builtin(7);
        e.as_mut()
            .add_attachment("second.bin", Value::unprotected(vec![7, 8, 9]));
    });
    db.entry_mut(id).unwrap().edit_tracking(|e| {
        e.set_unprotected(fields::USERNAME, "v3");
        e.as_mut().set_icon_custom_new(vec![10, 11, 12]);
    });
    // 保持上游契约：空的 tracked 编辑也创建一份编辑前快照。
    db.entry_mut(id).unwrap().edit_tracking(|_| {});
    assert_indexes(&db, id, "after tracked edits");

    let entry = db.entry(id).unwrap();
    let first = entry.attachment_by_name("first.bin").unwrap().id();
    let second = entry.attachment_by_name("second.bin").unwrap().id();
    let old_icon = entry.historical(0).unwrap().custom_icon().unwrap().id();
    let new_icon = entry.custom_icon().unwrap().id();
    db.attachment_mut(first)
        .unwrap()
        .foreach_entry_mut(|e| mark(e, "visit-first"), true);
    db.attachment_mut(second)
        .unwrap()
        .foreach_entry_mut(|e| mark(e, "visit-second"), true);
    db.custom_icon_mut(old_icon)
        .unwrap()
        .foreach_entry_mut(|e| mark(e, "visit-old-icon"), true);
    db.custom_icon_mut(new_icon)
        .unwrap()
        .foreach_entry_mut(|e| mark(e, "visit-new-icon"), true);

    for (stage, candidate) in [
        ("after reference traversal", &db),
        ("after reopen", &reopen(&db)),
    ] {
        assert_indexes(candidate, id, stage);
        let current = candidate.entry(id).unwrap();
        for index in 0..5 {
            let version = if index == 4 {
                candidate.entry(id).unwrap()
            } else {
                current.historical(index).unwrap()
            };
            assert!(version.get("visit-first").is_some());
            assert_eq!(version.get("visit-second").is_some(), index >= 2);
            assert_eq!(version.get("visit-old-icon").is_some(), index <= 1);
            assert_eq!(version.get("visit-new-icon").is_some(), index >= 3);
        }
    }
}

fn combined_icons() -> (Database, EntryId, CustomIconId) {
    let mut db = Database::parse(
        include_bytes!(concat!(env!("CARGO_MANIFEST_DIR"), "/dual-icons.kdbx")),
        DatabaseKey::new().with_password(include_str!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/dual-icons.password"
        ))),
    )
    .expect("open synthetic dual-icon fixture");
    let id = db.root().entry_ids().next().unwrap();
    assert_eq!(db.root().entry_ids().count(), 1);
    let icon = db.entry(id).unwrap().custom_icon().unwrap().id();
    assert_eq!(
        db.entry(id).unwrap().icon(),
        Some(&Icon::BuiltInAndCustom(0, icon))
    );
    assert_eq!(db.root().icon(), Some(&Icon::BuiltInAndCustom(48, icon)));
    db.entry_mut(id)
        .unwrap()
        .set_unprotected(fields::USERNAME, "synthetic-before");
    db.entry_mut(id).unwrap().edit_tracking(|e| {
        e.set_unprotected(fields::USERNAME, "synthetic-after");
    });
    (db, id, icon)
}

#[test]
fn removing_custom_icon_keeps_built_in_for_group_current_and_history() {
    let (db, id, icon) = combined_icons();
    let reopened = reopen(&db);
    for mut candidate in [db, reopened] {
        assert_eq!(
            candidate.custom_icon(icon).unwrap().entries(true).count(),
            2
        );
        assert_eq!(candidate.custom_icon(icon).unwrap().groups().count(), 1);
        assert_eq!(
            candidate.entry(id).unwrap().custom_icon().unwrap().id(),
            icon
        );
        assert_eq!(candidate.root().custom_icon().unwrap().id(), icon);
        candidate.custom_icon_mut(icon).unwrap().remove();
        assert!(candidate.custom_icon(icon).is_none());
        for result in [&candidate, &reopen(&candidate)] {
            let entry = result.entry(id).unwrap();
            assert_eq!(entry.icon(), Some(&Icon::BuiltIn(0)));
            assert_eq!(entry.historical(0).unwrap().icon(), Some(&Icon::BuiltIn(0)));
            assert_eq!(result.root().icon(), Some(&Icon::BuiltIn(48)));
        }
    }
}

#[test]
fn icon_setters_remove_only_the_replaced_current_references() {
    let (mut db, id, icon) = combined_icons();
    db.entry_mut(id).unwrap().set_icon_builtin(3);
    db.root_mut().set_icon_none();
    assert_eq!(db.custom_icon(icon).unwrap().entries(true).count(), 1);
    assert_eq!(db.custom_icon(icon).unwrap().entries(false).count(), 0);
    assert_eq!(db.custom_icon(icon).unwrap().groups().count(), 0);
    db.entry_mut(id).unwrap().set_icon_custom(icon).unwrap();
    assert_eq!(db.entry(id).unwrap().icon(), Some(&Icon::Custom(icon)));
    assert_eq!(db.custom_icon(icon).unwrap().entries(true).count(), 2);
    db.entry_mut(id).unwrap().set_icon_none();
    let replacement = db
        .entry_mut(id)
        .unwrap()
        .set_icon_custom_new(vec![7, 8, 9])
        .id();
    db.custom_icon_mut(icon).unwrap().remove();
    assert_eq!(
        db.entry(id).unwrap().custom_icon().unwrap().id(),
        replacement
    );
    assert_eq!(
        db.entry(id).unwrap().historical(0).unwrap().icon(),
        Some(&Icon::BuiltIn(0))
    );
}

#[test]
fn known_gap_tracked_attachment_deletion_leaves_dangling_history() {
    let mut db = database();
    let id = db.root_mut().add_entry().id();
    let attachment = db
        .entry_mut(id)
        .unwrap()
        .add_attachment("sample.bin", Value::protected(vec![1, 2, 3]))
        .id();
    db.entry_mut(id).unwrap().edit_tracking(|e| {
        e.set_unprotected(fields::USERNAME, "synthetic-edit");
    });
    db.entry_mut(id).unwrap().edit_tracking(|e| {
        e.as_mut().remove_attachment_by_name("sample.bin");
    });
    assert!(db.attachment(attachment).is_none());
    let entry = db.entry(id).unwrap();
    assert!(entry.attachment_by_name("sample.bin").is_none());
    assert_eq!(entry.history.as_ref().unwrap().get_entries().len(), 2);
    for index in 0..2 {
        // 只确认悬空引用存在，不解引用或把该损坏状态保存为样本。
        assert!(entry
            .historical(index)
            .unwrap()
            .attachment_by_name("sample.bin")
            .is_some());
    }
}
