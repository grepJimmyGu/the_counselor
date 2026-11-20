import Foundation
import Testing

@testable import LivermoreKit

private let server = URL(string: "https://api.test")!
private let good = "nuvmyz-Tapgo4-zimqyr"

@Suite("password rules")
struct PasswordPolicyTests {
    @Test("a strong password breaks no rule")
    func strong() {
        #expect(PasswordPolicy.violations(good, email: "jordan@example.com", displayName: "Jordan Lee").isEmpty)
    }

    // The same passwords, with the same verdicts, as the backend's
    // test_password_policy.py. The two sets of rules must not drift apart.
    @Test("each rule is reported on its own", arguments: [
        ("Short1!aB", PasswordRule.length),
        ("aB1!" + String(repeating: "xy", count: 31), .length),
        ("NUVMYZ-TAPGO4-ZIMQYR", .lowercase),
        ("nuvmyz-tapgo4-zimqyr", .uppercase),
        ("nuvmyz-Tapgoh-zimqyr", .number),
        ("nuvmyzTapgo4zimqyr", .symbol),
        ("nuvmyz-Taaago4-zimq", .repeat),
        ("nuvmyz-Tapgo-1234-z", .sequence),
        ("nuvmyz-Tdcba4-zimqyr", .sequence),
        ("nuvmyz-TaWXyZ4-zimq", .sequence),
        ("My-Livermore-4-ever", .personal),
        ("jordan-Tapgo4-zimqyr", .personal),
        ("nuvmyz-Tapgo4-Marsh!", .personal),
        ("nuvmyz-Tapgo4-Smith!", .personal),
    ])
    func oneRule(password: String, rule: PasswordRule) {
        let email = password.contains("Marsh") ? "kim.marsh@example.com" : "jordan@example.com"
        #expect(PasswordPolicy.violations(password, email: email, displayName: "Sam Smith") == [rule])
    }

    @Test("a space is allowed but is not the symbol")
    func space() {
        #expect(PasswordPolicy.violations("nuvmyz Tapgo4 zimqyr") == [.symbol])
        #expect(PasswordPolicy.violations("nuvmyz Tapgo4-zimqyr").isEmpty)
    }

    @Test("a password bcrypt would cut short is refused")
    func tooManyBytes() {
        // 42 characters, inside the limit, but 78 bytes.
        let password = "aB1!" + String(repeating: "é", count: 36) + "xy"
        #expect(password.unicodeScalars.count <= PasswordPolicy.maxLength)
        #expect(PasswordPolicy.violations(password).contains(.length))
    }

    @Test("a short name or email handle is not held against the password")
    func shortNames() {
        #expect(PasswordPolicy.violations("global-Tabor4-zimqyr", email: "al@example.com", displayName: "Bo").isEmpty)
    }

    @Test("two in a row and three in a run are fine")
    func nearMisses() {
        #expect(PasswordPolicy.violations("nuvmmz-Tapgo4-123-abc!").isEmpty)
    }

    @Test("an empty password fails every requirement and nothing else")
    func empty() {
        #expect(PasswordPolicy.violations("") == PasswordRule.required)
    }
}

@Suite("Google sign-in")
struct GoogleSignInTests {
    private let clientID = "1234-abc.apps.googleusercontent.com"

    private func make(reply: (Int, String)? = nil, record: RequestLog? = nil) -> GoogleSignIn {
        GoogleSignIn(clientID: clientID) { request in
            record?.add(request)
            guard let reply else { throw URLError(.notConnectedToInternet) }
            let response = HTTPURLResponse(url: request.url!, statusCode: reply.0, httpVersion: nil, headerFields: nil)!
            return (Data(reply.1.utf8), response)
        }!
    }

    @Test("there is no Google sign-in without a Google client ID")
    func unconfigured() {
        #expect(GoogleSignIn(clientID: nil) == nil)
        #expect(GoogleSignIn(clientID: "") == nil)
        #expect(GoogleSignIn(clientID: "not-a-google-id") == nil)
        #expect(GoogleSignIn(clientID: ".apps.googleusercontent.com") == nil)
    }

