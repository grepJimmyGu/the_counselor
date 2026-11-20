import Foundation
import LocalAuthentication
import Security

/// The email and password kept for signing in with Face ID.
public struct SavedCredential: Codable, Equatable, Sendable {
    public var email: String
    public var password: String

    public init(email: String, password: String) {
        self.email = email
        self.password = password
    }
}

/// The kind of biometric check this device offers.
public enum Biometry: Sendable, Equatable {
    case faceID, touchID, opticID

    public var name: String {
        switch self {
        case .faceID: "Face ID"
        case .touchID: "Touch ID"
        case .opticID: "Optic ID"
        }
    }

    public var symbol: String {
        switch self {
        case .faceID: "faceid"
        case .touchID: "touchid"
        case .opticID: "opticid"
        }
    }
}

public enum BiometricError: Error, Equatable, Sendable {
    /// The user dismissed the check, or the face did not match.
    case notAuthenticated
    /// Nothing is saved, or what was saved can no longer be read (the
    /// enrolled faces changed, which iOS treats as a different owner).
    case unavailable
}

/// Where a password is kept so that a face can stand in for typing it.
public protocol BiometricCredentialStore: Sendable {
    /// The check this device can run now, or nil if none is set up.
    var biometry: Biometry? { get }
    /// The address a password is saved for. Readable without a check.
    var savedEmail: String? { get }
    func save(_ credential: SavedCredential) throws
    /// Runs the biometric check, then returns the credential.
    func load(reason: String) async throws(BiometricError) -> SavedCredential
    func clear()
}

/// Keeps the password in the Keychain behind the device's biometric check.
///
/// `biometryCurrentSet` ties the item to the faces enrolled when it was saved:
/// enrolling another face makes it unreadable, so adding a face to a borrowed
/// phone does not open the account. `WhenPasscodeSetThisDeviceOnly` keeps it
/// out of backups and off other devices.
public struct KeychainBiometricStore: BiometricCredentialStore {
    private let service: String
    private let hintAccount = "biometric-email"
    private let secretAccount = "biometric-credential"

    public init(service: String = "com.livermorealpha.app") {
        self.service = service
    }

    private func query(_ account: String) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
    }

    public var biometry: Biometry? {
        let context = LAContext()
        guard context.canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, error: nil) else { return nil }
        switch context.biometryType {
        case .faceID: return .faceID
        case .touchID: return .touchID
        case .opticID: return .opticID
        default: return nil
        }
    }

    public var savedEmail: String? {
        var hint = query(hintAccount)
        hint[kSecReturnData as String] = true
        hint[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        guard SecItemCopyMatching(hint as CFDictionary, &item) == errSecSuccess, let data = item as? Data else {
            return nil
        }
        return String(data: data, encoding: .utf8)
    }

    public func save(_ credential: SavedCredential) throws {
        clear()
        guard let access = SecAccessControlCreateWithFlags(
            nil, kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly, .biometryCurrentSet, nil
        ) else { throw KeychainError(status: errSecParam) }
        var secret = query(secretAccount)
        secret[kSecValueData as String] = try JSONEncoder().encode(credential)
        secret[kSecAttrAccessControl as String] = access
        var status = SecItemAdd(secret as CFDictionary, nil)
        guard status == errSecSuccess else { throw KeychainError(status: status) }

        var hint = query(hintAccount)
        hint[kSecValueData as String] = Data(credential.email.utf8)
        hint[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        status = SecItemAdd(hint as CFDictionary, nil)
        guard status == errSecSuccess else {
            clear()
            throw KeychainError(status: status)
        }
    }

    public func load(reason: String) async throws(BiometricError) -> SavedCredential {
        let context = LAContext()
        // No "Enter Password" fallback: the fallback here is the sign-in form.
        context.localizedFallbackTitle = ""
        do {
            try await context.evaluatePolicy(.deviceOwnerAuthenticationWithBiometrics, localizedReason: reason)
        } catch {
            throw .notAuthenticated
        }
        var secret = query(secretAccount)
        secret[kSecReturnData as String] = true
        secret[kSecMatchLimit as String] = kSecMatchLimitOne
        // The check has just passed on this context; reusing it avoids a second prompt.
        secret[kSecUseAuthenticationContext as String] = context
        var item: CFTypeRef?
        guard SecItemCopyMatching(secret as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data,
              let credential = try? JSONDecoder().decode(SavedCredential.self, from: data)
        else {
            clear()
            throw .unavailable
        }
        return credential
    }

    public func clear() {
        SecItemDelete(query(secretAccount) as CFDictionary)
        SecItemDelete(query(hintAccount) as CFDictionary)
    }
}

/// For tests and the sample account: no Keychain, and the check always passes.
public final class InMemoryBiometricStore: BiometricCredentialStore, @unchecked Sendable {
    private let lock = NSLock()
    private var credential: SavedCredential?
    private var passes: Bool
    public let biometry: Biometry?

    public init(biometry: Biometry? = nil, saved: SavedCredential? = nil, passes: Bool = true) {
        self.biometry = biometry
        self.credential = saved
        self.passes = passes
    }

    public var savedEmail: String? { lock.withLock { credential?.email } }
    public func save(_ credential: SavedCredential) throws { lock.withLock { self.credential = credential } }
    public func clear() { lock.withLock { credential = nil } }

    public func load(reason: String) async throws(BiometricError) -> SavedCredential {
        let (passes, credential) = lock.withLock { (self.passes, self.credential) }
        guard passes else { throw .notAuthenticated }
        guard let credential else { throw .unavailable }
        return credential
    }
}
