import Foundation
import LivermoreAPI
import OpenAPIRuntime

public typealias BrokerageStatus = Components.Schemas.SnapTradeStatus
public typealias BrokerAccount = Components.Schemas.BrokerAccountView
public typealias BrokerHolding = Components.Schemas.BrokerPositionView
public typealias OrderPreview = Components.Schemas.PreviewOrderResponse
public typealias OrderReceipt = Components.Schemas.PlaceOrderResponse

/// An order as the user has filled it in, before the broker has priced it.
///
/// A sell is sized in shares — you sell what you hold. A buy is sized in
/// dollars, which is the question a person actually answers, and what the
/// backend's ticket takes. The two cases make it impossible to send both.
public struct OrderDraft: Equatable, Sendable {
    public enum Size: Equatable, Sendable {
        case sell(shares: Double)
        case buy(dollars: Double)
    }

    public var accountID: String
    public var symbol: String
    public var size: Size

    public init(accountID: String, symbol: String, size: Size) {
        self.accountID = accountID
        self.symbol = symbol.uppercased()
        self.size = size
    }

    public var action: String {
        switch size {
        case .sell: "SELL"
        case .buy: "BUY"
        }
    }

    /// Why this can't be priced, or nil when it can.
    public var problem: String? {
        if accountID.isEmpty { return "Choose a brokerage account." }
        if symbol.isEmpty { return "Enter a ticker." }
        switch size {
        case .sell(let shares): return shares > 0 ? nil : "Enter how many shares to sell."
        case .buy(let dollars): return dollars > 0 ? nil : "Enter how much to invest."
        }
    }
}

/// The user's own brokerage, reached through SnapTrade.
///
/// Livermore never holds brokerage credentials and never trades on its own:
/// the link is authorised on the broker's own login, and an order goes out
/// only after the user has seen the broker's price for it and sent it.
public struct BrokerageService: Sendable {
    let client: Client

    public init(client: Client) {
        self.client = client
    }

    /// Whether brokerage links are available at all, whether this user has
    /// one, and whether orders can be placed. Safe to call in any state.
    public func status() async throws(APIFailure) -> BrokerageStatus {
        let output = try await APIFailure.perform { try await client.snaptradeStatusApiSnaptradeStatusGet() }
        switch output {
        case .ok(let ok):
            guard case .json(let status) = ok.body else { throw .server(status: 200) }
            return status
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    /// A one-time address where the user signs in to their own broker.
    public func connectionURL() async throws(APIFailure) -> URL {
        let output = try await APIFailure.perform {
            // The broker sends the user back to the website's brokerage page
            // when they finish; the app re-reads the status when the sheet
            // closes, whichever page it ended on.
            try await client.snaptradeConnectApiSnaptradeConnectPost(
                body: .json(.init(returnPath: "/account/brokerage"))
            )
        }
        switch output {
        case .ok(let ok):
            guard case .json(let response) = ok.body,
                  let url = URL(string: response.redirectUri),
                  url.scheme == "https"
            else { throw .server(status: 200) }
            return url
        case .unprocessableContent:
            throw .server(status: 422)
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    public func accounts() async throws(APIFailure) -> [BrokerAccount] {
        let output = try await APIFailure.perform { try await client.snaptradeAccountsApiSnaptradeAccountsGet() }
        switch output {
        case .ok(let ok):
            guard case .json(let rows) = ok.body else { throw .server(status: 200) }
            return rows
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    /// What the brokers say the user holds — their view, not Livermore's
    /// tracked positions.
    public func holdings() async throws(APIFailure) -> [BrokerHolding] {
        let output = try await APIFailure.perform { try await client.snaptradePositionsApiSnaptradePositionsGet() }
        switch output {
        case .ok(let ok):
            guard case .json(let rows) = ok.body else { throw .server(status: 200) }
            return rows
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    /// Asks the broker to price an order. Nothing is sent to the market.
    public func preview(_ draft: OrderDraft) async throws(APIFailure) -> OrderPreview {
        if let problem = draft.problem { throw .rejected(problem) }
        var units: Double?
        var notional: Double?
        switch draft.size {
        case .sell(let shares): units = shares
        case .buy(let dollars): notional = dollars
        }
        let request = Components.Schemas.PreviewOrderRequest(
            accountId: draft.accountID, action: draft.action, notional: notional,
            orderType: "Market", symbol: draft.symbol, timeInForce: "Day", units: units
        )
        let output = try await APIFailure.perform {
            try await client.previewOrderApiSnaptradeOrdersPreviewPost(body: .json(request))
        }
        switch output {
        case .ok(let ok):
            guard case .json(let preview) = ok.body else { throw .server(status: 200) }
            return preview
        case .unprocessableContent:
            throw .rejected("Your broker couldn't price this order. Check the ticker and the amount.")
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    /// Sends an order the user has already seen priced. This is the one call
    /// in the app that moves real money, and it takes nothing but the id of
    /// the preview — it cannot place an order that was not shown first.
    public func place(_ preview: OrderPreview) async throws(APIFailure) -> OrderReceipt {
        let output = try await APIFailure.perform {
            try await client.placeOrderApiSnaptradeOrdersPlacePost(body: .json(.init(tradeId: preview.tradeId)))
        }
        switch output {
        case .ok(let ok):
            guard case .json(let receipt) = ok.body else { throw .server(status: 200) }
            return receipt
        case .unprocessableContent:
            throw .rejected("This order can't be sent. Price it again.")
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }
}

extension Components.Schemas.SnapTradeStatus {
    /// The user has authorised at least one brokerage account.
    public var isLinked: Bool { registered && connectedAccounts > 0 }

    /// Orders can be previewed and placed: linked, and the backend has order
    /// placement switched on (it has its own switch, off by default).
    public var canTrade: Bool { isLinked && tradingEnabled == true }
}

extension Components.Schemas.BrokerAccountView {
    /// "Robinhood ···4821", "Schwab — Individual", or whatever the broker
    /// gave us to tell accounts apart.
    public var displayName: String {
        let institution = institutionName ?? name ?? "Brokerage account"
        if let number, number.count >= 4 { return "\(institution) ···\(number.suffix(4))" }
        if let name, name != institution { return "\(institution) — \(name)" }
        return institution
    }
}

extension Components.Schemas.BrokerPositionView {
    /// Market value at the broker's last price, when it reported one.
    public var marketValue: Double? { lastPrice.map { $0 * units } }
}
