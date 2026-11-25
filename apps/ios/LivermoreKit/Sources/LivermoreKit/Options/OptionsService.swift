import Foundation
import LivermoreAPI
import OpenAPIRuntime

public typealias OptionChain = Components.Schemas.OptionChainView
public typealias OptionQuote = Components.Schemas.OptionContractView
public typealias OptionExpiration = Components.Schemas.OptionExpirationView
public typealias SavedOptionPlan = Components.Schemas.OptionPlanView

extension OptionQuote {
    public var legKind: OptionLeg.Kind { kind == .call ? .call : .put }

    /// Said when the price shown may not be the price the user gets: few
    /// contracts exist, or buyers and sellers are far apart. Nil otherwise.
    public var thinlyTraded: String? {
        // Against the quote the bid and ask belong to, not an estimate made since.
        let quoted = quotedMid ?? mid
        let gap = quoted > 0 ? (ask - bid) / quoted : 0
        guard openInterest < 100 || gap > 0.10 else { return nil }
        let open = openInterest == 1 ? "1 contract is open" : "\(openInterest) contracts are open"
        return "Thinly traded: \(open), buyers bid \(OptionText.price(bid)) and sellers ask \(OptionText.price(ask)). You may not get the price shown."
    }
}

extension OptionChain {
    /// The contracts of one kind, lowest strike first.
    public func quotes(_ kind: OptionLeg.Kind) -> [OptionQuote] {
        contracts.filter { $0.legKind == kind }.sorted { $0.strike < $1.strike }
    }

    /// The expiry this slice of the chain is for.
    public var selected: OptionExpiration? {
        expirations.first { $0.date == expiration }
    }

    /// The price range option prices imply by this expiry, or nil when the
    /// chain cannot say. What the at-the-money call and put cost together,
    /// either side of the stock's price: a description of prices, not a forecast.
    public var impliedRange: ClosedRange<Double>? {
        guard let move = selected?.impliedMovePct, move > 0 else { return nil }
        let swing = underlyingPrice * move / 100
        return max(underlyingPrice - swing, 0)...(underlyingPrice + swing)
    }

    /// Up to three expiries to offer first: the monthly ones about one, three
    /// and six months out. The rest are a tap away.
    public var quickExpirations: [OptionExpiration] {
        var picked: [OptionExpiration] = []
        for target in [30, 90, 180] {
            let found = expirations.first { $0.monthly && $0.days >= target }
            if let found, !picked.contains(where: { $0.date == found.date }) { picked.append(found) }
        }
        if !picked.contains(where: { $0.date == defaultExpiration }),
           let start = expirations.first(where: { $0.date == defaultExpiration }) {
            picked.insert(start, at: 0)
        }
        return picked
    }
}

extension OptionExpiration {
    /// "Jan 15 · 56 days".
    public var label: String {
        "\(OptionText.shortDay(date)) · \(days == 1 ? "1 day" : "\(days) days")"
    }
}

/// A plan being put together: a strategy, one expiry of the chain, and the
/// strike and size chosen so far.
public struct OptionPlanDraft: Equatable, Sendable {
    public static let maxContracts = 50

    public let strategy: OptionStrategy
    public private(set) var chain: OptionChain
    public private(set) var strike: Double
    public var contracts: Int {
        didSet { contracts = min(max(contracts, 1), Self.maxContracts) }
    }

    /// Nil when this expiry has no contract of the kind the strategy needs.
    /// `near` keeps a strike already chosen when the expiry changes; without
    /// it the strategy's own starting strike is used.
    public init?(strategy: OptionStrategy, chain: OptionChain, near strike: Double? = nil, contracts: Int = 1) {
        let strikes = chain.quotes(strategy.optionKind).map { $0.strike }
        let start = strike.flatMap { wanted in strikes.min { abs($0 - wanted) < abs($1 - wanted) } }
            ?? strategy.defaultStrike(in: strikes, price: chain.underlyingPrice)
        guard let start else { return nil }
        self.strategy = strategy
        self.chain = chain
        self.strike = start
        self.contracts = min(max(contracts, 1), Self.maxContracts)
    }

    /// The contracts the strike can be moved across, lowest strike first.
    public var quotes: [OptionQuote] { chain.quotes(strategy.optionKind) }

    public var quote: OptionQuote { quotes.first { $0.strike == strike } ?? quotes[0] }

    /// Where the chosen strike sits in `quotes`, for a slider.
    public var strikeIndex: Int {
        get { quotes.firstIndex { $0.strike == strike } ?? 0 }
        set { strike = quotes[min(max(newValue, 0), quotes.count - 1)].strike }
    }

    /// "7.5% above the price", "at the price".
    public var strikeDistance: String {
        let gap = (strike - chain.underlyingPrice) / chain.underlyingPrice
        if abs(gap) < 0.005 { return "at the price" }
        return "\(OptionText.percent(gap)) \(gap > 0 ? "above" : "below") the price"
    }

