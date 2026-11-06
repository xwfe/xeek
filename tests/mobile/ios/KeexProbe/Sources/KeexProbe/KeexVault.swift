// K004：Swift 调 Rust 核心。没有 Flutter、没有 Dart，凭据扩展就是这样用的。只处理合成库。
import Foundation
import KeexCoreC

public struct KeexError: Error, CustomStringConvertible {
    public let description: String

    static func last() -> KeexError {
        KeexError(description: keex_last_error().map { String(cString: $0) } ?? "unknown")
    }
}

public final class KeexVaultHandle {
    private var handle: OpaquePointer?

    /// `budget` 是 KDF 最多能用的字节数：iOS 扩展的内存上限很低，超了要拒绝，不能等系统杀进程。
    public init(data: Data, password: String, budget: UInt64 = 0) throws {
        var out: OpaquePointer?
        let status = data.withUnsafeBytes { raw in
            keex_vault_open(raw.bindMemory(to: UInt8.self).baseAddress, data.count, password, budget, &out)
        }
        guard status == 0 else { throw KeexError.last() }
        handle = out
    }

    deinit { close() }

    /// 锁库：释放核心里的解密内容。之后不能再用。
    public func close() {
        if let handle { keex_vault_free(handle) }
        handle = nil
    }

    public func summary() -> String {
        let text = keex_vault_summary(handle)!
        defer { keex_string_free(text) }
        return String(cString: text)
    }

    public func setUsername(entry: String, username: String) throws {
        guard keex_vault_set_username(handle, entry, username) == 0 else { throw KeexError.last() }
    }

    public func save(password: String) throws -> Data {
        var bytes: UnsafeMutablePointer<UInt8>?
        var length = 0
        guard keex_vault_save(handle, password, &bytes, &length) == 0 else { throw KeexError.last() }
        defer { keex_bytes_free(bytes, length) }
        return Data(bytes: bytes!, count: length)
    }

    public static func panicIsCaught() -> Bool {
        keex_test_panic() != 0 && String(cString: keex_last_error()).hasPrefix("PANIC")
    }
}
