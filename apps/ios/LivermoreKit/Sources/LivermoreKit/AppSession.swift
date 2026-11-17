import Foundation
import LivermoreAPI
import Observation
import OpenAPIRuntime
import OpenAPIURLSession

public enum SignInError: Error, Equatable, Sendable {
    /// 401 — the backend's "Invalid email or password."
    case invalidCredentials
    /// 422 — the request was malformed (e.g. not an email address).
    case invalidInput
    /// Any other HTTP status.
    case server(status: Int)
    /// The request never completed.
    case network

    public var message: String {
        switch self {
        case .invalidCredentials: "That email and password don't match an account."
        case .invalidInput: "Enter a valid email address and password."
        case .server(let status): "Livermore couldn't sign you in (error \(status)). Try again in a moment."
        case .network: "Couldn't reach Livermore. Check your connection and try again."
        }
    }
}

/// The signed-in user and the API client every screen shares.
@MainActor
@Observable
public final class AppSession {
    public enum State: Equatable, Sendable {
        case signedOut
        case signedIn(StoredSession)
    }

    public private(set) var state: State
    /// The plan tier ("scout", "strategist", "quant"), once loaded.
    public private(set) var tier: String?

    /// True only for the debug build's `-demo` session, whose account data is
    /// made up. Screens that show that data say so.
    public internal(set) var isDemo = false

    /// Shared by every feature. Carries the bearer token automatically.
    public let client: Client

    /// Live prices for the symbols on screen, shared by every screen.
    public let quotes: QuoteStore

    private let store: any SessionStore
    private let tokens = TokenBox()

    public init(
        serverURL: URL = APIEnvironment.production,
        store: any SessionStore = KeychainSessionStore(),
        transport: any ClientTransport = URLSessionTransport()
    ) {
        self.store = store
        let client = Client.livermore(serverURL: serverURL, transport: transport, tokens: tokens)
        self.client = client
        self.quotes = QuoteStore { symbols in
            try await ResearchService(client: client).quotes(symbols)
        }
        if let saved = store.load() {
            tokens.set(saved.token)
            state = .signedIn(saved)
        } else {
            state = .signedOut
        }
    }

    /// Company research calls, sharing this session's client and token.
    public var research: ResearchService { ResearchService(client: client) }

    /// The user's strategies and tracked positions. Needs a signed-in session.
    public var strategies: StrategyService { StrategyService(client: client) }

    /// Backtests and saving. Runs work signed out, within the anonymous limit.
    public var backtests: BacktestService { BacktestService(client: client) }

    public var isSignedIn: Bool {
        if case .signedIn = state { true } else { false }
    }

    public func signIn(email: String, password: String) async throws(SignInError) {
        let email = email.trimmingCharacters(in: .whitespacesAndNewlines)
        let output: Operations.PasswordLoginApiAuthPasswordLoginPost.Output
        do {
            output = try await client.passwordLoginApiAuthPasswordLoginPost(
                body: .json(.init(email: email, password: password))
            )
        } catch {
            throw .network
        }

        switch output {
        case .ok(let ok):
            guard case .json(let token) = ok.body else { throw .server(status: 200) }
            let session = StoredSession(
                token: token.sessionToken,
                userID: token.user.id,
                email: email,
                displayName: token.user.displayName
            )
            // A Keychain failure must not strand the user on the sign-in
            // screen with correct credentials: they are signed in for this
            // launch and asked again on the next.
            try? store.save(session)
            tokens.set(session.token)
            state = .signedIn(session)
        case .unprocessableContent:
            throw .invalidInput
        case .undocumented(let status, _):
            throw status == 401 ? .invalidCredentials : .server(status: status)
        }
    }

    public func signOut() {
        store.clear()
        tokens.set(nil)
        tier = nil
        state = .signedOut
    }

    /// Loads the plan tier. A 401 here means the stored token has expired
    /// (the backend mints them for 30 days and there is no refresh a device
    /// can call yet), so the user is signed out rather than left on screens
    /// that will all fail.
    public func refreshEntitlements() async {
        guard isSignedIn else { return }
        guard let output = try? await client.getMyEntitlementsApiMeEntitlementsGet() else { return }
        switch output {
        case .ok(let ok):
            if case .json(let entitlements) = ok.body {
                tier = entitlements.tier.rawValue
            }
        case .undocumented(statusCode: 401, _):
            signOut()
        default:
            break
        }
    }
}
