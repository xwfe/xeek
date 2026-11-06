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

/// 文件头里写的 KDF 内存（字节），不解密就能读。没有内存参数（AES-KDF、KDBX 3）时是 0。
///
/// 恶意或超大的参数不能等到分配时才发现：WASM 上是崩溃，手机上可能被系统杀掉。只读头部，
/// 解析不了也返回 0，让后面的正常解析去报错。
pub fn kdf_memory_bytes(data: &[u8]) -> u64 {
    const KDF_PARAMETERS: u8 = 11;
    let Some(fields) = data.get(12..) else { return 0 };
    let mut position = 0;
    while let (Some(&id), Some(size)) = (fields.get(position), fields.get(position + 1..position + 5)) {
        let size = u32::from_le_bytes([size[0], size[1], size[2], size[3]]) as usize;
        let Some(value) = fields.get(position + 5..position + 5 + size) else { return 0 };
        if id == 0 {
            return 0;
        }
        if id == KDF_PARAMETERS {
            return variant_u64(value, b"M").unwrap_or(0);
        }
        position += 5 + size;
    }
    0
}

/// 从 KDBX 4 的 VariantDictionary 里取一个 UInt64。
fn variant_u64(data: &[u8], wanted: &[u8]) -> Option<u64> {
    const UINT64: u8 = 0x05;
    let mut position = 2;
    while *data.get(position)? != 0 {
        let kind = *data.get(position)?;
        let key_size = u32::from_le_bytes(data.get(position + 1..position + 5)?.try_into().ok()?) as usize;
        let key = data.get(position + 5..position + 5 + key_size)?;
        let value_start = position + 5 + key_size;
        let value_size = u32::from_le_bytes(data.get(value_start..value_start + 4)?.try_into().ok()?) as usize;
        let value = data.get(value_start + 4..value_start + 4 + value_size)?;
        if key == wanted && kind == UINT64 {
            return Some(u64::from_le_bytes(value.try_into().ok()?));
        }
        position = value_start + 4 + value_size;
    }
    None
}

pub struct Vault {
    db: Database,
}

impl Vault {
    /// 解锁。KDF 在这里跑完，会一直占着当前线程：Web 放 Worker，原生放后台 isolate。
    ///
    /// `memory_budget` 是这个进程能给 KDF 的字节数，0 表示不限。超出时不分配，直接报错。
    pub fn open(data: &[u8], password: &str, keyfile: Option<&[u8]>, memory_budget: u64) -> Result<Vault, String> {
        let needed = kdf_memory_bytes(data);
        if memory_budget != 0 && needed > memory_budget {
            return Err(format!("KDF_BUDGET: needs {needed} bytes, budget is {memory_budget}"));
        }
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
