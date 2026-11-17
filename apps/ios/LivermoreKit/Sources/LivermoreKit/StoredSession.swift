import Foundation

/// What the app remembers about a signed-in user between launches.
///
/// `email` is kept here because the API's `UserPublic` does not return it —
/// it is the address the user typed at sign-in.
public struct StoredSession: Codable, Equatable, Sendable {
    public var token: String
    public var userID: String
    public var email: String
    public var displayName: String?

    public init(token: String, userID: String, email: String, displayName: String?) {
        self.token = token
        self.userID = userID
        self.email = email
        self.displayName = displayName
    }
}

/// Where the session is persisted. The app uses the Keychain; tests use memory.
public protocol SessionStore: Sendable {
    func load() -> StoredSession?
    func save(_ session: StoredSession) throws
    func clear()
}

public final class InMemorySessionStore: SessionStore, @unchecked Sendable {
    private let lock = NSLock()
    private var value: StoredSession?

    public init(_ initial: StoredSession? = nil) { value = initial }

    public func load() -> StoredSession? { lock.withLock { value } }
    public func save(_ session: StoredSession) throws { lock.withLock { value = session } }
    public func clear() { lock.withLock { value = nil } }
}