    public var plan: OptionPlan {
        let quote = quote
        return OptionPlan(
            symbol: chain.symbol,
            strategy: strategy,
            legs: strategy.legs(
                strike: quote.strike, expiration: chain.expiration, contractID: quote.contractId,
                premium: quote.mid, quotedPremium: chain.estimatedAt == nil ? nil : quote.quotedMid,
                contracts: contracts, underlyingPrice: chain.underlyingPrice
            ),
            underlyingPrice: chain.underlyingPrice,
            asOf: chain.asOf,
            estimatedAt: chain.estimatedAt
        )!
    }
}

extension SavedOptionPlan {
    /// The saved legs as a plan, or nil for a strategy this build does not
    /// know, so a newer backend cannot make an older app show wrong numbers.
    public var plan: OptionPlan? {
        guard let strategy = OptionStrategy(rawValue: strategy) else { return nil }
        let legs = legs.map { leg in
            OptionLeg(
                kind: OptionLeg.Kind(rawValue: leg.kind.rawValue) ?? .stock,
                side: leg.side == .buy ? .buy : .sell,
                quantity: leg.quantity, price: leg.price, quotedPrice: leg.quotedPrice,
                strike: leg.strike, expiration: leg.expiration, contractID: leg.contractId
            )
        }
        return OptionPlan(symbol: symbol, strategy: strategy, legs: legs, underlyingPrice: underlyingPrice, asOf: asOf)
    }
}

/// Option chains and the plans a user has saved.
public struct OptionsService: Sendable {
    let client: Client

    public init(client: Client) {
        self.client = client
    }

    /// One expiry of `symbol`'s chain: the default one, or `expiration` ("2027-01-15").
    ///
    /// Asked for at the stock's price now: when that is from a later session
    /// than the option quotes, every contract's price comes back as an
    /// estimate for it, and `estimatedAt` says so.
    public func chain(_ symbol: String, expiration: String? = nil) async throws(APIFailure) -> OptionChain {
        let output = try await APIFailure.perform {
            try await client.getChainApiOptionsSymbolChainGet(
                path: .init(symbol: symbol), query: .init(expiration: expiration, estimate: true)
            )
        }
        switch output {
        case .ok(let ok):
            guard case .json(let chain) = ok.body else { throw .server(status: 200) }
            return chain
        case .unprocessableContent:
            throw .server(status: 422)
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    public func plans() async throws(APIFailure) -> [SavedOptionPlan] {
        let output = try await APIFailure.perform { try await client.listPlansApiOptionsPlansGet() }
        switch output {
        case .ok(let ok):
            guard case .json(let rows) = ok.body else { throw .server(status: 200) }
            return rows
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    @discardableResult
    public func save(_ plan: OptionPlan) async throws(APIFailure) -> SavedOptionPlan {
        let legs = plan.legs.map { leg in
            Components.Schemas.OptionLeg(
                contractId: leg.contractID, expiration: leg.expiration,
                kind: .init(rawValue: leg.kind.rawValue) ?? .stock,
                price: leg.price, quantity: leg.quantity, quotedPrice: leg.quotedPrice,
                side: leg.side == .buy ? .buy : .sell, strike: leg.strike
            )
        }
        let output = try await APIFailure.perform {
            try await client.savePlanApiOptionsPlansPost(body: .json(.init(
                asOf: plan.asOf, legs: legs,
                strategy: .init(rawValue: plan.strategy.rawValue) ?? .longCall,
                symbol: plan.symbol, underlyingPrice: plan.underlyingPrice
            )))
        }
        switch output {
        case .created(let created):
            guard case .json(let saved) = created.body else { throw .server(status: 201) }
            return saved
        case .unprocessableContent:
            throw .rejected("This plan couldn't be saved as it is.")
        case .undocumented(let status, let payload):
            // 409: the account already holds as many plans as it can.
            if status == 409 {
                throw .rejected("You have saved as many plans as an account can hold. Delete one to save another.")
            }
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    public func delete(id: String) async throws(APIFailure) {
        let output = try await APIFailure.perform {
            try await client.deletePlanApiOptionsPlansPlanIdDelete(path: .init(planId: id))
        }
        switch output {
        case .noContent: return
        case .unprocessableContent: throw .server(status: 422)
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    /// What to tell the user when the chain did not load. The backend's 404s
    /// here are written for them ("There are no listed options for LCUT.");
    /// a bare "Not Found" means the backend is older than the app.
    public static func message(for failure: APIFailure) -> String {
        if case .unavailable(let reason) = failure {
            if reason.isEmpty || reason == "Not Found" { return "Options aren't available yet. Try again later." }
            return APIFailure.presentable(reason) ?? failure.message
        }
        return failure.message
    }
}
