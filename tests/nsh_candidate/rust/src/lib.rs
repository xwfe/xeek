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

mod controls;
use controls::{ClipboardPolicy, DeliveryGate};

const SENTINEL: &str = "SYNTHETIC-K092-PRIVATE-BOUNDARY";

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
    clipboard: ClipboardPolicy,
    barrier: Option<(String, Arc<DeliveryGate>)>,
    active: bool,
}

impl VaultSession {
    fn check(&self, ticket: &Ticket) -> Result<(), String> {
        if self.binding != ticket.binding || self.epoch != ticket.epoch {
            return Err("STALE_SESSION".into());
        }
        if !self.active {
            return Err("SESSION_INACTIVE".into());
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

    fn gate(&self, operation: &str) -> Option<Arc<DeliveryGate>> {
        self.barrier
            .as_ref()
            .filter(|(name, _)| name == operation)
            .map(|(_, gate)| gate.clone())
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
            clipboard: ClipboardPolicy::default(),
            barrier: None,
            active: true,
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
        self.clipboard.clear_owned();
    }

    /// 同步登记解锁请求，使尚未调度的任务也可被取消。
    pub fn begin_unlock(&mut self) -> Ticket {
        self.lock();
        self.ticket()
    }

    pub fn set_active(&mut self, active: bool) {
        if !active && self.active {
            self.lock();
        }
        self.active = active;
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
        let gate = this.with(|s| s.gate("unlock"));
        let opened = blocking(move || {
            let opened = Vault::open(data, &password, None, BUDGET);
            if let Some(gate) = gate {
                gate.pause();
            }
            opened
        })
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
        let gate = this.with(|s| s.gate("page"));
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
            if let Some(gate) = gate {
                gate.pause();
            }
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
        let gate = this.with(|s| s.gate("read"));
        let (vault, value) = blocking(move || {
            let value = vault
                .field(&entry, &field)
                .map_err(|_| "FIELD_NOT_FOUND".to_owned());
            if let Some(gate) = gate {
                gate.pause();
            }
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
        let gate = this.with(|s| s.gate("save"));
        let (vault, bytes) = blocking(move || {
            let bytes = vault
                .save(&password, None)
                .map_err(|_| "SAVE_FAILED".to_owned());
            if let Some(gate) = gate {
                gate.pause();
            }
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

    /// 仅实验：后台交付屏障不阻塞 UI 线程。
    pub fn arm_barrier(&mut self, operation: String) -> Result<(), String> {
        if !["unlock", "read", "page", "save", "copy"].contains(&operation.as_str()) {
            return Err("INVALID_BARRIER".into());
        }
        if self
            .barrier
            .as_ref()
            .is_some_and(|(_, gate)| !gate.released())
        {
            return Err("BARRIER_BUSY".into());
        }
        self.barrier = Some((operation, Arc::new(DeliveryGate::default())));
        Ok(())
    }

    pub async fn wait_barrier(this: Instance<Self>) -> Result<(), String> {
        let gate = this
            .with(|s| s.barrier.as_ref().map(|(_, gate)| gate.clone()))
            .ok_or("NO_BARRIER")?;
        blocking(move || gate.wait_entered())
            .await
            .map_err(|_| "WORKER_FAILED")?
    }

    pub fn release_barrier(&mut self) {
        if let Some((_, gate)) = &self.barrier {
            gate.release();
        }
    }

    /// 只把字段从核心交给私有 MemoryClipboard，不经过 JS。
    pub async fn copy_secret(
        this: Instance<Self>,
        ticket: Ticket,
        entry: String,
    ) -> Result<u32, String> {
        let vault = this.with_mut(|s| s.take(&ticket))?;
        let gate = this.with(|s| s.gate("copy"));
        let (vault, text) = blocking(move || {
            let text = vault
                .field(&entry, "Password")
                .map_err(|_| "FIELD_NOT_FOUND".to_owned());
            if let Some(gate) = gate {
                gate.pause();
            }
            (vault, text)
        })
        .await
        .map_err(|_| "WORKER_FAILED")?;
        this.with_mut(|s| {
            s.accept(&ticket, vault)?;
            Ok(s.clipboard.copy(text?))
        })
    }

    pub fn clipboard_status(&self) -> String {
        self.clipboard.status()
    }
    pub fn clipboard_external_copy(&mut self, same: bool) {
        self.clipboard.external_copy(same);
    }
    pub fn advance_clipboard_clock(&mut self, milliseconds: u32) -> Result<(), String> {
        self.clipboard.advance(milliseconds)
    }
    pub fn expire_clipboard_version(&mut self, version: u32) {
        self.clipboard.expire(version);
    }

    /// 故意让核心处理无效秘密标识，但仅交付固定错误码。
    pub fn sensitive_error(&self, ticket: Ticket) -> Result<(), String> {
        self.check(&ticket)?;
        let vault = self.vault.as_ref().ok_or("LOCKED_OR_BUSY")?;
        vault
            .field(SENTINEL, SENTINEL)
            .map(|_| ())
            .map_err(|_| "FIELD_NOT_FOUND".into())
    }

    pub fn copy_sentinel(&mut self, ticket: Ticket) -> Result<u32, String> {
        self.check(&ticket)?;
        self.vault.as_ref().ok_or("LOCKED_OR_BUSY")?;
        Ok(self.clipboard.copy(SENTINEL.into()))
    }
}

#[native_module("keex/vault")]
fn native(registry: &mut Registry) {
    registry.class::<VaultSession>();
}

#[cfg(test)]
mod tests;
