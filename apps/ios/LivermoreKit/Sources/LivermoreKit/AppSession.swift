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
    /// Sign-up only: the backend refused the password, in its own words. This
    /// is how a password found in breach data is reported, which only the
    /// backend can know.
    case passwordRejected(String)
    /// Google sign-in: the address belongs to an account that signs in with a
    /// password and has never used Google.
    case emailHasPassword
    /// Google did not complete the sign-in, or the backend did not accept it.
    case googleFailed
    /// Face ID sign-in: the saved password is no longer the account's password.
    case savedPasswordRejected
    /// Password reset: the emailed code was wrong, used or out of date. The
    /// backend gives one answer for all three, in its own words.
    case resetCodeRejected(String)
    /// The user backed out. Nothing to report.
    case cancelled
    /// Any other HTTP status.
    case server(status: Int)
    /// The request never completed.
    case network

    public var message: String {
        switch self {
        case .invalidCredentials: "That email and password don't match an account."
        case .invalidInput: "Enter a valid email address and password."
        case .emailTaken: "That email already has an account. Sign in instead."
        case .weakPassword: "That password doesn't meet the rules below."
        case .passwordRejected(let reason): reason
        case .emailHasPassword: "That email already has a Livermore account with a password. Sign in with the password instead."
        case .googleFailed: "Google sign-in didn't complete. Try again."
        case .savedPasswordRejected: "The saved password no longer works. Sign in with your current password."
        case .resetCodeRejected(let reason): reason
        case .cancelled: ""
        case .server(let status): "Livermore couldn't sign you in (error \(status)). Try again in a moment."
        case .network: "Couldn't reach Livermore. Check your connection and try again."
        }
    }
}

