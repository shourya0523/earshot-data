import Foundation
import CryptoKit
import Security
import EarshotCore

/// Encrypted per-call timeline (events only; never audio). AES-GCM with a
/// key held in the Keychain (this device only). Wiped when the medic signs.
final class CallStore {
    private let dir: URL = {
        let d = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("calls")
        try? FileManager.default.createDirectory(at: d, withIntermediateDirectories: true)
        var v = URLResourceValues(); v.isExcludedFromBackup = true
        var dd = d; try? dd.setResourceValues(v)
        return d
    }()

    private lazy var key: SymmetricKey = loadOrCreateKey()

    func save(_ events: [EarshotEvent], callId: String) {
        guard let data = try? JSONEncoder().encode(events), let box = try? AES.GCM.seal(data, using: key), let combined = box.combined else { return }
        try? combined.write(to: dir.appendingPathComponent("\(callId).bin"), options: [.atomic, .completeFileProtection])
    }

    func load(callId: String) -> [EarshotEvent]? {
        guard let d = try? Data(contentsOf: dir.appendingPathComponent("\(callId).bin")),
              let box = try? AES.GCM.SealedBox(combined: d), let plain = try? AES.GCM.open(box, using: key) else { return nil }
        return try? JSONDecoder().decode([EarshotEvent].self, from: plain)
    }

    func wipe(callId: String) {
        let u = dir.appendingPathComponent("\(callId).bin")
        if let h = try? FileHandle(forWritingTo: u) {   // overwrite before delete
            let n = (try? h.seekToEnd()) ?? 0
            try? h.seek(toOffset: 0); try? h.write(contentsOf: Data(count: Int(n))); try? h.close()
        }
        try? FileManager.default.removeItem(at: u)
    }

    private func loadOrCreateKey() -> SymmetricKey {
        let tag = "org.earshot.callstore.key"
        let q: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: tag, kSecReturnData as String: true]
        var out: CFTypeRef?
        if SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let d = out as? Data { return SymmetricKey(data: d) }
        let k = SymmetricKey(size: .bits256)
        let data = k.withUnsafeBytes { Data($0) }
        let add: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: tag, kSecValueData as String: data,
                                  kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly]
        SecItemAdd(add as CFDictionary, nil)
        return k
    }
}
