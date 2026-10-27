//! 直接调用固定上游 API，避免把本地 helper 的版本前置检查当成库行为。
use keepass::{config::DatabaseVersion, db::DatabaseSaveError, Database, DatabaseKey};
use std::{fs, path::Path};

fn open_synthetic(version: &str) -> (Database, DatabaseKey) {
    let path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../fixtures/kdbx")
        .join(format!("g{version}-rich.kdbx"));
    let bytes = fs::read(path).expect("registered synthetic fixture");
    let password = format!("合成口令-G{version}-RICH-Ünï🔑");
    let key = DatabaseKey::new().with_password(&password);
    let db = Database::open(&mut bytes.as_slice(), key.clone()).expect("open synthetic fixture");
    (db, key)
}

#[test]
fn original_3_1_save_is_unsupported_and_writes_no_bytes() {
    let (db, key) = open_synthetic("31");
    assert!(matches!(db.config.version, DatabaseVersion::KDB3(1)));
    let mut output = Vec::new();
    assert!(matches!(
        db.save(&mut output, key),
        Err(DatabaseSaveError::UnsupportedVersion)
    ));
    assert!(output.is_empty());
    assert!(matches!(db.config.version, DatabaseVersion::KDB3(1)));
}

#[test]
fn original_4_0_save_is_unsupported_and_writes_no_bytes() {
    let (db, key) = open_synthetic("40");
    assert!(matches!(db.config.version, DatabaseVersion::KDB4(0)));
    let mut output = Vec::new();
    assert!(matches!(
        db.save(&mut output, key),
        Err(DatabaseSaveError::UnsupportedVersion)
    ));
    assert!(output.is_empty());
    assert!(matches!(db.config.version, DatabaseVersion::KDB4(0)));
}

#[test]
fn original_4_1_save_reopens_without_changing_format() {
    let (db, key) = open_synthetic("41");
    assert!(matches!(db.config.version, DatabaseVersion::KDB4(1)));
    let mut output = Vec::new();
    db.save(&mut output, key.clone())
        .expect("4.1 positive control must save");
    assert!(!output.is_empty());
    let reopened =
        Database::open(&mut output.as_slice(), key).expect("reopen 4.1 positive control");
    assert!(matches!(reopened.config.version, DatabaseVersion::KDB4(1)));
    assert_eq!(reopened.num_entries(), db.num_entries());
    assert_eq!(reopened.num_groups(), db.num_groups());
    assert_eq!(reopened.num_attachments(), db.num_attachments());
}
