import Foundation
import LivermoreAPI
import OpenAPIRuntime

public typealias AgentProfile = Components.Schemas.AgentProfileView
public typealias AgentInsight = Components.Schemas.AgentInsightView
public typealias AgentScan = Components.Schemas.AgentScanView

/// An order the agent has drafted for the user to look at. A draft is all it
/// ever is: the agent cannot send it, and opening it only fills in the
/// ticket the user already knows, where the broker's price and an explicit
/// confirmation still come first.
public struct OrderSuggestion: Equatable, Sendable {
    public enum Side: String, Sendable { case buy, sell }

    public var symbol: String
    public var side: Side
    public var units: Double?
    public var amountUSD: Double?
    public var reason: String?

    public init(symbol: String, side: Side, units: Double? = nil, amountUSD: Double? = nil, reason: String? = nil) {
        self.symbol = symbol
        self.side = side
        self.units = units
        self.amountUSD = amountUSD
        self.reason = reason
    }
}

/// What the app can open when the user wants to act on something the agent said.
public enum AgentAction: Equatable, Sendable {
    case openCompany(symbol: String)
    case reviewOrder(OrderSuggestion)
    case openActions

    /// Reads the backend's `{"type": ...}` object. Nil for a type this build
    /// does not know, so a newer backend cannot make an older app open the
    /// wrong thing.
    public init?(json: [String: Any]) {
        func number(_ key: String) -> Double? {
            if let value = json[key] as? Double { return value }
            if let value = json[key] as? Int { return Double(value) }
            return nil
        }
        switch json["type"] as? String {
        case "open_company":
            guard let symbol = json["symbol"] as? String, !symbol.isEmpty else { return nil }
            self = .openCompany(symbol: symbol)
        case "open_actions":
            self = .openActions
        case "review_order":
            guard let symbol = json["symbol"] as? String, !symbol.isEmpty,
                  let side = (json["side"] as? String).flatMap(OrderSuggestion.Side.init(rawValue:))
            else { return nil }
            let units = number("units"), amount = number("amount_usd")
            guard (units ?? 0) > 0 || (amount ?? 0) > 0 else { return nil }
            self = .reviewOrder(OrderSuggestion(
                symbol: symbol, side: side, units: units, amountUSD: amount,
                reason: (json["reason"] as? String).flatMap { $0.isEmpty ? nil : $0 }
            ))
        default:
            return nil
        }
    }
}

extension AgentInsight {
    /// What this insight offers to open, if anything this build understands.
    public var suggestedAction: AgentAction? {
        guard let action else { return nil }
        return AgentAction(json: action.additionalProperties.value.compactMapValues { $0 })
    }
}

/// The portfolio agent's settings and what it has found.
public struct AgentService: Sendable {
    let client: Client

    public init(client: Client) {
        self.client = client
    }

    public func profile() async throws(APIFailure) -> AgentProfile {
        let output = try await APIFailure.perform { try await client.getProfileApiAgentProfileGet() }
        switch output {
        case .ok(let ok):
            guard case .json(let profile) = ok.body else { throw .server(status: 200) }
            return profile
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    /// Changes the settings that are given and leaves the rest alone.
    public func update(
        enabled: Bool? = nil,
        emailAlerts: Bool? = nil,
        watchlist: [String]? = nil,
        moveAlertPct: Double? = nil,
        maxPositionPct: Double? = nil,
        notes: String? = nil
    ) async throws(APIFailure) -> AgentProfile {
        let output = try await APIFailure.perform {
            try await client.updateProfileApiAgentProfilePut(body: .json(.init(
                enabled: enabled, emailAlerts: emailAlerts, watchlist: watchlist, moveAlertPct: moveAlertPct,
                maxPositionPct: maxPositionPct, notes: notes
            )))
        }
        switch output {
        case .ok(let ok):
            guard case .json(let profile) = ok.body else { throw .server(status: 200) }
            return profile
        case .unprocessableContent:
            throw .rejected("One of those settings is outside what the agent accepts.")
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    public func insights() async throws(APIFailure) -> [AgentInsight] {
        let output = try await APIFailure.perform { try await client.listInsightsApiAgentInsightsGet() }
        switch output {
        case .ok(let ok):
            guard case .json(let rows) = ok.body else { throw .server(status: 200) }
            return rows
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    public func dismiss(_ insight: AgentInsight) async throws(APIFailure) {
        let output = try await APIFailure.perform {
            try await client.dismissInsightApiAgentInsightsInsightIdDismissPost(path: .init(insightId: insight.id))
        }
        switch output {
        case .ok: return
        case .unprocessableContent: throw .server(status: 422)
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    /// Has the agent look now, and returns everything it holds afterwards.
    public func scan() async throws(APIFailure) -> AgentScan {
        let output = try await APIFailure.perform { try await client.scanNowApiAgentScanPost() }
        switch output {
        case .ok(let ok):
            guard case .json(let scan) = ok.body else { throw .server(status: 200) }
            return scan
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }
}
