import Foundation
import HTTPTypes
import OpenAPIRuntime

/// A network stub: answers by operation id and records what was sent.
final class MockTransport: ClientTransport, @unchecked Sendable {
    struct Recorded: Sendable {
        let operationID: String
        let authorization: String?
        let body: String
        /// The path and query as sent, e.g. "/api/data/daily/NVDA?start=2020-11-20".
        var path: String = ""
    }

    enum Reply: Sendable {
        case json(status: Int, String)
        case failure
    }

    private let lock = NSLock()
    private var recorded: [Recorded] = []
    private var replies: [String: Reply] = [:]

    func stub(_ operationID: String, _ reply: Reply) {
        lock.withLock { replies[operationID] = reply }
    }

    var requests: [Recorded] { lock.withLock { recorded } }

    func send(
        _ request: HTTPRequest,
        body: HTTPBody?,
        baseURL: URL,
        operationID: String
    ) async throws -> (HTTPResponse, HTTPBody?) {
        let sent: String
        if let body {
            sent = String(decoding: try await Data(collecting: body, upTo: 1 << 20), as: UTF8.self)
        } else {
            sent = ""
        }
        let reply: Reply? = lock.withLock {
            recorded.append(.init(
                operationID: operationID,
                authorization: request.headerFields[.authorization],
                body: sent,
                path: request.path ?? ""
            ))
            return replies[operationID]
        }
        switch reply {
        case .json(let status, let payload):
            return (
                HTTPResponse(status: .init(code: status), headerFields: [.contentType: "application/json"]),
                HTTPBody(payload)
            )
        case .failure, nil:
            throw URLError(.notConnectedToInternet)
        }
    }
}

enum Fixture {
    static let login = "password_login_api_auth_password_login_post"
    static let entitlements = "get_my_entitlements_api_me_entitlements_get"

    static let tokenResponse = """
    {"user":{"id":"u-1","handle":null,"display_name":"Jimmy","avatar_url":null,"locale":"en"},"session_token":"tok-123"}
    """
    /// Built from the schema's required fields; `tier` is the value under test.
    static let strategistEntitlements = """
    {"tier":"strategist","status":"active","week_start":"x","template_runs_unlimited":false,"universe_size_max_custom":1,"history_window_years_custom":1,"asset_classes":[],"robustness_tests":[],"market_pulse_ticker_scope":"top_250","business_model_section":"full","commodity_framework":false,"saved_strategies_max":1,"saved_strategies_always_public":false}
    """
    static let saved = StoredSessionFixture.make()
}

import LivermoreKit

enum StoredSessionFixture {
    static func make() -> StoredSession {
        StoredSession(token: "saved-tok", userID: "u-9", email: "saved@example.com", displayName: nil)
    }
}
