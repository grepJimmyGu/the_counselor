import Foundation
import HTTPTypes
import LivermoreAPI
import OpenAPIRuntime
import OpenAPIURLSession
import os

public enum APIEnvironment {
    /// The FastAPI backend. The app talks to it directly — the website on
    /// Vercel is not in the path.
    public static let production = URL(string: "https://thecounselor-production.up.railway.app")!
}

/// Holds the bearer token the middleware attaches. A lock rather than an actor
/// because the middleware reads it synchronously on every request.
final class TokenBox: Sendable {
    private let token = OSAllocatedUnfairLock<String?>(initialState: nil)
    func set(_ value: String?) { token.withLock { $0 = value } }
    func get() -> String? { token.withLock { $0 } }
}

/// Adds `Authorization: Bearer <token>` when a user is signed in.
///
/// Requests go out without the header when signed out; the backend's
/// `allow_anonymous` routes then serve the anonymous tier, exactly as they do
/// for a signed-out browser.
struct BearerTokenMiddleware: ClientMiddleware {
    let tokens: TokenBox

    func intercept(
        _ request: HTTPRequest,
        body: HTTPBody?,
        baseURL: URL,
        operationID: String,
        next: @Sendable (HTTPRequest, HTTPBody?, URL) async throws -> (HTTPResponse, HTTPBody?)
    ) async throws -> (HTTPResponse, HTTPBody?) {
        var request = request
        if let token = tokens.get() {
            request.headerFields[.authorization] = "Bearer \(token)"
        }
        return try await next(request, body, baseURL)
    }
}

extension Client {
    static func livermore(
        serverURL: URL,
        transport: any ClientTransport,
        tokens: TokenBox
    ) -> Client {
        Client(
            serverURL: serverURL,
            transport: transport,
            middlewares: [BearerTokenMiddleware(tokens: tokens)]
        )
    }
}
