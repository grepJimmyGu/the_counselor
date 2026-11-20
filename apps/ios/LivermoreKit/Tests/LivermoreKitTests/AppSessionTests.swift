import Foundation
import Testing

@testable import LivermoreKit

private let server = URL(string: "https://api.test")!

@MainActor
@Suite("AppSession")
struct AppSessionTests {
    private func make(
        store: InMemorySessionStore = InMemorySessionStore()
    ) -> (AppSession, MockTransport, InMemorySessionStore) {
        let transport = MockTransport()
        return (AppSession(serverURL: server, store: store, transport: transport), transport, store)
    }

    @Test("a successful sign-in stores the session and authorises later requests")
    func signInSuccess() async throws {
        let (session, transport, store) = make()
        transport.stub(Fixture.login, .json(status: 200, Fixture.tokenResponse))
        transport.stub(Fixture.entitlements, .json(status: 200, Fixture.strategistEntitlements))

        try await session.signIn(email: "  me@example.com \n", password: "pw")

        let expected = StoredSession(token: "tok-123", userID: "u-1", email: "me@example.com", displayName: "Jimmy")
        #expect(session.state == .signedIn(expected))
        #expect(store.load() == expected)
        // The address is trimmed before it is sent, not just before it is stored.
        let sent = try JSONSerialization.jsonObject(with: Data(transport.requests[0].body.utf8)) as? [String: String]
        #expect(sent == ["email": "me@example.com", "password": "pw"])
        // The login request itself must not carry a token; the next one must.
        #expect(transport.requests[0].authorization == nil)

        await session.refreshEntitlements()
        #expect(transport.requests[1].authorization == "Bearer tok-123")
        #expect(session.tier == "strategist")
    }

    @Test("a 401 is reported as wrong credentials and nothing is stored")
    func signInWrongPassword() async {
        let (session, transport, store) = make()
        transport.stub(Fixture.login, .json(status: 401, #"{"detail":"Invalid email or password."}"#))

        await #expect(throws: SignInError.invalidCredentials) {
            try await session.signIn(email: "me@example.com", password: "nope")
        }
        #expect(session.state == .signedOut)
        #expect(store.load() == nil)
    }

    @Test("a 422 is reported as invalid input, not as a server fault")
    func signInInvalidInput() async {
        let (session, transport, _) = make()
        transport.stub(Fixture.login, .json(status: 422, #"{"detail":[{"loc":["body","email"],"msg":"bad","type":"value_error"}]}"#))

        await #expect(throws: SignInError.invalidInput) {
            try await session.signIn(email: "not-an-email", password: "pw")
        }
    }

    @Test("other statuses and dropped connections are told apart")
    func signInServerAndNetwork() async {
        let (session, transport, _) = make()
        transport.stub(Fixture.login, .json(status: 503, "{}"))
        await #expect(throws: SignInError.server(status: 503)) {
            try await session.signIn(email: "me@example.com", password: "pw")
        }

        transport.stub(Fixture.login, .failure)
        await #expect(throws: SignInError.network) {
            try await session.signIn(email: "me@example.com", password: "pw")
        }
    }

    @Test("a stored session is restored at launch and its token is used")
    func restoresStoredSession() async {
        let (session, transport, _) = make(store: InMemorySessionStore(Fixture.saved))
        transport.stub(Fixture.entitlements, .json(status: 200, Fixture.strategistEntitlements))

        #expect(session.state == .signedIn(Fixture.saved))
        await session.refreshEntitlements()
        #expect(transport.requests.last?.authorization == "Bearer saved-tok")
    }

    @Test("signing out forgets the session and stops sending the token")
    func signOut() async {
        let (session, transport, store) = make(store: InMemorySessionStore(Fixture.saved))
        transport.stub(Fixture.login, .json(status: 401, "{}"))

        session.signOut()

        #expect(session.state == .signedOut)
        #expect(store.load() == nil)
        _ = try? await session.signIn(email: "me@example.com", password: "pw")
        #expect(transport.requests.last?.authorization == nil)
    }

    @Test("an expired token signs the user out instead of leaving dead screens")
    func expiredTokenSignsOut() async {
        let (session, transport, store) = make(store: InMemorySessionStore(Fixture.saved))
        transport.stub(Fixture.entitlements, .json(status: 401, #"{"detail":"Invalid or expired session token."}"#))

        await session.refreshEntitlements()

        #expect(session.state == .signedOut)
        #expect(store.load() == nil)
    }

    @Test("a failed entitlements load keeps the user signed in")
    func entitlementsOutageKeepsSession() async {
        let (session, transport, _) = make(store: InMemorySessionStore(Fixture.saved))
        transport.stub(Fixture.entitlements, .failure)
        await session.refreshEntitlements()
        #expect(session.isSignedIn)

        transport.stub(Fixture.entitlements, .json(status: 500, "{}"))
        await session.refreshEntitlements()
        #expect(session.isSignedIn)
    }
}
