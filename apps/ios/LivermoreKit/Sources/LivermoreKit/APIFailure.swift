import Foundation
import OpenAPIRuntime

/// Why a call to the backend did not produce data. Shared by every service so
/// each failure is told apart the same way everywhere.
public enum APIFailure: Error, Equatable, Sendable {
    /// 402 — outside what this plan covers. Carries the backend's explanation.
    case upgradeRequired(String)
    /// 404 — the backend could not build the response. Carries its reason,
    /// which is for diagnosis only: the overview route puts raw exception text
    /// there, so it is never shown.
    case unavailable(String)
    /// 401 — no token, or one the backend no longer accepts. Tokens last 30
    /// days and a device cannot refresh one, so this means "sign in again".
    case notSignedIn
    case server(status: Int)
    /// The response arrived but could not be decoded — the app and the backend
    /// disagree about its shape. Kept apart from `network` so a schema
    /// mismatch is never reported to the user as a connection problem.
    case unreadable
    case network

    public var message: String {
        switch self {
        case .upgradeRequired(let detail): detail
        case .unavailable: "Livermore couldn't load this right now."
        case .notSignedIn: "Your session has ended. Sign in again."
        case .server(let status): "Livermore returned an error (\(status)). Try again in a moment."
        case .unreadable: "Livermore sent data this version of the app can't read. Updating the app may fix it."
        case .network: "Couldn't reach Livermore. Check your connection and try again."
        }
    }

    /// Runs a generated client call, sorting thrown errors into `unreadable`
    /// (decoding) and `network` (everything else).
    static func perform<T: Sendable>(_ call: () async throws -> T) async throws(APIFailure) -> T {
        do {
            return try await call()
        } catch let error as ClientError where error.underlyingError is DecodingError {
            throw .unreadable
        } catch {
            throw .network
        }
    }

    /// Maps a status the schema does not document, pulling the backend's
    /// `detail` out of the body. FastAPI sends either `{"detail": "text"}` or,
    /// for a plan gate, `{"detail": {"entitlement": {"detail": "text"}}}`.
    static func from(status: Int, payload: UndocumentedPayload) async -> APIFailure {
        var detail: String?
        if let body = payload.body, let data = try? await Data(collecting: body, upTo: 1 << 20) {
            detail = Self.detail(in: data)
        }
        switch status {
        case 401: return .notSignedIn
        case 402: return .upgradeRequired(detail ?? "This isn't included in your plan.")
        case 404: return .unavailable(detail ?? "")
        default: return .server(status: status)
        }
    }

    static func detail(in data: Data) -> String? {
        guard let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        if let text = root["detail"] as? String { return text }
        if let nested = root["detail"] as? [String: Any] {
            if let entitlement = nested["entitlement"] as? [String: Any], let text = entitlement["detail"] as? String {
                return text
            }
            return nested["detail"] as? String
        }
        return nil
    }
}
