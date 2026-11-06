package dev.keex.experiment

/** 和 Flutter 用的是同一个 libkeex_wasm_core.so，但走 JNI，不需要 Dart 也不需要 Flutter 引擎。 */
object NativeCore {
    init {
        System.loadLibrary("keex_wasm_core")
    }

    external fun open(data: ByteArray, password: String, budget: Long): Long
    external fun summary(handle: Long): String
    external fun setUsername(handle: Long, entry: String, username: String)
    external fun setKdf(handle: Long, name: String, memoryMib: Int, iterations: Int, parallelism: Int)
    external fun save(handle: Long, password: String): ByteArray
    external fun testPanic()
    external fun close(handle: Long)
}
