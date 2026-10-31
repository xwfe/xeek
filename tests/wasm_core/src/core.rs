//! 浏览器和原生共用的那一份逻辑。两个壳（web.rs、native.rs）只做类型转换，
//! 所以“同一个 writer”不是约定，而是同一份代码。
use keepass::{
    config::{DatabaseConfig, KdfConfig},
    db::{fields, EntryId},
    Database, DatabaseKey,
};

fn database_key(password: &str, keyfile: Option<&[u8]>) -> Result<DatabaseKey, String> {
    let mut key = DatabaseKey::new();
    if !password.is_empty() {
        key = key.with_password(password);
    }
    if let Some(mut bytes) = keyfile {
        key = key.with_keyfile(&mut bytes).map_err(|e| e.to_string())?;
    }
    Ok(key)
}

pub struct Vault {
    db: Database,
}

impl Vault {
    /// 解锁。KDF 在这里跑完，会一直占着当前线程：Web 放 Worker，原生放后台 isolate。
    pub fn open(data: &[u8], password: &str, keyfile: Option<&[u8]>) -> Result<Vault, String> {
        let key = database_key(password, keyfile)?;
        let db = Database::parse(data, key).map_err(|e| e.to_string())?;
        Ok(Vault { db })
    }

    /// 摘要，JSON 字符串。不含任何字段值。
    pub fn summary(&self) -> String {
        let history: usize = self
            .db
            .iter_all_entries()
            .map(|entry| entry.history.as_ref().map_or(0, |h| h.get_entries().len()))
            .sum();
        // 第一个有 UserName 字段的条目，给往返测试用；只给 ID。
        let target = self
            .db
            .iter_all_entries()
            .find(|entry| entry.get_username().is_some())
            .map(|entry| entry.id().to_string());
        serde_json::json!({
            "entries": self.db.num_entries(),
            "groups": self.db.num_groups(),
            "attachments": self.db.num_attachments(),
            "history": history,
            "version": format!("{:?}", self.db.config.version),
            "kdf": format!("{:?}", self.db.config.kdf_config),
            "unknownContent": self.db.unknown_content(),
            "target": target,
        })
        .to_string()
    }

    pub fn set_username(&mut self, entry: &str, username: &str) -> Result<(), String> {
        let id = EntryId::from_uuid(entry.parse().map_err(|_| "invalid UUID".to_owned())?);
        let mut entry = self.db.entry_mut(id).ok_or_else(|| "entry not found".to_owned())?;
        entry.edit_tracking(|tracked| tracked.set_unprotected(fields::USERNAME, username));
        Ok(())
    }

    /// 换 KDF，只用来生成不同参数的测试库。memory 单位 MiB。
    pub fn set_kdf(&mut self, name: &str, memory_mib: u32, iterations: u32, parallelism: u32) -> Result<(), String> {
        let memory = u64::from(memory_mib) * 1024 * 1024;
        let iterations = u64::from(iterations);
        if name == "aes-kdf" {
            self.db.config.kdf_config = KdfConfig::Aes { rounds: iterations };
            return Ok(());
        }
        // 版本类型不公开，只能从默认配置里拿；KDBX 4 用的都是 0x13。
        let version = match DatabaseConfig::default().kdf_config {
            KdfConfig::Argon2 { version, .. } | KdfConfig::Argon2id { version, .. } => version,
            _ => return Err("default KDF is not Argon2".to_owned()),
        };
        self.db.config.kdf_config = match name {
            "argon2d" => KdfConfig::Argon2 { iterations, memory, parallelism, version },
            "argon2id" => KdfConfig::Argon2id { iterations, memory, parallelism, version },
            _ => return Err("unknown KDF".to_owned()),
        };
        Ok(())
    }

    pub fn save(&self, password: &str, keyfile: Option<&[u8]>) -> Result<Vec<u8>, String> {
        let key = database_key(password, keyfile)?;
        let mut bytes = Vec::new();
        self.db.save(&mut bytes, key).map_err(|e| e.to_string())?;
        Ok(bytes)
    }
}
