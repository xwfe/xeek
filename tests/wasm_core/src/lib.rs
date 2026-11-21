//! K070：把补丁版 keepass 包成一份核心、两个壳。只处理合成库，不是生产绑定。
//!
//! 接口故意很小：打开、看摘要、改一个字段、换 KDF、保存。真实绑定的形状由 K009/K081 决定。
pub mod core;
#[cfg(target_os = "android")]
mod android;
#[cfg(not(target_arch = "wasm32"))]
mod native;
#[cfg(target_arch = "wasm32")]
mod web;
