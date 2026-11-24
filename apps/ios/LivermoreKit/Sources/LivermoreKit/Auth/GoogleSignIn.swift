import CryptoKit
import Foundation

public enum GoogleSignInError: Error, Equatable, Sendable {
    /// The user closed the Google sheet. Not a failure to report.
    case cancelled
    /// Google sent the browser back without a usable code, or refused the exchange.
    case rejected
    /// The request to Google never completed.
    case network
}

/// Google's sign-in for an installed app: the authorization-code flow with
/// PKCE, run in the system browser sheet.
///
/// The steps are Google's own (developers.google.com/identity/protocols/oauth2/native-app):
/// open the consent page, receive a one-time code on the app's own URL scheme,
/// and exchange that code for an ID token. The ID token is what the Livermore
/// backend verifies; nothing here decides who the user is.
public struct GoogleSignIn: Sendable {
    /// One attempt. The verifier and state never leave the device until the
    /// exchange, which is what stops a stolen code being used elsewhere.
    public struct Attempt: Sendable {
        public let url: URL
        let verifier: String
        let state: String
    }

    public typealias Loader = @Sendable (URLRequest) async throws -> (Data, URLResponse)

    public let clientID: String
    private let load: Loader

    /// Nil unless `clientID` is a Google OAuth client ID. A build without one
    /// has no Google button rather than one that cannot work.
    public init?(clientID: String?, load: @escaping Loader = { try await URLSession.shared.data(for: $0) }) {
        guard let clientID, clientID.hasSuffix(Self.clientSuffix), clientID.count > Self.clientSuffix.count else {
            return nil
        }
        self.clientID = clientID
        self.load = load
    }

    private static let clientSuffix = ".apps.googleusercontent.com"
    private static let authorizeURL = "https://accounts.google.com/o/oauth2/v2/auth"
    private static let tokenURL = URL(string: "https://oauth2.googleapis.com/token")!

    /// The URL scheme Google returns to: the client ID written backwards.
    /// An iOS client is registered with exactly this scheme.
    public var callbackScheme: String {
        clientID.split(separator: ".").reversed().joined(separator: ".")
    }

    var redirectURI: String { "\(callbackScheme):/oauth2redirect" }

    public func begin() -> Attempt {
        let verifier = Self.randomToken()
        let state = Self.randomToken()
        let challenge = Data(SHA256.hash(data: Data(verifier.utf8))).base64URLEncoded
        var components = URLComponents(string: Self.authorizeURL)!
        components.queryItems = [
            URLQueryItem(name: "client_id", value: clientID),
            URLQueryItem(name: "redirect_uri", value: redirectURI),
            URLQueryItem(name: "response_type", value: "code"),
            URLQueryItem(name: "scope", value: "openid email profile"),
            URLQueryItem(name: "code_challenge", value: challenge),
            URLQueryItem(name: "code_challenge_method", value: "S256"),
            URLQueryItem(name: "state", value: state),
        ]
        return Attempt(url: components.url!, verifier: verifier, state: state)
    }

    /// The one-time code from the URL Google sent the browser back to.
    func code(from callback: URL, for attempt: Attempt) throws(GoogleSignInError) -> String {
        let items = URLComponents(url: callback, resolvingAgainstBaseURL: false)?.queryItems ?? []
        func value(_ name: String) -> String? { items.first { $0.name == name }?.value }
        if value("error") == "access_denied" { throw .cancelled }
        // A callback carrying someone else's state did not come from this attempt.
        guard value("state") == attempt.state, let code = value("code"), !code.isEmpty else { throw .rejected }
        return code
    }

    /// Finishes an attempt: turns the callback URL into a Google ID token.
    public func idToken(from callback: URL, for attempt: Attempt) async throws(GoogleSignInError) -> String {
        let code = try code(from: callback, for: attempt)
        var request = URLRequest(url: Self.tokenURL)
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        var form = URLComponents()
        form.queryItems = [
            URLQueryItem(name: "client_id", value: clientID),
            URLQueryItem(name: "code", value: code),
            URLQueryItem(name: "code_verifier", value: attempt.verifier),
            URLQueryItem(name: "grant_type", value: "authorization_code"),
            URLQueryItem(name: "redirect_uri", value: redirectURI),
        ]
        request.httpBody = Data((form.percentEncodedQuery ?? "").utf8)

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await load(request)
        } catch {
            throw .network
        }
        struct TokenReply: Decodable { let id_token: String }
        guard (response as? HTTPURLResponse)?.statusCode == 200,
              let reply = try? JSONDecoder().decode(TokenReply.self, from: data)
        else { throw .rejected }
        return reply.id_token
    }

    /// The address inside an ID token, for showing who is signed in. Read
    /// without checking the signature: the backend does that, and this value
    /// is only ever displayed.
    public static func email(inIDToken token: String) -> String? {
        let parts = token.split(separator: ".")
        guard parts.count == 3, let payload = Data(base64URLEncoded: String(parts[1])) else { return nil }
        struct Claims: Decodable { let email: String? }
        return (try? JSONDecoder().decode(Claims.self, from: payload))?.email
    }

    private static func randomToken() -> String {
        var generator = SystemRandomNumberGenerator()
        return Data((0..<32).map { _ in UInt8.random(in: .min ... .max, using: &generator) }).base64URLEncoded
    }
}

extension Data {
    var base64URLEncoded: String {
        base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }

    init?(base64URLEncoded text: String) {
        var base64 = text.replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
        base64 += String(repeating: "=", count: (4 - base64.count % 4) % 4)
        self.init(base64Encoded: base64)
    }
}
