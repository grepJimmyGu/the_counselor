import Foundation

/// One line of an option plan: shares, or contracts of one option.
public struct OptionLeg: Equatable, Sendable {
    public enum Kind: String, Sendable { case stock, call, put }
    public enum Side: String, Sendable { case buy, sell }

    public var kind: Kind
    public var side: Side
    /// Shares for a stock leg, contracts (of 100 shares) for an option leg.
    public var quantity: Int
    /// Per share: as quoted at the close, or an estimate for the stock's
    /// price now (`quotedPrice` is then set).
    public var price: Double
    /// Only when `price` is an estimate: the quote at the close it came from.
    public var quotedPrice: Double?
    public var strike: Double?
    /// "2027-01-15".
    public var expiration: String?
    public var contractID: String?

    public init(
        kind: Kind, side: Side, quantity: Int, price: Double, quotedPrice: Double? = nil,
        strike: Double? = nil, expiration: String? = nil, contractID: String? = nil
    ) {
        self.kind = kind
        self.side = side
        self.quantity = quantity
        self.price = price
        self.quotedPrice = quotedPrice
        self.strike = strike
        self.expiration = expiration
        self.contractID = contractID
    }

    /// The shares this leg stands for: a contract is 100 of them.
    public var shares: Double { kind == .stock ? Double(quantity) : Double(quantity) * 100 }

    var sign: Double { side == .buy ? 1 : -1 }

    /// What one share's worth of this leg is worth at expiry with the stock at `price`.
    func value(at price: Double) -> Double {
        switch kind {
        case .stock: price
        case .call: max(price - (strike ?? 0), 0)
        case .put: max((strike ?? 0) - price, 0)
        }
    }

    /// How fast this leg's profit grows per dollar the stock rises, once the
    /// stock is above every strike.
    var slopeAbove: Double {
        kind == .put ? 0 : sign * shares
    }
}

/// What a set of legs makes or loses at expiry, for any price the stock
/// could be at. Arithmetic on the prices paid and the strikes, nothing more:
/// no pricing model and no probabilities.
///
/// Profit against the stock price is a line with corners at the strikes, so
/// its highest and lowest points and where it crosses zero are found from the
/// corners and the slope past the last one. That holds for any mix of legs,
/// so spreads and collars need nothing new here.
public struct OptionPayoff: Equatable, Sendable {
    public let legs: [OptionLeg]

    public init(legs: [OptionLeg]) {
        self.legs = legs
    }

    public func profit(at price: Double) -> Double {
        let price = max(price, 0)
        return legs.reduce(0) { $0 + $1.sign * $1.shares * ($1.value(at: price) - $1.price) }
    }

    /// Money that changes hands for the options today: positive is paid,
    /// negative is received. Shares in a plan are ones already held.
    public var cashNow: Double {
        legs.filter { $0.kind != .stock }.reduce(0) { $0 + $1.sign * $1.shares * $1.price }
    }

    /// Zero and every strike, in order: the only places the line can turn.
    private var corners: [Double] {
        ([0] + legs.compactMap(\.strike)).reduce(into: [Double]()) { if !$0.contains($1) { $0.append($1) } }.sorted()
    }

    private var slopeAboveLastCorner: Double {
        legs.reduce(0) { $0 + $1.slopeAbove }
    }

    /// The most this can make, or nil when there is no limit.
    public var maxGain: Double? {
        slopeAboveLastCorner > 0 ? nil : corners.map(profit(at:)).max()
    }

    /// The most this can lose, as a positive amount, or nil when there is no limit.
    public var maxLoss: Double? {
        slopeAboveLastCorner < 0 ? nil : corners.map(profit(at:)).min().map { max(-$0, 0) }
    }

    /// The stock prices at which this neither makes nor loses money, lowest first.
    public var breakevens: [Double] {
        let points = corners.map { ($0, profit(at: $0)) }
        var found: [Double] = []
        for (a, b) in zip(points, points.dropFirst()) where (a.1 < 0 && b.1 > 0) || (a.1 > 0 && b.1 < 0) {
            found.append(a.0 + (b.0 - a.0) * (0 - a.1) / (b.1 - a.1))
        }
        if let last = points.last {
            let slope = slopeAboveLastCorner
            if (last.1 < 0 && slope > 0) || (last.1 > 0 && slope < 0) {
                found.append(last.0 - last.1 / slope)
            }
        }
        return found
    }

    /// Stock prices to draw the line through: the range given, plus every
    /// corner and breakeven inside it, so the chart turns exactly where the
    /// numbers say it does.
    public func curve(from low: Double, to high: Double) -> [(price: Double, profit: Double)] {
        let inside = (corners + breakevens).filter { $0 > low && $0 < high }
        return ([low] + inside + [high]).sorted().map { ($0, profit(at: $0)) }
    }
}
