use std::{
    fs,
    path::PathBuf,
    sync::{
        atomic::{AtomicU32, Ordering},
        Arc,
    },
    time::{Instant, SystemTime, UNIX_EPOCH},
};

use keex_wasm_core::core::Vault;
use nsh_core::prelude::*;

static NEXT_BINDING: AtomicU32 = AtomicU32::new(1);
const FIXTURE: &[u8] = include_bytes!("../../../fixtures/kdbx/v41-vault-edit2.kdbx");
const BUDGET: u64 = 128 * 1024 * 1024;
const LIMIT: u32 = 50;

fn fixture(sample: &str) -> Result<&'static [u8], String> {
    match sample {
        "baseline" => Ok(FIXTURE),
        "scale-1000" => Ok(include_bytes!(
            "../../../fixtures/kdbx/m41-scale-1000-small.kdbx"
        )),
        "scale-10000" => Ok(include_bytes!(
            "../../../fixtures/kdbx/m41-scale-10000-small.kdbx"
        )),
        _ => Err("INVALID_SAMPLE".into()),
    }
}

#[derive(Clone, JsObject)]
pub struct Ticket {
    pub binding: u32,
    pub epoch: u32,
}

#[derive(Clone, JsObject)]
pub struct Summary {
    pub id: String,
    pub title: String,
}

#[derive(Clone, JsObject)]
pub struct PageResult {
    pub rows: Vec<Summary>,
    pub core_ms: f64,
}

#[class]
/// 仅连接固定 L0 样本的合成会话。
pub struct VaultSession {
    binding: u32,
    epoch: u32,
    vault: Option<Vault>,
    edited: Option<String>,
    generation: Arc<AtomicU32>,
    sample: String,
}

impl VaultSession {
    fn check(&self, ticket: &Ticket) -> Result<(), String> {
        if self.binding != ticket.binding || self.epoch != ticket.epoch {
            return Err("STALE_SESSION".into());
        }
        Ok(())
    }

    fn ticket(&self) -> Ticket {
        Ticket {
            binding: self.binding,
            epoch: self.epoch,
        }
    }

    fn accept(&mut self, ticket: &Ticket, vault: Vault) -> Result<Ticket, String> {
        self.check(ticket)?;
        self.vault = Some(vault);
        Ok(self.ticket())
    }

    fn take(&mut self, ticket: &Ticket) -> Result<Vault, String> {
        self.check(ticket)?;
        self.vault.take().ok_or_else(|| "LOCKED_OR_BUSY".into())
    }

    /// 桌面、headless 和 iOS 模拟器写到实验 crate 的 target/outputs；Android 设备上没有构建目录，
    /// 写到 NSH 给应用的私有数据目录。iOS 真机同样没有构建目录，尚未验证，暂不改。
    fn output_dir() -> Result<PathBuf, String> {
        if cfg!(target_os = "android") {
            return data_dir()
                .map(|dir| dir.join("outputs"))
                .ok_or_else(|| "SAVE_IO".into());
        }
        Ok(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("target/outputs"))
    }
}

#[class]
impl VaultSession {
    /// 创建已锁定的独立绑定。
    pub fn new() -> Self {
        Self {
            binding: NEXT_BINDING.fetch_add(1, Ordering::Relaxed),
            epoch: 0,
            vault: None,
            edited: None,
            generation: Arc::new(AtomicU32::new(0)),
            sample: "baseline".into(),
        }
    }

    /// 撤销当前授权与全部旧 epoch。
    pub fn lock(&mut self) {
        self.epoch = self
            .epoch
            .checked_add(1)
            .expect("synthetic epoch exhausted");
        self.generation.store(self.epoch, Ordering::SeqCst);
        self.vault = None;
        self.edited = None;
    }

    /// 同步登记解锁请求，使尚未调度的任务也可被取消。
    pub fn begin_unlock(&mut self) -> Ticket {
        self.lock();
        self.ticket()
    }

    /// 只允许三份编译时固定的公开合成样本，切换即撤销旧授权。
    pub fn select_sample(&mut self, sample: String) -> Result<(), String> {
        fixture(&sample)?;
        self.lock();
        self.sample = sample;
        Ok(())
    }

    /// 在后台解锁；交付前再次验证请求 epoch。
    pub async fn unlock(
        this: Instance<Self>,
        ticket: Ticket,
        password: String,
    ) -> Result<Ticket, String> {
        this.with(|s| s.check(&ticket))?;
        let data = this.with(|s| fixture(&s.sample))?;
        let opened = blocking(move || Vault::open(data, &password, None, BUDGET))
            .await
            .map_err(|_| "WORKER_FAILED")?;
        this.with_mut(|s| {
            s.check(&ticket)?;
            let vault = opened.map_err(|_| "UNLOCK_FAILED")?;
            s.accept(&ticket, vault)
        })
    }

