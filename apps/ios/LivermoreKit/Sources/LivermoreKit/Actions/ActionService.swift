import Foundation
import LivermoreAPI
import OpenAPIRuntime

public typealias UnresolvedExit = Components.Schemas.UnresolvedExit
public typealias PendingNotice = Components.Schemas.PendingBannerItem

/// What Livermore is waiting on the user for: exits a strategy signalled, and
/// notices not yet read.
///
/// An exit stays in this list until the user says what they did — sold, or
/// chose to hold. It cannot be dismissed away, because dismissing a notice is
/// not a decision about a position.
public struct ActionService: Sendable {
    let client: Client

    public init(client: Client) {
        self.client = client
    }

    public func unresolvedExits() async throws(APIFailure) -> [UnresolvedExit] {
        let output = try await APIFailure.perform {
            try await client.listUnresolvedExitsApiSavedStrategiesUnresolvedExitsGet()
        }
        switch output {
        case .ok(let ok):
            guard case .json(let rows) = ok.body else { throw .server(status: 200) }
            return rows
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    /// Records that the user sold: Livermore reduces the tracked position to
    /// match. `fillPrice` nil means "at the price the tier recorded".
    @discardableResult
    public func confirmExit(
        _ exit: UnresolvedExit, sharesSold: Double, fillPrice: Double?
    ) async throws(APIFailure) -> StrategyPosition {
        let output = try await APIFailure.perform {
            try await client.confirmPositionExitApiSavedStrategiesStrategyIdPositionsPositionIdConfirmExitPost(
                path: .init(strategyId: exit.strategyId, positionId: exit.positionId),
                body: .json(.init(fillPrice: fillPrice, sharesSold: sharesSold, triggerType: exit.triggerType))
            )
        }
        switch output {
        case .ok(let ok):
            guard case .json(let position) = ok.body else { throw .server(status: 200) }
            return position
        case .unprocessableContent:
            throw .rejected("Enter how many shares you sold.")
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    /// Records that the user saw the signal and is keeping the position.
    @discardableResult
    public func hold(_ exit: UnresolvedExit, note: String? = nil) async throws(APIFailure) -> StrategyPosition {
        let output = try await APIFailure.perform {
            try await client.holdPositionThroughExitApiSavedStrategiesStrategyIdPositionsPositionIdHoldPost(
                path: .init(strategyId: exit.strategyId, positionId: exit.positionId),
                body: .json(.init(triggerType: exit.triggerType, userNote: note))
            )
        }
        switch output {
        case .ok(let ok):
            guard case .json(let position) = ok.body else { throw .server(status: 200) }
            return position
        case .unprocessableContent:
            throw .server(status: 422)
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    /// Tells Livermore about a position the user really holds, so it can be
    /// watched against the strategy's stop and targets.
    @discardableResult
    public func declarePosition(
        strategyID: String, symbol: String, shares: Double, entryPrice: Double
    ) async throws(APIFailure) -> StrategyPosition {
        let output = try await APIFailure.perform {
            try await client.declarePositionApiSavedStrategiesStrategyIdPositionsPost(
                path: .init(strategyId: strategyID),
                body: .json(.init(entryPrice: entryPrice, shares: shares, symbol: symbol.uppercased()))
            )
        }
        switch output {
        case .created(let created):
            guard case .json(let position) = created.body else { throw .server(status: 201) }
            return position
        case .unprocessableContent:
            throw .rejected("Enter the ticker, the number of shares and the price you paid.")
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    public func notices() async throws(APIFailure) -> [PendingNotice] {
        let output = try await APIFailure.perform {
            try await client.listPendingBannersApiMeNotificationsPendingGet()
        }
        switch output {
        case .ok(let ok):
            guard case .json(let rows) = ok.body else { throw .server(status: 200) }
            return rows
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    public func acknowledge(_ notice: PendingNotice) async throws(APIFailure) {
        let output = try await APIFailure.perform {
            try await client.acknowledgeBannerApiMeNotificationsEntryIdAckPost(path: .init(entryId: notice.id))
        }
        switch output {
        case .noContent:
            return
        case .unprocessableContent:
            throw .server(status: 422)
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }
}

// MARK: - What an exit asks for

extension Components.Schemas.UnresolvedExit {
    public var id: String { "\(positionId):\(triggerType)" }

    public var isDaily: Bool { (barResolution ?? "daily") == "daily" }

    /// How many shares the rule says to sell — the web's `quantityFor`.
    public enum Quantity: Equatable, Sendable {
        /// One number, safe to put on an order ticket.
        case exact(Double)
        /// An earlier tier fired and the user never said whether they sold,
        /// so the right number depends on what they still hold. Stating one
        /// would be a guess presented as an instruction.
        case ambiguous(ifEarlierTierSold: Double, ifNot: Double)
    }

    public var quantity: Quantity {
        if action == "sell_all" { return .exact(Self.rounded(sharesRemaining, like: sharesInitial)) }
        let suggested = Self.rounded(shares ?? 0, like: sharesInitial)
        if sharesRemaining == sharesInitial { return .exact(suggested) }
        return .ambiguous(ifEarlierTierSold: suggested, ifNot: Self.rounded(sharesRemaining, like: sharesInitial))
    }

    /// Whole shares for a position declared in whole shares; four places
    /// otherwise. Always rounded down — never more than is held.
    static func rounded(_ raw: Double, like declared: Double) -> Double {
        declared == declared.rounded() ? raw.rounded(.down) : (raw * 10_000).rounded(.down) / 10_000
    }

    /// The headline: "Stop tier reached at −8.2%".
    public var headline: String {
        let tier = tierLabel.map { "\($0) tier" } ?? "Exit tier"
        guard let change = pctChange else { return "\(tier) reached" }
        return "\(tier) reached at \(String(format: "%+.1f%%", change * 100))"
    }

    /// What the price on the ticket is and is not. A daily exit was measured
    /// on a completed session; an intraday one on a delayed feed. Neither is
    /// a price the user can still get.
    public var priceCaveat: String {
        if isDaily {
            let day = barDate ?? signaledAt.map { String($0.prefix(10)) } ?? "the last session"
            return "Measured on the close of \(day). That is the price that met the rule, not one you can still get — you would act at the next open."
        }
        return "The rule is checked on a feed delayed by up to about 20 minutes. That price is the bar that met the rule, not a quote you can still get."
    }
}
