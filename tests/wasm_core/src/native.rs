//! 原生的壳：C ABI，给 Dart FFI 用。约定：返回 0 成功；失败时 keex_last_error 给出原因。
//! 指针都由 Dart 一侧保证有效；这里只有合成数据的实验，不是生产接口。
use crate::core::Vault;
use std::{
    cell::RefCell,
    ffi::{c_char, CStr, CString},
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

unsafe fn text<'a>(value: *const c_char) -> Result<&'a str, String> {
    CStr::from_ptr(value).to_str().map_err(|e| e.to_string())
}

/// 错误信息，属于当前线程，下一次调用前有效。
#[no_mangle]
pub extern "C" fn keex_last_error() -> *const c_char {
    LAST_ERROR.with(|slot| slot.borrow().as_ptr())
}

/// # Safety
/// `data` 指向 `length` 字节，`password` 是 NUL 结尾的 UTF-8，`out` 可写。
#[no_mangle]
pub unsafe extern "C" fn keex_vault_open(data: *const u8, length: usize, password: *const c_char, out: *mut *mut Vault) -> i32 {
    let opened = text(password).and_then(|p| Vault::open(slice::from_raw_parts(data, length), p, None));
    match opened {
        Ok(vault) => {
            *out = Box::into_raw(Box::new(vault));
            0
        }
        Err(message) => fail(message),
    }
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
    let edited = text(entry).and_then(|e| text(username).and_then(|u| (*vault).set_username(e, u)));
    edited.map_or_else(fail, |()| 0)
}

/// # Safety
/// 指针要求同上。写出的字节用 keex_bytes_free 释放。
#[no_mangle]
pub unsafe extern "C" fn keex_vault_save(vault: *const Vault, password: *const c_char, out: *mut *mut u8, out_length: *mut usize) -> i32 {
    match text(password).and_then(|p| (*vault).save(p, None)) {
        Ok(bytes) => {
            let boxed = bytes.into_boxed_slice();
            *out_length = boxed.len();
            *out = Box::into_raw(boxed).cast();
            0
        }
        Err(message) => fail(message),
    }
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