    /// 只返回最多 50 条 ID 和标题，标题搜索不触及秘密字段。
    pub async fn page(
        this: Instance<Self>,
        ticket: Ticket,
        query: String,
        offset: u32,
        limit: u32,
    ) -> Result<PageResult, String> {
        if limit == 0 || limit > LIMIT || query.len() > 256 {
            return Err("INVALID_PAGE".into());
        }
        let vault = this.with_mut(|s| s.take(&ticket))?;
        let (vault, rows) = blocking(move || {
            let started = Instant::now();
            let rows = vault
                .page(&query, offset as usize, limit as usize)
                .into_iter()
                .map(|row| Summary {
                    id: row.id,
                    title: row.title,
                })
                .collect::<Vec<_>>();
            let result = PageResult {
                rows,
                core_ms: started.elapsed().as_secs_f64() * 1000.0,
            };
            (vault, result)
        })
        .await
        .map_err(|_| "WORKER_FAILED")?;
        this.with_mut(|s| {
            s.accept(&ticket, vault)?;
            Ok(rows)
        })
    }

    /// 按需读取一个字段；不返回整条或整库。
    pub async fn read_field(
        this: Instance<Self>,
        ticket: Ticket,
        entry: String,
        field: String,
    ) -> Result<String, String> {
        let vault = this.with_mut(|s| s.take(&ticket))?;
        let (vault, value) = blocking(move || {
            let value = vault
                .field(&entry, &field)
                .map_err(|_| "FIELD_NOT_FOUND".to_owned());
            (vault, value)
        })
        .await
        .map_err(|_| "WORKER_FAILED")?;
        this.with_mut(|s| {
            s.accept(&ticket, vault)?;
            value
        })
    }

    /// 沿用核心的 tracked UserName 编辑语义。
    pub async fn set_username(
        this: Instance<Self>,
        ticket: Ticket,
        entry: String,
        value: String,
    ) -> Result<(), String> {
        if value.len() > 1024 {
            return Err("INVALID_FIELD".into());
        }
        let vault = this.with_mut(|s| s.take(&ticket))?;
        let (vault, result) = blocking({
            let entry = entry.clone();
            move || {
                let mut vault = vault;
                let result = vault
                    .set_username(&entry, &value)
                    .map_err(|_| "FIELD_NOT_FOUND".to_owned());
                (vault, result)
            }
        })
        .await
        .map_err(|_| "WORKER_FAILED")?;
        this.with_mut(|s| {
            s.accept(&ticket, vault)?;
            result?;
            s.edited = Some(entry);
            Ok(())
        })
    }

    /// 只在固定实验输出目录新建副本，拒绝覆盖。
    pub async fn save_copy(
        this: Instance<Self>,
        ticket: Ticket,
        password: String,
    ) -> Result<String, String> {
        let edited = this.with(|s| s.edited.clone()).ok_or("NO_EDIT")?;
        let sample = this.with(|s| s.sample.clone());
        let dir = Self::output_dir()?;
        let vault = this.with_mut(|s| s.take(&ticket))?;
        let (vault, bytes) = blocking(move || {
            let bytes = vault
                .save(&password, None)
                .map_err(|_| "SAVE_FAILED".to_owned());
            (vault, bytes)
        })
        .await
        .map_err(|_| "WORKER_FAILED")?;
        this.with(|s| s.check(&ticket))?;
        let bytes = match bytes {
            Ok(bytes) => bytes,
            Err(error) => {
                this.with_mut(|s| s.accept(&ticket, vault))?;
                return Err(error);
            }
        };
        let generation = this.with(|s| s.generation.clone());
        let output_ticket = ticket.clone();
        let copy = blocking(move || -> Result<String, String> {
            use std::io::Write;
            fs::create_dir_all(&dir).map_err(|_| "SAVE_IO")?;
            let stamp = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map_err(|_| "CLOCK")?
                .as_nanos();
            if generation.load(Ordering::SeqCst) != output_ticket.epoch {
                return Err("STALE_SESSION".into());
            }
            let name = format!("copy-{}-{stamp}.kdbx", output_ticket.binding);
            let mut file = fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(dir.join(&name))
                .map_err(|_| "SAVE_IO")?;
            file.write_all(&bytes).map_err(|_| "SAVE_IO")?;
            let receipt = serde_json::json!({"copy": name, "entry": edited, "sample": sample});
            fs::write(
                dir.join(format!("receipt-{sample}.json")),
                receipt.to_string(),
            )
            .map_err(|_| "SAVE_IO")?;
            Ok(name)
        })
        .await
        .map_err(|_| "WORKER_FAILED")?;
        this.with_mut(|s| s.accept(&ticket, vault))?;
        copy
    }
}

#[native_module("keex/vault")]
fn native(registry: &mut Registry) {
    registry.class::<VaultSession>();
}

#[cfg(test)]
mod tests;
