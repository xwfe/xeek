// K004：桌面上跑 Swift → C ABI → Rust，参数和别的候选 helper 相同，用同一把尺子量。iOS 上只验证能编译链接。
import Foundation

@main
struct Helper {
    static func main() {
        let args = CommandLine.arguments
        guard args.count == 5, let password = readLine(strippingNewline: true),
              let input = FileManager.default.contents(atPath: args[1]) else {
            FileHandle.standardError.write(Data("usage: input output entry username\n".utf8))
            exit(2)
        }
        do {
            let vault = try KeexVaultHandle(data: input, password: password)
            try vault.setUsername(entry: args[3], username: args[4])
            let output = try vault.save(password: password)
            vault.close()
            guard KeexVaultHandle.panicIsCaught() else { fatalError("panic not caught") }
            FileManager.default.createFile(atPath: args[2], contents: output)
        } catch {
            FileHandle.standardError.write(Data("\(error)\n".utf8))
            exit(1)
        }
    }
}
