use keepass::{
    db::{fields, EntryId, Value},
    Database, DatabaseKey,
};
use std::{fs::OpenOptions, path::PathBuf};

fn save_new(db: &Database, name: &str) -> Database {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(format!("{name}.kdbx"));
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&path)
        .unwrap();
    let key = DatabaseKey::new().with_password(include_str!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/password"
    )));
    db.save(&mut file, key.clone()).unwrap();
    drop(file);
    Database::open(&mut std::fs::File::open(path).unwrap(), key).unwrap()
}

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
    assert_eq!(
        dest.entry(id).unwrap().get_username(),
        Some(before.as_str())
    );
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
    save_new(&dest, "history-dest");
    save_new(&source, "history-source");
    dest.merge(&source).unwrap();
    let entry = dest.entry(id).unwrap();
    assert_eq!(entry.get_username(), Some("synthetic-source"));
    assert!(entry.history.as_ref().unwrap().get_entries().is_empty());
    let reopened = save_new(&dest, "history-merged");
    assert_eq!(
        reopened.entry(id).unwrap().get_username(),
        Some("synthetic-source")
    );
    assert!(reopened
        .entry(id)
        .unwrap()
        .history
        .as_ref()
        .unwrap()
        .get_entries()
        .is_empty());
    save_new(&reopened, "history-reopened");
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
    save_new(&dest, "attachment-dest");
    save_new(&source, "attachment-source");
    dest.merge(&source).unwrap();
    let entry = dest.entry(id).unwrap();
    assert_eq!(entry.get_username(), Some("synthetic-source"));
    assert!(entry.attachment_by_name("source-only.txt").is_none());
    let reopened = save_new(&dest, "attachment-merged");
    assert_eq!(
        reopened.entry(id).unwrap().get_username(),
        Some("synthetic-source")
    );
    assert!(reopened
        .entry(id)
        .unwrap()
        .attachment_by_name("source-only.txt")
        .is_none());
    save_new(&reopened, "attachment-reopened");
}

#[cfg(feature = "preservation_probe")]
#[test]
fn merge_reverses_preservation_history_even_when_destination_current_wins() {
    let mut source = Database::new();
    source.config.kdf_config = keepass::config::KdfConfig::Aes { rounds: 1_000 };
    let id = source
        .root_mut()
        .add_entry()
        .edit(|e| {
            e.set_unprotected(fields::USERNAME, "h0");
        })
        .id();
    let mut dest = save_new(&source, "order-base");
    for (index, name) in ["h0", "h1", "h2"].into_iter().enumerate() {
        {
            let mut entry = source.entry_mut(id).unwrap();
            entry.set_unprotected(fields::USERNAME, name);
            entry.times.last_modification =
                Some(format!("2025-01-0{}T00:00:00", index + 1).parse().unwrap());
        }
        source.entry_mut(id).unwrap().edit_tracking(|e| {
            e.set_unprotected(fields::USERNAME, "synthetic-current");
        });
    }
    source.entry_mut(id).unwrap().times.last_modification =
        Some("2025-01-04T00:00:00".parse().unwrap());
    dest.entry_mut(id).unwrap().times.last_modification =
        Some("2025-01-05T00:00:00".parse().unwrap());
    fn names(db: &Database, id: EntryId) -> Vec<String> {
        db.entry(id)
            .unwrap()
            .history
            .as_ref()
            .unwrap()
            .get_entries()
            .iter()
            .map(|entry| entry.get_username().unwrap().to_owned())
            .collect()
    }
    assert_eq!(names(&source, id), ["h0", "h1", "h2"]);
    dest.merge(&source).unwrap();
    assert_eq!(dest.entry(id).unwrap().get_username(), Some("h0"));
    assert_eq!(names(&dest, id), ["h2", "h1", "h0"]);
    let reopened = save_new(&dest, "order-merged");
    assert_eq!(names(&reopened, id), ["h2", "h1", "h0"]);
}
