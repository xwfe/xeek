//! Kotlin 的壳：JNI。只在 Android 上编译，给不依赖 Flutter 的原生进程用。
use crate::core::Vault;
use jni::{
    objects::{JByteArray, JClass, JString},
    sys::{jint, jlong},
    JNIEnv,
};
use std::panic::{catch_unwind, AssertUnwindSafe};

/// 错误一律抛成 Java 异常；panic 也接住，不能穿过 JNI。
fn guarded<T>(env: &mut JNIEnv, fallback: T, body: impl FnOnce(&mut JNIEnv) -> Result<T, String>) -> T {
    let outcome = catch_unwind(AssertUnwindSafe(|| body(env)));
    let message = match outcome {
        Ok(Ok(value)) => return value,
        Ok(Err(message)) => message,
        Err(_) => "PANIC: core panicked".to_owned(),
    };
    let _ = env.throw_new("java/lang/IllegalStateException", message);
    fallback
}

fn string(env: &mut JNIEnv, value: &JString) -> Result<String, String> {
    env.get_string(value).map(Into::into).map_err(|e| e.to_string())
}

#[no_mangle]
pub extern "system" fn Java_dev_keex_experiment_NativeCore_open(mut env: JNIEnv, _: JClass, data: JByteArray, password: JString, budget: jlong) -> jlong {
    guarded(&mut env, 0, |env| {
        let bytes = env.convert_byte_array(&data).map_err(|e| e.to_string())?;
        let password = string(env, &password)?;
        let vault = Vault::open(&bytes, &password, None, budget as u64)?;
        Ok(Box::into_raw(Box::new(vault)) as jlong)
    })
}

#[no_mangle]
pub extern "system" fn Java_dev_keex_experiment_NativeCore_summary<'a>(mut env: JNIEnv<'a>, _: JClass, handle: jlong) -> JString<'a> {
    let text = unsafe { &*(handle as *const Vault) }.summary();
    env.new_string(text).unwrap_or_default()
}

#[no_mangle]
pub extern "system" fn Java_dev_keex_experiment_NativeCore_setUsername(mut env: JNIEnv, _: JClass, handle: jlong, entry: JString, username: JString) {
    guarded(&mut env, (), |env| {
        let (entry, username) = (string(env, &entry)?, string(env, &username)?);
        unsafe { &mut *(handle as *mut Vault) }.set_username(&entry, &username)
    });
}

#[no_mangle]
pub extern "system" fn Java_dev_keex_experiment_NativeCore_setKdf(mut env: JNIEnv, _: JClass, handle: jlong, name: JString, memory_mib: jint, iterations: jint, parallelism: jint) {
    guarded(&mut env, (), |env| {
        let name = string(env, &name)?;
        unsafe { &mut *(handle as *mut Vault) }.set_kdf(&name, memory_mib as u32, iterations as u32, parallelism as u32)
    });
}

#[no_mangle]
pub extern "system" fn Java_dev_keex_experiment_NativeCore_save<'a>(mut env: JNIEnv<'a>, _: JClass, handle: jlong, password: JString) -> JByteArray<'a> {
    // 先在 guarded 里算出字节，再转成 Java 数组：返回值的生命周期不能借 guarded 里的 env。
    let saved = guarded(&mut env, None, |env| {
        let password = string(env, &password)?;
        unsafe { &*(handle as *const Vault) }.save(&password, None).map(Some)
    });
    match saved {
        Some(bytes) => env.byte_array_from_slice(&bytes).unwrap_or_default(),
        None => env.new_byte_array(0).unwrap_or_default(),
    }
}

#[no_mangle]
pub extern "system" fn Java_dev_keex_experiment_NativeCore_testPanic(mut env: JNIEnv, _: JClass) {
    guarded(&mut env, (), |_| -> Result<(), String> { panic!("synthetic panic") });
}

#[no_mangle]
pub extern "system" fn Java_dev_keex_experiment_NativeCore_close(_: JNIEnv, _: JClass, handle: jlong) {
    drop(unsafe { Box::from_raw(handle as *mut Vault) });
}
