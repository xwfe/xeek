//! 原生的壳：C ABI，给 Dart FFI 和 Swift 用。约定：返回 0 成功；失败时 keex_last_error 给出原因。
//! 指针都由调用方保证有效；这里只有合成数据的实验，不是生产接口。
use crate::core::Vault;
use std::{
    cell::RefCell,
    ffi::{c_char, CStr, CString},
    panic::{catch_unwind, AssertUnwindSafe},
    ptr, slice,
};

thread_local! {
    static LAST_ERROR: RefCell<CString> = RefCell::new(CString::default());
}

fn fail(message: String) -> i32 {
    let text = CString::new(message.replace('\0', " ")).unwrap_or_default();
    LAST_ERROR.with(|slot| *slot.borrow_mut() = text);
    1
}

/// panic 穿过 C ABI 是未定义行为，主程序也不该因为核心的一个错误被带走，所以都接住转成错误码。
/// 内存真的不够时 Rust 直接中止，接不住：这要靠打开前的预算检查和独立进程。
fn guarded(body: impl FnOnce() -> Result<(), String>) -> i32 {
    match catch_unwind(AssertUnwindSafe(body)) {
        Ok(Ok(())) => 0,
        Ok(Err(message)) => fail(message),
        Err(_) => fail("PANIC: core panicked".to_owned()),
    }
}

unsafe fn text<'a>(value: *const c_char) -> Result<&'a str, String> {
    CStr::from_ptr(value).to_str().map_err(|e| e.to_string())
}

/// 错误信息，属于当前线程，下一次调用前有效。
#[no_mangle]
pub extern "C" fn keex_last_error() -> *const c_char {
    LAST_ERROR.with(|slot| slot.borrow().as_ptr())
}

/// `budget` 是 KDF 内存预算（字节），0 表示不限。
///
/// # Safety
/// `data` 指向 `length` 字节，`password` 是 NUL 结尾的 UTF-8，`out` 可写。
#[no_mangle]
pub unsafe extern "C" fn keex_vault_open(data: *const u8, length: usize, password: *const c_char, budget: u64, out: *mut *mut Vault) -> i32 {
    guarded(|| {
        let vault = Vault::open(slice::from_raw_parts(data, length), text(password)?, None, budget)?;
        *out = Box::into_raw(Box::new(vault));
        Ok(())
    })
}

/// # Safety
/// `vault` 来自 keex_vault_open。返回的字符串用 keex_string_free 释放。
#[no_mangle]
pub unsafe extern "C" fn keex_vault_summary(vault: *const Vault) -> *mut c_char {
    CString::new((*vault).summary()).map_or(ptr::null_mut(), CString::into_raw)
}

/// # Safety
/// 指针要求同上。
#[no_mangle]
pub unsafe extern "C" fn keex_vault_set_username(vault: *mut Vault, entry: *const c_char, username: *const c_char) -> i32 {
    guarded(|| (*vault).set_username(text(entry)?, text(username)?))
}

/// # Safety
/// 指针要求同上。写出的字节用 keex_bytes_free 释放。
#[no_mangle]
pub unsafe extern "C" fn keex_vault_save(vault: *const Vault, password: *const c_char, out: *mut *mut u8, out_length: *mut usize) -> i32 {
    guarded(|| {
        let boxed = (*vault).save(text(password)?, None)?.into_boxed_slice();
        *out_length = boxed.len();
        *out = Box::into_raw(boxed).cast();
        Ok(())
    })
}

/// 只用来生成不同 KDF 参数的测试库。
///
/// # Safety
/// 指针要求同上。
#[no_mangle]
pub unsafe extern "C" fn keex_vault_set_kdf(vault: *mut Vault, name: *const c_char, memory_mib: u32, iterations: u32, parallelism: u32) -> i32 {
    guarded(|| (*vault).set_kdf(text(name)?, memory_mib, iterations, parallelism))
}

/// 故意 panic，验证 guarded 真的接得住。
#[no_mangle]
pub extern "C" fn keex_test_panic() -> i32 {
    guarded(|| panic!("synthetic panic"))
}

/// # Safety
/// 只释放 keex_vault_save 写出的那块内存。
#[no_mangle]
pub unsafe extern "C" fn keex_bytes_free(data: *mut u8, length: usize) {
    drop(Box::from_raw(ptr::slice_from_raw_parts_mut(data, length)));
}

/// # Safety
/// 只释放 keex_vault_summary 返回的字符串。
#[no_mangle]
pub unsafe extern "C" fn keex_string_free(value: *mut c_char) {
    drop(CString::from_raw(value));
}

/// # Safety
/// `vault` 来自 keex_vault_open，释放后不能再用。
#[no_mangle]
pub unsafe extern "C" fn keex_vault_free(vault: *mut Vault) {
    drop(Box::from_raw(vault));
}
