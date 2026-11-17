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
    /// 409 on sign-up — the address already has an account.
    case emailTaken
    /// Sign-up only: checked on the device before anything is sent.
    case weakPassword
    /// Any other HTTP status.
    case server(status: Int)
    /// The request never completed.
    case network

    public var message: String {
        switch self {
        case .invalidCredentials: "That email and password don't match an account."
        case .invalidInput: "Enter a valid email address and password."
        case .emailTaken: "That email already has an account. Sign in instead."
        case .weakPassword: "Choose a password of at least \(AppSession.minimumPasswordLength) characters."
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

    /// The symbols the user follows, kept on this device.
    public let watchlist = Watchlist()

    /// Daily price histories for the charts, kept while the app runs.
    public let priceHistory: PriceHistory

    /// Exits waiting on a decision and unread notices.
    public let inbox: ActionInbox

    /// The linked brokerage, as last read.
    public let brokerageLink: BrokerageLink

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
        self.priceHistory = PriceHistory { symbol in
            try await ResearchService(client: client).dailyCloses(symbol)
        }
        self.inbox = ActionInbox(service: ActionService(client: client))
        self.brokerageLink = BrokerageLink(service: BrokerageService(client: client))
        if let saved = store.load() {
            tokens.set(saved.token)
            state = .signedIn(saved)
        } else {
            state = .signedOut
        }
        // A token the backend no longer accepts ends the session wherever it
        // is discovered, rather than leaving every screen to fail on its own.
        inbox.onSessionExpired = { [weak self] in self?.signOut() }
        brokerageLink.onSessionExpired = { [weak self] in self?.signOut() }
    }

    /// Company research calls, sharing this session's client and token.
    public var research: ResearchService { ResearchService(client: client) }

    /// The user's strategies and tracked positions. Needs a signed-in session.
    public var strategies: StrategyService { StrategyService(client: client) }

    /// Backtests and saving. Runs work signed out, within the anonymous limit.
    public var backtests: BacktestService { BacktestService(client: client) }

    /// Exits waiting on a decision, and notices. Needs a signed-in session.
    public var actions: ActionService { ActionService(client: client) }

    /// The user's linked brokerage: accounts, holdings, order tickets.
    public var brokerage: BrokerageService { BrokerageService(client: client) }

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
            adopt(token, email: email)
        case .unprocessableContent:
            throw .invalidInput
        case .undocumented(let status, _):
            throw status == 401 ? .invalidCredentials : .server(status: status)
        }
    }

    public nonisolated static let minimumPasswordLength = 8

    /// Creates an account and signs in to it. The backend folds this
    /// device's anonymous session into the new account, so a backtest run
    /// before signing up is not lost.
    public func signUp(email: String, password: String, displayName: String?) async throws(SignInError) {
        let email = email.trimmingCharacters(in: .whitespacesAndNewlines)
        guard password.count >= Self.minimumPasswordLength else { throw .weakPassword }
        let name = displayName?.trimmingCharacters(in: .whitespacesAndNewlines)
        let output: Operations.PasswordSignupApiAuthPasswordSignupPost.Output
        do {
            output = try await client.passwordSignupApiAuthPasswordSignupPost(
                body: .json(.init(displayName: name?.isEmpty == false ? name : nil, email: email, password: password))
            )
        } catch {
            throw .network
        }

        switch output {
        case .created(let created):
            guard case .json(let token) = created.body else { throw .server(status: 201) }
            adopt(token, email: email)
        case .unprocessableContent:
            throw .invalidInput
        case .undocumented(let status, _):
            throw status == 409 ? .emailTaken : .server(status: status)
        }
    }

    private func adopt(_ token: Components.Schemas.TokenResponse, email: String) {
        let session = StoredSession(
            token: token.sessionToken,
            userID: token.user.id,
            email: email,
            displayName: token.user.displayName
        )
        // A Keychain failure must not strand the user on the sign-in screen
        // with correct credentials: they are signed in for this launch and
        // asked again on the next.
        try? store.save(session)
        tokens.set(session.token)
        state = .signedIn(session)
    }

    public func signOut() {
        store.clear()
        tokens.set(nil)
        tier = nil
        inbox.reset()
        brokerageLink.reset()
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
