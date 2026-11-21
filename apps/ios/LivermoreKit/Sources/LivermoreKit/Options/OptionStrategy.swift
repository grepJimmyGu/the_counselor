import Foundation

/// The four things a first-time user can set out to do with an option.
public enum OptionStrategy: String, CaseIterable, Identifiable, Sendable {
    case longCall = "long_call"
    case longPut = "long_put"
    case coveredCall = "covered_call"
    case protectivePut = "protective_put"

    public var id: String { rawValue }

    /// What the user wants, in their words. The card's title.
    public var goal: String {
        switch self {
        case .longCall: "I think it will go up"
        case .longPut: "I think it will go down"
        case .coveredCall: "Earn income on shares I own"
        case .protectivePut: "Protect shares I own"
        }
    }

    /// What the trade is called.
    public var name: String {
        switch self {
        case .longCall: "Buy a call"
        case .longPut: "Buy a put"
        case .coveredCall: "Sell a covered call"
        case .protectivePut: "Buy a protective put"
        }
    }

    /// One line on what the trade is, for the card.
    public func explanation(symbol: String) -> String {
        switch self {
        case .longCall:
            "Pay a fee now for the right to buy \(symbol) at a set price later. You can lose the fee and no more."
        case .longPut:
            "Pay a fee now for the right to sell \(symbol) at a set price later. You can lose the fee and no more."
        case .coveredCall:
            "Get paid now for agreeing to sell your \(symbol) shares at a higher price if it gets there."
        case .protectivePut:
            "Pay a fee now so your \(symbol) shares can be sold at a set price however far they fall."
        }
    }

    /// What the user has to have to do it.
    public var needs: String {
        ownsShares ? "Needs 100 shares" : "Needs cash for the fee"
    }

    public var optionKind: OptionLeg.Kind {
        switch self {
        case .longCall, .coveredCall: .call
        case .longPut, .protectivePut: .put
        }
    }

    public var optionSide: OptionLeg.Side { self == .coveredCall ? .sell : .buy }

    /// Whether the plan is about shares the user already holds.
    public var ownsShares: Bool { self == .coveredCall || self == .protectivePut }

    /// Where the strike starts, out of the strikes on offer. A starting point
    /// the user moves, not advice: at today's price when buying a call or a
    /// put, and 5% away from it when the plan is about shares already held
    /// (above for a call sold against them, below for a put protecting them).
    public func defaultStrike(in strikes: [Double], price: Double) -> Double? {
        let sorted = strikes.sorted()
        switch self {
        case .longCall, .longPut:
            return sorted.min { abs($0 - price) < abs($1 - price) }
        case .coveredCall:
            return sorted.first { $0 >= price * 1.05 } ?? sorted.last
        case .protectivePut:
            return sorted.last { $0 <= price * 0.95 } ?? sorted.first
        }
    }

    /// The plan's legs: the option, and the shares it is written against.
    public func legs(
        strike: Double, expiration: String, contractID: String, premium: Double,
        contracts: Int, underlyingPrice: Double
    ) -> [OptionLeg] {
        let option = OptionLeg(
            kind: optionKind, side: optionSide, quantity: contracts, price: premium,
            strike: strike, expiration: expiration, contractID: contractID
        )
        guard ownsShares else { return [option] }
        // Shares already held, measured from today's price.
        return [OptionLeg(kind: .stock, side: .buy, quantity: contracts * 100, price: underlyingPrice), option]
    }
}

/// The words a first-time user meets, each explained in a sentence where it
/// appears rather than in an introduction.
public enum OptionTerm: String, CaseIterable, Sendable {
    case call, put, strike, expiry, contract, fee, breakeven, bidAsk, openContracts, impliedRange

    public var title: String {
        switch self {
        case .call: "Call"
        case .put: "Put"
        case .strike: "Strike"
        case .expiry: "Expiry"
        case .contract: "Contracts"
        case .fee: "Fee"
        case .breakeven: "Breakeven"
        case .bidAsk: "Bid and ask"
        case .openContracts: "Open contracts"
        case .impliedRange: "Implied range"
        }
    }

    public var meaning: String {
        switch self {
        case .call:
            "A call is the right to buy 100 shares at the strike price, any time until it expires."
        case .put:
            "A put is the right to sell 100 shares at the strike price, any time until it expires."
        case .strike:
            "The strike is the share price the option lets you buy or sell at."
        case .expiry:
            "The expiry is the last day the option can be used. After it, the option is worth nothing."
        case .contract:
            "One contract covers 100 shares, so an option priced at $2.50 costs $250."
        case .fee:
            "The fee (also called the premium) is what the option costs. The buyer pays it and the seller keeps it, whatever happens next."
        case .breakeven:
            "The breakeven is the share price at expiry where you neither make nor lose money."
        case .bidAsk:
            "Bid is the most a buyer is offering. Ask is the least a seller will take. Plans here use the price halfway between."
        case .openContracts:
            "How many of this option exist right now. More usually means it is easier to trade at a fair price."
        case .impliedRange:
            "What the call and the put at the stock's price cost together, added to and taken from the share price. It is the size of move option prices are charging for, not a forecast."
        }
    }
}
