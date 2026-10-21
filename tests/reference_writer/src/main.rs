//! 仅用于公开合成库的 KDBX 4.1 参考保存实验，不是生产 writer。
use keepass::{
    config::{DatabaseConfig, DatabaseVersion, KdfConfig, OuterCipherConfig},
    db::{fields, EntryId},
    Database, DatabaseKey,
};
use std::{
    env,
    fs::{File, OpenOptions},
    io::{self, Read, Write},
    process::ExitCode,
};

type StepResult<T> = Result<T, &'static str>;

struct Counts {
    entries: usize,
    groups: usize,
    attachments: usize,
    history_before: usize,
    history_after: usize,
    bytes: usize,
}

fn read_key() -> StepResult<DatabaseKey> {
    let mut password = String::new();
    io::stdin()
        .take(4097)
        .read_to_string(&mut password)
        .map_err(|_| "stdin_failed")?;
    if password.len() > 4096 {
        return Err("password_too_long");
    }
    if password.ends_with('\n') {
        password.pop();
        if password.ends_with('\r') {
            password.pop();
        }
    }
    if password.is_empty() || password.contains('\n') || password.contains('\r') {
        return Err("invalid_password_input");
    }
    Ok(DatabaseKey::new().with_password(&password))
}

fn configured_kdf(name: &str) -> StepResult<KdfConfig> {
    match name {
        "aes-kdf" => Ok(KdfConfig::Aes { rounds: 1_000_000 }),
        "argon2d" | "argon2id" => {
            // 只复用公开版本枚举；资源参数全部显式给定，不采用库的默认预算。
            let version = match DatabaseConfig::default().kdf_config {
                KdfConfig::Argon2 { version, .. } | KdfConfig::Argon2id { version, .. } => version,
                _ => return Err("argon2_version_unavailable"),
            };
            if version.as_u32() != 0x13 {
                return Err("unexpected_argon2_version");
            }
            if name == "argon2d" {
                Ok(KdfConfig::Argon2 {
                    iterations: 2,
                    memory: 8 * 1024 * 1024,
                    parallelism: 1,
                    version,
                })
            } else {
                Ok(KdfConfig::Argon2id {
                    iterations: 2,
                    memory: 8 * 1024 * 1024,
                    parallelism: 1,
                    version,
                })
            }
        }
        _ => Err("unsupported_kdf"),
    }
}

fn total_history(db: &Database) -> usize {
    db.iter_all_entries()
        .map(|entry| entry.history.as_ref().map_or(0, |h| h.get_entries().len()))
        .sum()
}

fn run() -> StepResult<Counts> {
    let args: Vec<String> = env::args().collect();
    if args.len() != 7 {
        return Err("invalid_arguments");
    }
    let entry_id = EntryId::from_uuid(args[3].parse().map_err(|_| "invalid_uuid")?);
    let new_username = &args[4];
    if new_username.is_empty() || new_username.len() > 4096 {
        return Err("invalid_new_username");
    }
    let kdf = configured_kdf(&args[5])?;
    let cipher = match args[6].as_str() {
        "aes" => OuterCipherConfig::AES256,
        "chacha20" => OuterCipherConfig::ChaCha20,
        _ => return Err("unsupported_cipher"),
    };
    let key = read_key()?;
    let mut source = File::open(&args[1]).map_err(|_| "input_open_failed")?;
    if source
        .metadata()
        .map_err(|_| "input_metadata_failed")?
        .len()
        > 64 * 1024 * 1024
    {
        return Err("input_exceeds_test_budget");
    }
    let mut db = Database::open(&mut source, key.clone()).map_err(|_| "database_open_failed")?;
    if !matches!(&db.config.version, DatabaseVersion::KDB4(1)) {
        return Err("input_is_not_kdbx_4_1");
    }

    let entries = db.num_entries();
    let groups = db.num_groups();
    let attachments = db.num_attachments();
    let history_before = total_history(&db);
    {
        let mut entry = db.entry_mut(entry_id).ok_or("entry_not_found")?;
        let protected = entry
            .fields
            .get(fields::USERNAME)
            .ok_or("username_field_missing")?
            .is_protected();
        if entry.get_username() == Some(new_username.as_str()) {
            return Err("username_is_unchanged");
        }
        // 一个 tracker 产生一份编辑前快照；此库将新历史插到开头，差异须如实登记。
        entry.edit_tracking(|tracked| {
            if protected {
                tracked.set_protected(fields::USERNAME, new_username.as_str());
            } else {
                tracked.set_unprotected(fields::USERNAME, new_username.as_str());
            }
        });
    }
    let history_after = total_history(&db);
    if db.num_entries() != entries
        || db.num_groups() != groups
        || db.num_attachments() != attachments
        || history_after != history_before + 1
    {
        return Err("model_count_mismatch");
    }
    db.config.kdf_config = kdf;
    db.config.outer_cipher_config = cipher;
    let mut ciphertext = Vec::new();
    db.save(&mut ciphertext, key)
        .map_err(|_| "database_save_failed")?;

    // 加密完成后才创建新目标；失败残留不可登记为成功样本，重跑仍拒绝覆盖。
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut destination = options.open(&args[2]).map_err(|_| "output_create_failed")?;
    destination
        .write_all(&ciphertext)
        .map_err(|_| "output_write_failed")?;
    destination.sync_all().map_err(|_| "output_sync_failed")?;
    Ok(Counts {
        entries,
        groups,
        attachments,
        history_before,
        history_after,
        bytes: ciphertext.len(),
    })
}

fn fail(code: &'static str) -> ExitCode {
    eprintln!("{{\"ok\":false,\"error\":\"{}\"}}", code);
    ExitCode::FAILURE
}

fn main() -> ExitCode {
    std::panic::set_hook(Box::new(|_| {}));
    match std::panic::catch_unwind(run) {
        Ok(Ok(c)) => {
            println!("{{\"ok\":true,\"entries\":{},\"groups\":{},\"attachments\":{},\"history_before\":{},\"history_after\":{},\"bytes\":{}}}",
                     c.entries, c.groups, c.attachments, c.history_before, c.history_after, c.bytes);
            ExitCode::SUCCESS
        }
        Ok(Err(code)) => fail(code),
        Err(_) => fail("library_panic"),
    }
}