    @Test("the consent page is asked for a code, with a PKCE challenge and the app's own return address")
    func consentURL() throws {
        let google = make()
        let attempt = google.begin()
        let items = try #require(URLComponents(url: attempt.url, resolvingAgainstBaseURL: false)?.queryItems)
        let query = Dictionary(uniqueKeysWithValues: items.map { ($0.name, $0.value ?? "") })

        #expect(attempt.url.absoluteString.hasPrefix("https://accounts.google.com/o/oauth2/v2/auth?"))
        #expect(google.callbackScheme == "com.googleusercontent.apps.1234-abc")
        #expect(query["client_id"] == clientID)
        #expect(query["redirect_uri"] == "com.googleusercontent.apps.1234-abc:/oauth2redirect")
        #expect(query["response_type"] == "code")
        #expect(query["scope"] == "openid email profile")
        #expect(query["code_challenge_method"] == "S256")
        #expect(query["state"] == attempt.state)
        // The challenge is sent; the verifier it was made from is not.
        #expect(query["code_challenge"]?.count == 43)
        #expect(!attempt.url.absoluteString.contains(attempt.verifier))
        // Each attempt is its own.
        #expect(google.begin().state != attempt.state)
    }

    @Test("the code is taken only from a callback that belongs to this attempt")
    func callback() throws {
        let google = make()
        let attempt = google.begin()
        let base = "com.googleusercontent.apps.1234-abc:/oauth2redirect"

        #expect(try google.code(from: URL(string: "\(base)?state=\(attempt.state)&code=4/abc")!, for: attempt) == "4/abc")
        #expect(throws: GoogleSignInError.rejected) {
            try google.code(from: URL(string: "\(base)?state=someone-else&code=4/abc")!, for: attempt)
        }
        #expect(throws: GoogleSignInError.rejected) {
            try google.code(from: URL(string: "\(base)?state=\(attempt.state)")!, for: attempt)
        }
        #expect(throws: GoogleSignInError.cancelled) {
            try google.code(from: URL(string: "\(base)?error=access_denied&state=\(attempt.state)")!, for: attempt)
        }
    }

    @Test("the code is exchanged for an ID token, proving the attempt with its verifier")
    func exchange() async throws {
        let log = RequestLog()
        let google = make(reply: (200, #"{"access_token":"a","id_token":"header.payload.sig","expires_in":3599}"#), record: log)
        let attempt = google.begin()
        let callback = URL(string: "com.googleusercontent.apps.1234-abc:/oauth2redirect?state=\(attempt.state)&code=4/abc")!

        #expect(try await google.idToken(from: callback, for: attempt) == "header.payload.sig")

        let request = try #require(log.requests.first)
        #expect(request.url?.absoluteString == "https://oauth2.googleapis.com/token")
        #expect(request.httpMethod == "POST")
        var form = URLComponents()
        form.percentEncodedQuery = String(data: request.httpBody ?? Data(), encoding: .utf8)
        let sent = Dictionary(uniqueKeysWithValues: (form.queryItems ?? []).map { ($0.name, $0.value ?? "") })
        #expect(sent == [
            "client_id": clientID,
            "code": "4/abc",
            "code_verifier": attempt.verifier,
            "grant_type": "authorization_code",
            "redirect_uri": "com.googleusercontent.apps.1234-abc:/oauth2redirect",
        ])
    }

    @Test("a refused exchange and a dropped connection are told apart")
    func exchangeFailures() async {
        let attempt = make().begin()
        let callback = URL(string: "x:/oauth2redirect?state=\(attempt.state)&code=c")!
        await #expect(throws: GoogleSignInError.rejected) {
            try await make(reply: (400, #"{"error":"invalid_grant"}"#)).idToken(from: callback, for: attempt)
        }
        await #expect(throws: GoogleSignInError.network) {
            try await make().idToken(from: callback, for: attempt)
        }
    }

    @Test("the address shown comes from the ID token")
    func emailClaim() {
        #expect(GoogleSignIn.email(inIDToken: idToken(email: "jordan@example.com")) == "jordan@example.com")
        #expect(GoogleSignIn.email(inIDToken: "not-a-token") == nil)
    }
}

