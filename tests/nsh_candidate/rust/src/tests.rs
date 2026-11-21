use super::*;
use std::time::Instant;

const PASSWORD: &str = "keex-synthetic-V41-VAULT";

fn opened() -> Vault {
    Vault::open(FIXTURE, PASSWORD, None, BUDGET).unwrap()
}

#[test]
fn normal_page_search_field_edit_save() {
    let mut vault = opened();
    let page = vault.page("", 0, 2);
    assert_eq!(page.len(), 2);
    assert_ne!(page[0].id, vault.page("", 2, 2)[0].id);
    assert!(vault.page("impossible-title-k091", 0, 2).is_empty());
    assert!(vault.page("", usize::MAX, 2).is_empty());
    assert!(vault
        .page(&page[0].title, 0, 50)
        .iter()
        .any(|row| row.id == page[0].id));
    vault.field(&page[0].id, "UserName").unwrap();
    vault
        .set_username(&page[0].id, "synthetic-nsh-edit")
        .unwrap();
    let bytes = vault.save(PASSWORD, None).unwrap();
    let reopened = Vault::open(&bytes, PASSWORD, None, BUDGET).unwrap();
    assert_eq!(
        reopened.field(&page[0].id, "UserName").unwrap(),
        "synthetic-nsh-edit"
    );
}

#[test]
fn wrong_password_budget_and_missing_field() {
    assert!(Vault::open(FIXTURE, "wrong-synthetic", None, BUDGET).is_err());
    assert!(Vault::open(
        include_bytes!("../../../fixtures/kdbx/r41-argon2-huge.kdbx"),
        PASSWORD,
        None,
        1
    )
    .is_err());
    let vault = opened();
    let id = vault.page("", 0, 1).remove(0).id;
    assert!(vault.field(&id, "missing-k091").is_err());
    assert!(vault.field("not-a-uuid", "UserName").is_err());
}

#[test]
fn cancel_and_lock_reject_worker_completion_and_old_binding() {
    let mut session = VaultSession::new();
    let pending_unlock = session.begin_unlock();
    session.lock();
    assert_eq!(
        session.accept(&pending_unlock, opened()).err().unwrap(),
        "STALE_SESSION"
    );
    let ticket = session.ticket();
    session.accept(&ticket, opened()).unwrap();
    let worker_vault = session.take(&ticket).unwrap();
    assert_eq!(session.take(&ticket).err().unwrap(), "LOCKED_OR_BUSY");
    session.lock();
    assert_eq!(
        session.accept(&ticket, worker_vault).err().unwrap(),
        "STALE_SESSION"
    );
    assert!(session.vault.is_none());
    assert_eq!(
        VaultSession::new().check(&session.ticket()).err().unwrap(),
        "STALE_SESSION"
    );
}

#[test]
fn sample_switch_revokes_ticket_and_invalid_selection_is_rejected() {
    let mut session = VaultSession::new();
    let ticket = session.begin_unlock();
    session.accept(&ticket, opened()).unwrap();
    session.select_sample("scale-1000".into()).unwrap();
    assert_eq!(session.check(&ticket).unwrap_err(), "STALE_SESSION");
    assert!(session.vault.is_none());
    assert!(session.select_sample("../../unregistered".into()).is_err());
    assert_eq!(session.sample, "scale-1000");
}

#[test]
fn inactive_sessions_cannot_unlock_or_copy_and_errors_are_redacted() {
    let mut session = VaultSession::new();
    let ticket = session.begin_unlock();
    session.accept(&ticket, opened()).unwrap();
    assert_eq!(
        session.sensitive_error(ticket.clone()).unwrap_err(),
        "FIELD_NOT_FOUND"
    );
    session.copy_sentinel(ticket.clone()).unwrap();
    assert_eq!(session.clipboard_status(), "owned");
    session.set_active(false);
    assert_eq!(session.clipboard_status(), "empty");
    assert_eq!(session.check(&ticket).unwrap_err(), "STALE_SESSION");
    let pending = session.begin_unlock();
    assert_eq!(session.check(&pending).unwrap_err(), "SESSION_INACTIVE");
    assert!(session.copy_sentinel(pending).is_err());
    session.set_active(true);
    assert!(session.vault.is_none());
    assert_eq!(session.check(&ticket).unwrap_err(), "STALE_SESSION");
    assert!(session.arm_barrier("invalid".into()).is_err());
    session.arm_barrier("read".into()).unwrap();
    assert!(session.arm_barrier("save".into()).is_err());
    session.release_barrier();
    session.arm_barrier("save".into()).unwrap();
    session.release_barrier();
}

#[test]
fn synthetic_scale_measurements() {
    for (count, data, password) in [
        (
            1000,
            include_bytes!("../../../fixtures/kdbx/m41-scale-1000-small.kdbx").as_slice(),
            "keex-synthetic-M41-SCALE-1000-SMALL",
        ),
        (
            10000,
            include_bytes!("../../../fixtures/kdbx/m41-scale-10000-small.kdbx").as_slice(),
            "keex-synthetic-M41-SCALE-10000-SMALL",
        ),
    ] {
        let start = Instant::now();
        let vault = Vault::open(data, password, None, BUDGET).unwrap();
        let unlock = start.elapsed();
        let start = Instant::now();
        let first = vault.page("", 0, 50);
        let first_time = start.elapsed();
        let start = Instant::now();
        assert!(vault.page("impossible-title-k091", 0, 50).is_empty());
        let search = start.elapsed();
        assert_eq!(first.len(), 50);
        assert_eq!(vault.page("", 0, count + 100).len(), count);
        println!(
            "scale entries={count} unlock_ms={:.3} page50_ms={:.3} search_miss_ms={:.3}",
            unlock.as_secs_f64() * 1000.0,
            first_time.as_secs_f64() * 1000.0,
            search.as_secs_f64() * 1000.0
        );
    }
}
