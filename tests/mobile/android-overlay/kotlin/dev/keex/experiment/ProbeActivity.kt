package dev.keex.experiment

import android.app.Activity
import android.os.Bundle
import android.os.Process
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

/**
 * 跑在独立的 :probe 进程里，模拟系统拉起的自动填充或凭据服务：主程序可以没开，这里也没有 Flutter 引擎。
 * 驱动用 am start 传 step，每一步一个新进程，这样峰值内存才干净。只处理合成库。
 */
class ProbeActivity : Activity() {
    private val server = "http://127.0.0.1:47120"

    private fun get(path: String): ByteArray {
        val connection = URL(server + path).openConnection() as HttpURLConnection
        return connection.inputStream.use { it.readBytes() }
    }

    private fun post(path: String, body: ByteArray) {
        val connection = URL(server + path).openConnection() as HttpURLConnection
        connection.requestMethod = "POST"
        connection.doOutput = true
        connection.setFixedLengthStreamingMode(body.size)
        connection.outputStream.use { it.write(body) }
        connection.responseCode
        connection.disconnect()
    }

    private fun sample(file: String) = get("/sample?file=" + java.net.URLEncoder.encode(file, "UTF-8"))

    /** 这个进程到目前的物理内存峰值。系统杀进程看的就是这个量级。 */
    private fun peakMiB(): Long =
        File("/proc/self/status").readLines().first { it.startsWith("VmHWM") }.filter(Char::isDigit).toLong() / 1024

    private fun flutterLoaded() = File("/proc/self/maps").readText().contains("libflutter")

    private fun <T> timed(body: () -> T): Pair<T, Long> {
        val started = System.nanoTime()
        val value = body()
        return value to (System.nanoTime() - started) / 1_000_000
    }

    private fun runStep(step: String, config: JSONObject): JSONObject {
        val first = config.getJSONArray("roundTrips").getJSONObject(0)
        val result = JSONObject().put("step", step)
        val parts = step.split(":")
        when (parts[0]) {
            "environment" -> result.put("flutterLoaded", flutterLoaded()).put("pid", Process.myPid())
            "panic" -> result.put("caught", runCatching { NativeCore.testPanic() }.exceptionOrNull()?.message)
            "wrong" -> result.put("error", runCatching { NativeCore.open(sample(first.getString("file")), "synthetic-" + System.nanoTime(), 0) }.exceptionOrNull()?.message)
            "budget" -> {
                val argon2 = config.getJSONObject("argon2Sample")
                val data = sample(argon2.getString("file"))
                val refused = runCatching { NativeCore.open(data, argon2.getString("password"), 1024 * 1024) }
                result.put("error", refused.exceptionOrNull()?.message).put("peakMiB", peakMiB())
            }
            "roundtrip" -> {
                val samples = config.getJSONArray("roundTrips")
                val item = (0 until samples.length()).map(samples::getJSONObject).first { it.getString("name") == parts[1] }
                val password = item.getString("password")
                val data = sample(item.getString("file"))
                val (handle, openMs) = timed { NativeCore.open(data, password, 0) }
                val summary = JSONObject(NativeCore.summary(handle))
                NativeCore.setUsername(handle, summary.getString("target"), "synthetic-browser-edit")
                val (saved, saveMs) = timed { NativeCore.save(handle, password) }
                post("/upload?name=kotlin-android--${parts[1]}.kdbx", saved)
                if (parts[1] == first.getString("name")) {
                    for (n in 1..2) post("/upload?name=kotlin-android--random-$n.kdbx", NativeCore.save(handle, password))
                }
                NativeCore.close(handle)
                result.put("ok", true).put("target", summary.getString("target")).put("openMs", openMs).put("saveMs", saveMs)
                    .put("peakMiB", peakMiB()).put("flutterLoaded", flutterLoaded())
            }
            "ladder", "cancel" -> {
                val (name, memory, iterations, parallelism) = parts.subList(1, 5)
                val password = first.getString("password")
                val handle = NativeCore.open(sample(first.getString("file")), password, 0)
                NativeCore.setKdf(handle, name, memory.toInt(), iterations.toInt(), parallelism.toInt())
                if (parts[0] == "cancel") {
                    // 取消就是结束这个进程：KDF 中途没有退出点，主程序不受影响。
                    thread { Thread.sleep(1500); Process.killProcess(Process.myPid()) }
                }
                val (saved, saveMs) = timed { NativeCore.save(handle, password) }
                post("/upload?name=kotlin-android--kdf-$name-$memory-$iterations-$parallelism.kdbx", saved)
                val (reopened, openMs) = timed { NativeCore.open(saved, password, 0) }
                NativeCore.close(reopened)
                NativeCore.close(handle)
                result.put("ok", true).put("saveMs", saveMs).put("openMs", openMs).put("peakMiB", peakMiB())
                    .put("name", name).put("memoryMiB", memory.toInt()).put("iterations", iterations.toInt()).put("parallelism", parallelism.toInt())
            }
            else -> result.put("error", "unknown step")
        }
        return result
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val step = intent.getStringExtra("step") ?: "environment"
        thread {
            val result = try {
                runStep(step, JSONObject(String(get("/core-config.json"))))
            } catch (error: Throwable) {
                JSONObject().put("step", step).put("error", error.message)
            }
            post("/probe-step", result.toString().toByteArray())
            finish()
        }
    }
}
