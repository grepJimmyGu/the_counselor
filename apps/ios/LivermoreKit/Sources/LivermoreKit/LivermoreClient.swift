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

    /// The iOS OAuth client ID from Google Cloud ("....apps.googleusercontent.com").
    /// Not a secret: every copy of the app carries it. While it is nil the
    /// sign-in screen has no Google button. The backend must be given the same
    /// value as GOOGLE_IOS_CLIENT_ID or it will refuse the app's tokens.
    public static let googleClientID: String? = nil
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

/// Reads the timestamp formats the backend actually sends.
///
/// The generator's default accepts only whole-second ISO 8601. The backend
/// serialises Python datetimes with microseconds ("…T04:14:09.273587Z"), and
/// naive ones with no zone at all, so the default fails the whole response —
/// the sentiment summary could not be decoded with it.
struct LenientDateTranscoder: DateTranscoder {
    func encode(_ date: Date) throws -> String {
        ISO8601DateFormatter().string(from: date)
    }

    func decode(_ string: String) throws -> Date {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = fractional.date(from: string) { return date }
        if let date = ISO8601DateFormatter().date(from: string) { return date }
        // No zone: the backend's naive datetimes are UTC.
        let hasZone = string.hasSuffix("Z") || string.dropFirst(19).contains(where: { $0 == "+" || $0 == "-" })
        if !hasZone {
            if let date = fractional.date(from: string + "Z") { return date }
            if let date = ISO8601DateFormatter().date(from: string + "Z") { return date }
        }
        throw DecodingError.dataCorrupted(
            .init(codingPath: [], debugDescription: "Unrecognised timestamp: \(string)")
        )
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
            configuration: Configuration(dateTranscoder: LenientDateTranscoder()),
            transport: transport,
            middlewares: [BearerTokenMiddleware(tokens: tokens)]
        )
    }
}
