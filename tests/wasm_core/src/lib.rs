//! K070：把补丁版 keepass 包成浏览器能调用的接口。只处理合成库，不是生产绑定。
//!
//! 接口故意很小：打开、看摘要、改一个字段、换 KDF、保存。真实绑定的形状由 K009/K081 决定。
use keepass::{
    config::{DatabaseConfig, KdfConfig},
    db::{fields, EntryId},
    Database, DatabaseKey,
};
use wasm_bindgen::prelude::*;

fn database_key(password: &str, keyfile: Option<Vec<u8>>) -> Result<DatabaseKey, JsError> {
    let mut key = DatabaseKey::new();
    if !password.is_empty() {
        key = key.with_password(password);
    }
    if let Some(bytes) = keyfile {
        key = key
            .with_keyfile(&mut bytes.as_slice())
            .map_err(|e| JsError::new(&e.to_string()))?;
    }
    Ok(key)
}

#[wasm_bindgen]
pub struct Vault {
    db: Database,
}

#[wasm_bindgen]
impl Vault {
    /// 解锁。KDF 在这里跑完，会一直占着当前线程，所以只能放在 Worker 里调用。
    pub fn open(data: &[u8], password: &str, keyfile: Option<Vec<u8>>) -> Result<Vault, JsError> {
        let key = database_key(password, keyfile)?;
        let db = Database::parse(data, key).map_err(|e| JsError::new(&e.to_string()))?;
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

    pub fn set_username(&mut self, entry: &str, username: &str) -> Result<(), JsError> {
        let id: EntryId = EntryId::from_uuid(entry.parse().map_err(|_| JsError::new("invalid UUID"))?);
        let mut entry = self.db.entry_mut(id).ok_or_else(|| JsError::new("entry not found"))?;
        entry.edit_tracking(|tracked| tracked.set_unprotected(fields::USERNAME, username));
        Ok(())
    }

    /// 换 KDF，只用来生成不同参数的测试库。memory 单位 MiB。
    pub fn set_kdf(&mut self, name: &str, memory_mib: u32, iterations: u32, parallelism: u32) -> Result<(), JsError> {
        let memory = u64::from(memory_mib) * 1024 * 1024;
        let iterations = u64::from(iterations);
        if name == "aes-kdf" {
            self.db.config.kdf_config = KdfConfig::Aes { rounds: iterations };
            return Ok(());
        }
        // 版本类型不公开，只能从默认配置里拿；KDBX 4 用的都是 0x13。
        let version = match DatabaseConfig::default().kdf_config {
            KdfConfig::Argon2 { version, .. } | KdfConfig::Argon2id { version, .. } => version,
            _ => return Err(JsError::new("default KDF is not Argon2")),
        };
        self.db.config.kdf_config = match name {
            "argon2d" => KdfConfig::Argon2 { iterations, memory, parallelism, version },
            "argon2id" => KdfConfig::Argon2id { iterations, memory, parallelism, version },
            _ => return Err(JsError::new("unknown KDF")),
        };
        Ok(())
    }

    pub fn save(&self, password: &str, keyfile: Option<Vec<u8>>) -> Result<Vec<u8>, JsError> {
        let key = database_key(password, keyfile)?;
        let mut bytes = Vec::new();
        self.db.save(&mut bytes, key).map_err(|e| JsError::new(&e.to_string()))?;
        Ok(bytes)
    }
}
