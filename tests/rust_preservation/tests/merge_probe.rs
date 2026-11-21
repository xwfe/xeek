use keepass::{
    db::{fields, EntryId, Value},
    Database, DatabaseKey,
};

fn base() -> (Database, EntryId) {
    let db = Database::parse(
        include_bytes!(concat!(env!("CARGO_MANIFEST_DIR"), "/official.kdbx")),
        DatabaseKey::new().with_password(include_str!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/password"
        ))),
    )
    .unwrap();
    let id = EntryId::from_uuid(
        include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/entry-id"))
            .parse()
            .unwrap(),
    );
    (db, id)
}

fn stamp(db: &mut Database, id: EntryId, source: bool) {
    let time = if source {
        "2025-01-02T00:00:00"
    } else {
        "2025-01-01T00:00:00"
    };
    db.entry_mut(id).unwrap().times.last_modification = Some(time.parse().unwrap());
}

#[test]
fn unchanged_same_uuid_is_noop() {
    let (mut dest, id) = base();
    let (source, _) = base();
    let before = dest.entry(id).unwrap().get_username().unwrap().to_owned();
    let log = dest.merge(&source).unwrap();
    assert!(log.events.is_empty());
    assert_eq!(dest.entry(id).unwrap().get_username(), Some(before.as_str()));
}

#[test]
fn equal_current_timestamp_with_divergence_is_error_not_history_warning() {
    let (mut dest, id) = base();
    let (mut source, _) = base();
    source
        .entry_mut(id)
        .unwrap()
        .set_unprotected(fields::USERNAME, "synthetic-source");
    let error = dest.merge(&source).unwrap_err();
    assert!(format!("{error:?}").contains("EntryModificationTimeNotUpdated"));
    assert_eq!(
        dest.entry(id).unwrap().get_username(),
        Some("synthetic-official-base")
    );
}

#[test]
fn newer_source_with_empty_history_loses_destination_snapshot() {
    let (mut dest, id) = base();
    let (mut source, _) = base();
    stamp(&mut dest, id, false);
    stamp(&mut source, id, true);
    source
        .entry_mut(id)
        .unwrap()
        .set_unprotected(fields::USERNAME, "synthetic-source");
    dest.merge(&source).unwrap();
    let entry = dest.entry(id).unwrap();
    assert_eq!(entry.get_username(), Some("synthetic-source"));
    assert!(entry.history.as_ref().unwrap().get_entries().is_empty());
}

#[test]
fn newer_source_attachment_is_not_applied() {
    let (mut dest, id) = base();
    let (mut source, _) = base();
    stamp(&mut dest, id, false);
    stamp(&mut source, id, true);
    source.entry_mut(id).unwrap().add_attachment(
        "source-only.txt",
        Value::Unprotected(b"synthetic-source-attachment".to_vec()),
    );
    source
        .entry_mut(id)
        .unwrap()
        .set_unprotected(fields::USERNAME, "synthetic-source");
    assert!(source
        .entry(id)
        .unwrap()
        .attachment_by_name("source-only.txt")
        .is_some());
    dest.merge(&source).unwrap();
    let entry = dest.entry(id).unwrap();
    assert_eq!(entry.get_username(), Some("synthetic-source"));
    assert!(entry.attachment_by_name("source-only.txt").is_none());
}
