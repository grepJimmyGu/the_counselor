import Foundation
import LivermoreAPI
import OpenAPIRuntime

public typealias SavedStrategy = Components.Schemas.AppApiRoutesSavedStrategiesSavedStrategyResponse
public typealias TrackedPosition = Components.Schemas.TrackedPosition
public typealias SignalState = Components.Schemas.SignalStateResponse
public typealias SignalEvent = Components.Schemas.SignalEventResponse
public typealias StrategyPositions = Components.Schemas.PositionsResponse
public typealias StrategyPosition = Components.Schemas.PositionView
public typealias TierMarker = Components.Schemas.TierMarker

/// The signed-in user's saved strategies and the positions Livermore is
/// tracking against them. Every call here needs a session; without one the
/// backend answers 401, surfaced as `APIFailure.notSignedIn`.
public struct StrategyService: Sendable {
    let client: Client

    public init(client: Client) {
        self.client = client
    }

    public func strategies() async throws(APIFailure) -> [SavedStrategy] {
        let output = try await APIFailure.perform { try await client.listSavedStrategiesApiSavedStrategiesGet() }
        switch output {
        case .ok(let ok):
            guard case .json(let rows) = ok.body else { throw .server(status: 200) }
            return rows
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    /// Open positions across every strategy, each with its live stop and next
    /// target.
    public func openPositions() async throws(APIFailure) -> [TrackedPosition] {
        let output = try await APIFailure.perform {
            try await client.listOpenPositionsApiSavedStrategiesOpenPositionsGet()
        }
        switch output {
        case .ok(let ok):
            guard case .json(let rows) = ok.body else { throw .server(status: 200) }
            return rows
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    public func signal(strategyID: String) async throws(APIFailure) -> SignalState {
        let output = try await APIFailure.perform {
            try await client.getSignalApiSavedStrategiesStrategyIdSignalGet(path: .init(strategyId: strategyID))
        }
        switch output {
        case .ok(let ok):
            guard case .json(let state) = ok.body else { throw .server(status: 200) }
            return state
        case .unprocessableContent:
            throw .server(status: 422)
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    public func positions(strategyID: String) async throws(APIFailure) -> StrategyPositions {
        let output = try await APIFailure.perform {
            try await client.getStrategyPositionsApiSavedStrategiesStrategyIdPositionsGet(
                path: .init(strategyId: strategyID)
            )
        }
        switch output {
        case .ok(let ok):
            guard case .json(let positions) = ok.body else { throw .server(status: 200) }
            return positions
        case .unprocessableContent:
            throw .server(status: 422)
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }
}

extension Components.Schemas.AppApiRoutesSavedStrategiesSavedStrategyResponse {
    /// True when the strategy has exit rules — a stop or targets — which is
    /// what Livermore monitors a position against. Without them there is
    /// nothing to track, and the strategy page says so.
    ///
    /// This is the rule the web's strategy *page* uses
    /// (`risk_management.exit_ladder` is non-empty). The web's strategy *list*
    /// badges "Live" on a different test (an intraday bar resolution); the
    /// page's rule is the one that decides whether tracking works.
    public var tracksExits: Bool {
        guard let risk = strategyJson.additionalProperties.value["risk_management"] as? [String: (any Sendable)?],
              let ladder = risk["exit_ladder"] as? [(any Sendable)?]
        else { return false }
        return !ladder.isEmpty
    }

    /// The strategy in the shape the backtester takes, or nil when it uses
    /// something this version of the app has no type for. The saved copy is
    /// free-form JSON; a strategy built with the website's signal composer
    /// can carry fields added since this app was built.
    public var typedStrategy: StrategyJSON? {
        guard let data = try? JSONEncoder().encode(strategyJson) else { return nil }
        return try? JSONDecoder().decode(StrategyJSON.self, from: data)
    }

    /// The tickers the strategy trades.
    public var universe: [String] {
        let raw = strategyJson.additionalProperties.value["universe"] as? [(any Sendable)?] ?? []
        return raw.compactMap { $0 as? String }
    }

    /// "daily" unless the strategy says otherwise.
    public var barResolution: String {
        (strategyJson.additionalProperties.value["bar_resolution"] as? String) ?? "daily"
    }
}

extension Components.Schemas.TrackedPosition {
    /// How the price shown was obtained. A daily strategy is evaluated on the
    /// close, so an intraday quote is fresher than the thing its ladder is
    /// measured against; saying which avoids implying tick-by-tick monitoring.
    /// Mirrors `priceNote` in the web's positions page.
    public var priceNote: String {
        if priceSource == "none" { return "no recent price" }
        if priceSource == "daily_close" { return "last close" }
        return barResolution == "daily" ? "latest quote · checked at the close" : "latest quote"
    }
}
