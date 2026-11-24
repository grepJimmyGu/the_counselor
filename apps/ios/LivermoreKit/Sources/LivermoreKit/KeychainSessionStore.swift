import Foundation
import Security

/// Persists the session in the Keychain.
///
/// The backend token is a 30-day bearer credential for the user's account,
/// which may have a brokerage linked — it does not belong in `UserDefaults`.
/// `AfterFirstUnlockThisDeviceOnly` keeps it out of backups and off other
/// devices while still letting a background refresh read it.
public struct KeychainSessionStore: SessionStore {
    private let service: String
    private let account = "session"

    public init(service: String = "com.livermorealpha.app") {
        self.service = service
    }

    private var baseQuery: [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
    }

    public func load() -> StoredSession? {
        var query = baseQuery
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data
        else { return nil }
        return try? JSONDecoder().decode(StoredSession.self, from: data)
    }

    public func save(_ session: StoredSession) throws {
        let data = try JSONEncoder().encode(session)
        SecItemDelete(baseQuery as CFDictionary)
        var attributes = baseQuery
        attributes[kSecValueData as String] = data
        attributes[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        let status = SecItemAdd(attributes as CFDictionary, nil)
        guard status == errSecSuccess else { throw KeychainError(status: status) }
    }

    public func clear() {
        SecItemDelete(baseQuery as CFDictionary)
    }
}

public struct KeychainError: Error, Equatable {
    public let status: OSStatus
}
