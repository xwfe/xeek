//! 浏览器的壳：wasm-bindgen 导出，错误转成 JS 异常。
use crate::core;
use wasm_bindgen::prelude::*;

fn js(message: String) -> JsError {
    JsError::new(&message)
}

#[wasm_bindgen]
pub struct Vault(core::Vault);

#[wasm_bindgen]
impl Vault {
    pub fn open(data: &[u8], password: &str, keyfile: Option<Vec<u8>>, memory_budget: Option<f64>) -> Result<Vault, JsError> {
        let budget = memory_budget.unwrap_or(0.0) as u64;
        core::Vault::open(data, password, keyfile.as_deref(), budget).map(Vault).map_err(js)
    }

    pub fn summary(&self) -> String {
        self.0.summary()
    }

    pub fn set_username(&mut self, entry: &str, username: &str) -> Result<(), JsError> {
        self.0.set_username(entry, username).map_err(js)
    }

    pub fn set_kdf(&mut self, name: &str, memory_mib: u32, iterations: u32, parallelism: u32) -> Result<(), JsError> {
        self.0.set_kdf(name, memory_mib, iterations, parallelism).map_err(js)
    }

    pub fn save(&self, password: &str, keyfile: Option<Vec<u8>>) -> Result<Vec<u8>, JsError> {
        self.0.save(password, keyfile.as_deref()).map_err(js)
    }
}