extension SignInError {
    /// The message on a screen that is doing something other than signing in,
    /// named by `task` ("send the code", "change your password").
    ///
    /// A 404 there means the backend the app is talking to is older than the
    /// app and has no such endpoint. "Try again in a moment" would be wrong:
    /// trying again cannot help until the server is updated.
    public func message(whileTryingTo task: String) -> String {
        switch self {
        case .server(status: 404):
            "Livermore's server doesn't support this yet, so the app can't \(task). It needs a server update, not another try."
        case .server(let status):
            "Livermore couldn't \(task) (error \(status)). Try again in a moment."
        default:
            message
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

    /// Google sign-in, or nil in a build with no Google client ID.
    public let google: GoogleSignIn?

    /// The biometric check this device offers, if any.
    public var biometry: Biometry? { biometrics.biometry }

    /// The address whose password is saved for Face ID sign-in, if one is.
    public private(set) var biometricEmail: String?

    /// Set after a typed sign-in on a device with Face ID: the credential the
    /// user can choose to keep. Cleared by accepting or declining.
    public private(set) var biometricOffer: SavedCredential?

    private let store: any SessionStore
    private let biometrics: any BiometricCredentialStore
    private let tokens = TokenBox()

    public init(
        serverURL: URL = APIEnvironment.production,
        store: any SessionStore = KeychainSessionStore(),
        biometrics: any BiometricCredentialStore = KeychainBiometricStore(),
        googleClientID: String? = APIEnvironment.googleClientID,
        transport: any ClientTransport = URLSessionTransport()
    ) {
        self.store = store
        self.biometrics = biometrics
        self.biometricEmail = biometrics.savedEmail
        self.google = GoogleSignIn(clientID: googleClientID)
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
            adopt(token: token.sessionToken, user: token.user, email: email)
            offerBiometrics(SavedCredential(email: email, password: password))
        case .unprocessableContent:
            throw .invalidInput
        case .undocumented(let status, _):
            throw status == 401 ? .invalidCredentials : .server(status: status)
        }
    }

    /// Signs in with the ID token Google issued. The backend checks the token
    /// and finds or creates the account; a first sign-in creates one.
    public func signInWithGoogle(idToken: String) async throws(SignInError) {
        let output: Operations.GoogleOauthCallbackApiAuthOauthGoogleCallbackPost.Output
        do {
            output = try await client.googleOauthCallbackApiAuthOauthGoogleCallbackPost(
                body: .json(.init(idToken: idToken))
            )
        } catch {
            throw .network
        }

        switch output {
        case .ok(let ok):
            guard case .json(let token) = ok.body else { throw .server(status: 200) }
            let email = GoogleSignIn.email(inIDToken: idToken) ?? ""
            adopt(token: token.sessionToken, user: token.user, email: email)
        case .unprocessableContent:
            throw .googleFailed
        case .undocumented(let status, _):
            switch status {
            case 409: throw .emailHasPassword
            case 400: throw .googleFailed
            default: throw .server(status: status)
            }
        }
    }

    // MARK: Forgotten password

    /// Asks for a reset code to be emailed. Succeeds whether or not the
    /// address has an account: the backend deliberately does not say.
    public func requestPasswordReset(email: String) async throws(SignInError) {
        let email = email.trimmingCharacters(in: .whitespacesAndNewlines)
        let output: Operations.RequestPasswordResetApiAuthPasswordResetRequestPost.Output
        do {
            output = try await client.requestPasswordResetApiAuthPasswordResetRequestPost(
                body: .json(.init(email: email))
            )
        } catch {
            throw .network
        }
        switch output {
        case .accepted: return
        case .unprocessableContent: throw .invalidInput
        case .undocumented(let status, _): throw .server(status: status)
        }
    }

    /// Sets a new password with the emailed code, and signs in with it.
    public func resetPassword(email: String, code: String, newPassword: String) async throws(SignInError) {
        let email = email.trimmingCharacters(in: .whitespacesAndNewlines)
        guard PasswordPolicy.violations(newPassword, email: email).isEmpty else { throw .weakPassword }
        let output: Operations.ConfirmPasswordResetApiAuthPasswordResetConfirmPost.Output
        do {
            output = try await client.confirmPasswordResetApiAuthPasswordResetConfirmPost(
                body: .json(.init(email: email, code: code, newPassword: newPassword))
            )
        } catch {
            throw .network
        }
        switch output {
        case .ok(let ok):
            guard case .json(let token) = ok.body else { throw .server(status: 200) }
            adopt(token: token.sessionToken, user: token.user, email: email)
            // A password already kept for Face ID is the old one; this replaces it.
            offerBiometrics(SavedCredential(email: email, password: newPassword))
        case .badRequest(let refused):
            guard case .json(let reason) = refused.body else { throw .server(status: 400) }
            throw reason.code == .invalidCode ? .resetCodeRejected(reason.detail) : .passwordRejected(reason.detail)
        case .unprocessableContent:
            throw .invalidInput
        case .undocumented(let status, _):
            throw .server(status: status)
        }
    }

    // MARK: Changing the password

    /// Replaces the signed-in user's password. The backend asks for the
    /// current one again, signs out every other device, and replies with a
    /// new session for this one.
    public func changePassword(current: String, new: String) async throws(SignInError) {
        guard case .signedIn(let stored) = state else { throw .cancelled }
        let email = stored.email.isEmpty ? nil : stored.email
        guard PasswordPolicy.violations(new, email: email, displayName: stored.displayName).isEmpty else {
            throw .weakPassword
        }
        let output: Operations.ChangePasswordApiAuthPasswordChangePost.Output
        do {
            output = try await client.changePasswordApiAuthPasswordChangePost(
                body: .json(.init(currentPassword: current, newPassword: new))
            )
        } catch {
            throw .network
        }
        switch output {
        case .ok(let ok):
            guard case .json(let token) = ok.body else { throw .server(status: 200) }
            adopt(token: token.sessionToken, user: token.user, email: stored.email)
            // A password kept for Face ID is now the old one. Replace it; a
            // device that keeps none is not asked to start here.
            if biometricEmail == stored.email {
                let saved = SavedCredential(email: stored.email, password: new)
                if (try? biometrics.save(saved)) == nil { biometricEmail = nil }
            }
        case .badRequest(let refused):
            guard case .json(let reason) = refused.body else { throw .server(status: 400) }
            throw .passwordRejected(reason.detail)
        case .unprocessableContent:
            throw .invalidInput
        case .undocumented(statusCode: 401, _):
            // The session ended while the screen was open; there is nothing
            // to change a password on. The app returns to sign-in.
            signOut()
            throw .cancelled
        case .undocumented(let status, _):
            throw .server(status: status)
        }
    }

    // MARK: Face ID sign-in

    /// Signs in with the saved password, after the device's biometric check.
    public func signInWithBiometrics() async throws(SignInError) {
        let credential: SavedCredential
        do {
            credential = try await biometrics.load(reason: "Sign in to Livermore")
        } catch {
            if error == .unavailable { biometricEmail = nil }
            throw error == .unavailable ? .savedPasswordRejected : .cancelled
        }
        do {
            try await signIn(email: credential.email, password: credential.password)
        } catch {
            // The password was changed elsewhere; keeping it would fail every time.
            if error == .invalidCredentials {
                turnOffBiometricSignIn()
                throw .savedPasswordRejected
            }
            throw error
        }
    }

    /// Keeps the password just typed, so the next sign-in needs only a face.
    public func acceptBiometricOffer(_ offer: SavedCredential) {
        biometricOffer = nil
        if (try? biometrics.save(offer)) != nil { biometricEmail = offer.email }
    }

    public func declineBiometricOffer() {
        biometricOffer = nil
    }

    public func turnOffBiometricSignIn() {
        biometrics.clear()
        biometricEmail = nil
    }

    private func offerBiometrics(_ credential: SavedCredential) {
        guard biometrics.biometry != nil else { return }
        if biometricEmail == credential.email {
            // Already chosen for this account: keep what is saved current.
            if (try? biometrics.save(credential)) == nil { biometricEmail = nil }
        } else {
            biometricOffer = credential
        }
    }

    /// Creates an account and signs in to it. The backend folds this
    /// device's anonymous session into the new account, so a backtest run
    /// before signing up is not lost.
    public func signUp(email: String, password: String, displayName: String?) async throws(SignInError) {
        let email = email.trimmingCharacters(in: .whitespacesAndNewlines)
        let name = displayName?.trimmingCharacters(in: .whitespacesAndNewlines)
        guard PasswordPolicy.violations(password, email: email, displayName: name).isEmpty else {
            throw .weakPassword
        }
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
            adopt(token: token.sessionToken, user: token.user, email: email)
            offerBiometrics(SavedCredential(email: email, password: password))
        case .badRequest(let refused):
            guard case .json(let reason) = refused.body else { throw .server(status: 400) }
            throw .passwordRejected(reason.detail)
        case .unprocessableContent:
            throw .invalidInput
        case .undocumented(let status, _):
            throw status == 409 ? .emailTaken : .server(status: status)
        }
    }

    private func adopt(token: String, user: Components.Schemas.UserPublic, email: String) {
        let session = StoredSession(token: token, userID: user.id, email: email, displayName: user.displayName)
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
        biometricOffer = nil
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