/// A token shaped like Google's: only the middle part is read by the app.
private func idToken(email: String) -> String {
    let payload = Data(#"{"sub":"g-1","email":"\#(email)","email_verified":true}"#.utf8).base64URLEncoded
    return "eyJhbGciOiJSUzI1NiJ9.\(payload).signature"
}

final class RequestLog: @unchecked Sendable {
    private let lock = NSLock()
    private var stored: [URLRequest] = []
    func add(_ request: URLRequest) { lock.withLock { stored.append(request) } }
    var requests: [URLRequest] { lock.withLock { stored } }
}

@MainActor
@Suite("signing in with Google and with Face ID")
struct AuthSessionTests {
    private static let google = "google_oauth_callback_api_auth_oauth_google_callback_post"
    private static let googleReply = """
    {"user":{"id":"u-7","handle":null,"display_name":"Jordan","avatar_url":null,"locale":"en"},"session_token":"tok-g","is_new":true}
    """

    private func make(
        biometrics: InMemoryBiometricStore = InMemoryBiometricStore()
    ) -> (AppSession, MockTransport, InMemorySessionStore) {
        let transport = MockTransport()
        let store = InMemorySessionStore()
        let session = AppSession(serverURL: server, store: store, biometrics: biometrics, transport: transport)
        return (session, transport, store)
    }

    @Test("a Google ID token signs the user in, showing the address from the token")
    func googleSuccess() async throws {
        let (session, transport, store) = make()
        transport.stub(Self.google, .json(status: 200, Self.googleReply))
        let token = idToken(email: "jordan@example.com")

        try await session.signInWithGoogle(idToken: token)

        let expected = StoredSession(token: "tok-g", userID: "u-7", email: "jordan@example.com", displayName: "Jordan")
        #expect(session.state == .signedIn(expected))
        #expect(store.load() == expected)
        let sent = try JSONSerialization.jsonObject(with: Data(transport.requests[0].body.utf8)) as? [String: String]
        #expect(sent == ["id_token": token])
        // There is no password to keep, so nothing is offered for Face ID.
        #expect(session.biometricOffer == nil)
    }

    @Test("an address that signs in with a password is sent to the password")
    func googlePasswordAccount() async {
        let (session, transport, _) = make()
        transport.stub(Self.google, .json(status: 409, #"{"detail":"An account with this email already exists."}"#))
        await #expect(throws: SignInError.emailHasPassword) {
            try await session.signInWithGoogle(idToken: idToken(email: "me@example.com"))
        }
        #expect(!session.isSignedIn)
    }

    @Test("a token the backend does not accept is a failed Google sign-in")
    func googleRefused() async {
        let (session, transport, _) = make()
        transport.stub(Self.google, .json(status: 400, #"{"detail":"Invalid Google ID token"}"#))
        await #expect(throws: SignInError.googleFailed) {
            try await session.signInWithGoogle(idToken: "bad")
        }
    }

    @Test("a typed sign-in on a device with Face ID offers to keep the password, and keeps it only if accepted")
    func offer() async throws {
        let biometrics = InMemoryBiometricStore(biometry: .faceID)
        let (session, transport, _) = make(biometrics: biometrics)
        transport.stub(Fixture.login, .json(status: 200, Fixture.tokenResponse))

        try await session.signIn(email: "me@example.com", password: "pw")
        let offer = try #require(session.biometricOffer)
        #expect(offer == SavedCredential(email: "me@example.com", password: "pw"))
        #expect(biometrics.savedEmail == nil)

        session.declineBiometricOffer()
        #expect(session.biometricOffer == nil)
        #expect(biometrics.savedEmail == nil)

        session.acceptBiometricOffer(offer)
        #expect(session.biometricEmail == "me@example.com")
        #expect(biometrics.savedEmail == "me@example.com")
    }

    @Test("a device with no Face ID is never asked")
    func noBiometry() async throws {
        let (session, transport, _) = make()
        transport.stub(Fixture.login, .json(status: 200, Fixture.tokenResponse))
        try await session.signIn(email: "me@example.com", password: "pw")
        #expect(session.biometricOffer == nil)
        #expect(session.biometry == nil)
    }

    @Test("Face ID signs in with the saved password")
    func biometricSignIn() async throws {
        let saved = SavedCredential(email: "me@example.com", password: "pw")
        let (session, transport, _) = make(biometrics: InMemoryBiometricStore(biometry: .faceID, saved: saved))
        transport.stub(Fixture.login, .json(status: 200, Fixture.tokenResponse))
        #expect(session.biometricEmail == "me@example.com")

        try await session.signInWithBiometrics()

        #expect(session.isSignedIn)
        let sent = try JSONSerialization.jsonObject(with: Data(transport.requests[0].body.utf8)) as? [String: String]
        #expect(sent == ["email": "me@example.com", "password": "pw"])
        // Already chosen for this account, so the user is not asked again.
        #expect(session.biometricOffer == nil)
    }

    @Test("a face that does not match sends nothing and reports nothing")
    func biometricDeclined() async {
        let saved = SavedCredential(email: "me@example.com", password: "pw")
        let store = InMemoryBiometricStore(biometry: .faceID, saved: saved, passes: false)
        let (session, transport, _) = make(biometrics: store)
        await #expect(throws: SignInError.cancelled) { try await session.signInWithBiometrics() }
        #expect(transport.requests.isEmpty)
        #expect(SignInError.cancelled.message.isEmpty)
        // The password is still there for the next try.
        #expect(session.biometricEmail == "me@example.com")
    }

    @Test("a saved password the account no longer accepts is thrown away")
    func biometricStale() async {
        let saved = SavedCredential(email: "me@example.com", password: "old")
        let store = InMemoryBiometricStore(biometry: .faceID, saved: saved)
        let (session, transport, _) = make(biometrics: store)
        transport.stub(Fixture.login, .json(status: 401, #"{"detail":"Invalid email or password."}"#))

        await #expect(throws: SignInError.savedPasswordRejected) { try await session.signInWithBiometrics() }
        #expect(session.biometricEmail == nil)
        #expect(store.savedEmail == nil)
    }

    @Test("signing out keeps the Face ID password; turning it off deletes it")
    func signOutKeeps() async throws {
        let saved = SavedCredential(email: "me@example.com", password: "pw")
        let store = InMemoryBiometricStore(biometry: .faceID, saved: saved)
        let (session, transport, _) = make(biometrics: store)
        transport.stub(Fixture.login, .json(status: 200, Fixture.tokenResponse))
        try await session.signInWithBiometrics()

        session.signOut()
        #expect(session.biometricEmail == "me@example.com")

        session.turnOffBiometricSignIn()
        #expect(session.biometricEmail == nil)
        #expect(store.savedEmail == nil)
    }
}

@MainActor
@Suite("forgotten password")
struct PasswordResetTests {
    private static let request = "request_password_reset_api_auth_password_reset_request_post"
    private static let confirm = "confirm_password_reset_api_auth_password_reset_confirm_post"

    private func make(
        biometrics: InMemoryBiometricStore = InMemoryBiometricStore()
    ) -> (AppSession, MockTransport, InMemorySessionStore) {
        let transport = MockTransport()
        let store = InMemorySessionStore()
        return (AppSession(serverURL: server, store: store, biometrics: biometrics, transport: transport), transport, store)
    }

    private func sent(_ transport: MockTransport, _ index: Int = 0) throws -> [String: String]? {
        try JSONSerialization.jsonObject(with: Data(transport.requests[index].body.utf8)) as? [String: String]
    }

    @Test("asking for a code sends the trimmed address and signs nobody in")
    func ask() async throws {
        let (session, transport, _) = make()
        transport.stub(Self.request, .json(status: 202, #"{"detail":"If that address has a Livermore account, a reset code is on its way."}"#))

        try await session.requestPasswordReset(email: "  kim@example.com ")

        #expect(try sent(transport) == ["email": "kim@example.com"])
        #expect(!session.isSignedIn)
    }

    @Test("an address the backend cannot read, a server fault and no connection are told apart")
    func askFailures() async {
        let (session, transport, _) = make()
        transport.stub(Self.request, .json(status: 422, #"{"detail":[{"loc":["body","email"],"msg":"bad","type":"value_error"}]}"#))
        await #expect(throws: SignInError.invalidInput) { try await session.requestPasswordReset(email: "nope") }
        transport.stub(Self.request, .json(status: 503, "{}"))
        await #expect(throws: SignInError.server(status: 503)) { try await session.requestPasswordReset(email: "kim@example.com") }
        transport.stub(Self.request, .failure)
        await #expect(throws: SignInError.network) { try await session.requestPasswordReset(email: "kim@example.com") }
    }

    @Test("the code and a new password sign the user in")
    func reset() async throws {
        let (session, transport, store) = make()
        transport.stub(Self.confirm, .json(status: 200, Fixture.tokenResponse))

        try await session.resetPassword(email: " kim@example.com", code: "482913", newPassword: good)

        #expect(try sent(transport) == ["email": "kim@example.com", "code": "482913", "new_password": good])
        #expect(session.isSignedIn)
        #expect(store.load()?.email == "kim@example.com")
    }

    @Test("a wrong or expired code is reported in the backend's words")
    func wrongCode() async {
        let (session, transport, _) = make()
        let reason = "That code is wrong or has expired. Ask for a new one."
        transport.stub(Self.confirm, .json(status: 400, #"{"detail":"\#(reason)","code":"invalid_code","failed":[]}"#))
        await #expect(throws: SignInError.resetCodeRejected(reason)) {
            try await session.resetPassword(email: "kim@example.com", code: "000000", newPassword: good)
        }
        #expect(!session.isSignedIn)
    }

    @Test("a password that breaks a rule is stopped on the device; one the backend refuses is reported")
    func badPassword() async {
        let (session, transport, _) = make()
        await #expect(throws: SignInError.weakPassword) {
            try await session.resetPassword(email: "kim@example.com", code: "482913", newPassword: "short")
        }
        #expect(transport.requests.isEmpty)

        let reason = "That password has appeared in a known data breach. Choose a different one."
        transport.stub(Self.confirm, .json(status: 400, #"{"detail":"\#(reason)","code":"breached_password","failed":[]}"#))
        await #expect(throws: SignInError.passwordRejected(reason)) {
            try await session.resetPassword(email: "kim@example.com", code: "482913", newPassword: good)
        }
    }

    @Test("a password kept for Face ID is replaced by the new one")
    func replacesSavedPassword() async throws {
        let biometrics = InMemoryBiometricStore(biometry: .faceID, saved: SavedCredential(email: "kim@example.com", password: "old"))
        let (session, transport, _) = make(biometrics: biometrics)
        transport.stub(Self.confirm, .json(status: 200, Fixture.tokenResponse))

        try await session.resetPassword(email: "kim@example.com", code: "482913", newPassword: good)

        // Already chosen for this account: updated without asking again.
        #expect(session.biometricOffer == nil)
        #expect(try await biometrics.load(reason: "") == SavedCredential(email: "kim@example.com", password: good))
    }
}

@MainActor
@Suite("changing the password")
struct ChangePasswordTests {
    private static let change = "change_password_api_auth_password_change_post"
    private static let reply = """
    {"user":{"id":"u-9","handle":null,"display_name":null,"avatar_url":null,"locale":"en"},"session_token":"tok-new"}
    """

    private func make(
        biometrics: InMemoryBiometricStore = InMemoryBiometricStore()
    ) -> (AppSession, MockTransport, InMemorySessionStore) {
        let transport = MockTransport()
        let store = InMemorySessionStore(Fixture.saved)
        return (AppSession(serverURL: server, store: store, biometrics: biometrics, transport: transport), transport, store)
    }

    @Test("the change is sent with the old session and the reply's session replaces it")
    func change() async throws {
        let (session, transport, store) = make()
        transport.stub(Self.change, .json(status: 200, Self.reply))
        transport.stub(Fixture.entitlements, .json(status: 200, Fixture.strategistEntitlements))

        try await session.changePassword(current: "old-pw", new: good)

        let sent = try JSONSerialization.jsonObject(with: Data(transport.requests[0].body.utf8)) as? [String: String]
        #expect(sent == ["current_password": "old-pw", "new_password": good])
        #expect(transport.requests[0].authorization == "Bearer saved-tok")
        // Still signed in, as the same address, on the new session.
        #expect(store.load()?.token == "tok-new")
        #expect(store.load()?.email == "saved@example.com")
        await session.refreshEntitlements()
        #expect(transport.requests[1].authorization == "Bearer tok-new")
    }

    @Test("a refusal is reported in the backend's words and the session is kept")
    func refused() async {
        let (session, transport, store) = make()
        let reason = "That is not your current password."
        transport.stub(Self.change, .json(status: 400, #"{"detail":"\#(reason)","code":"wrong_password","failed":[]}"#))
        await #expect(throws: SignInError.passwordRejected(reason)) {
            try await session.changePassword(current: "nope", new: good)
        }
        #expect(store.load()?.token == "saved-tok")
        #expect(session.isSignedIn)
    }

    @Test("a new password that breaks a rule is stopped on the device")
    func weak() async {
        let (session, transport, _) = make()
        await #expect(throws: SignInError.weakPassword) {
            try await session.changePassword(current: "old-pw", new: "short")
        }
        // The account's own address counts against it.
        await #expect(throws: SignInError.weakPassword) {
            try await session.changePassword(current: "old-pw", new: "saved-Tapgo4-zimqyr")
        }
        #expect(transport.requests.isEmpty)
    }

    @Test("a session that has ended signs the app out instead of reporting an error")
    func sessionEnded() async {
        let (session, transport, store) = make()
        transport.stub(Self.change, .json(status: 401, #"{"detail":"Invalid or expired session token."}"#))
        await #expect(throws: SignInError.cancelled) {
            try await session.changePassword(current: "old-pw", new: good)
        }
        #expect(!session.isSignedIn)
        #expect(store.load() == nil)
    }

    @Test("a password kept for Face ID follows the change; a device that keeps none is not asked")
    func faceID() async throws {
        let saved = SavedCredential(email: "saved@example.com", password: "old-pw")
        let biometrics = InMemoryBiometricStore(biometry: .faceID, saved: saved)
        let (session, transport, _) = make(biometrics: biometrics)
        transport.stub(Self.change, .json(status: 200, Self.reply))
        try await session.changePassword(current: "old-pw", new: good)
        #expect(try await biometrics.load(reason: "") == SavedCredential(email: "saved@example.com", password: good))

        let none = InMemoryBiometricStore(biometry: .faceID)
        let (other, otherTransport, _) = make(biometrics: none)
        otherTransport.stub(Self.change, .json(status: 200, Self.reply))
        try await other.changePassword(current: "old-pw", new: good)
        #expect(other.biometricOffer == nil)
        #expect(none.savedEmail == nil)
    }
}

@Suite("errors on screens that are not signing in")
struct TaskErrorMessageTests {
    @Test("a 404 says the server is behind the app, and does not say to try again")
    func serverBehind() {
        // Seen 2026-11-19: the reset screen against a backend without the
        // reset endpoints said "couldn't sign you in (error 404). Try again
        // in a moment", which was wrong on both counts.
        let message = SignInError.server(status: 404).message(whileTryingTo: "send the code")
        #expect(message.contains("send the code"))
        #expect(message.contains("server update"))
        #expect(!message.contains("sign you in"))
        #expect(!message.contains("Try again in a moment"))
    }

    @Test("other server faults name the task and are worth retrying")
    func otherFaults() {
        let message = SignInError.server(status: 503).message(whileTryingTo: "change your password")
        #expect(message == "Livermore couldn't change your password (error 503). Try again in a moment.")
    }

    @Test("every other error keeps its own words")
    func unchanged() {
        #expect(SignInError.network.message(whileTryingTo: "send the code") == SignInError.network.message)
        #expect(SignInError.passwordRejected("No.").message(whileTryingTo: "send the code") == "No.")
    }
}

