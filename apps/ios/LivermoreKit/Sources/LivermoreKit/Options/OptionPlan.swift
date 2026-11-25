import Foundation

/// Numbers and dates written the same way wherever a plan is described.
/// A fixed US format, so the sentences read the same on every device.
public enum OptionText {
    private static let us = Locale(identifier: "en_US")

    /// A total in whole dollars: "$1,423". One contract is 100 shares and
    /// prices are in cents, so a plan's totals are always whole dollars.
    public static func dollars(_ amount: Double) -> String {
        amount.rounded().formatted(.currency(code: "USD").precision(.fractionLength(0)).locale(us))
    }

    /// A price per share: "$139.23".
    public static func price(_ amount: Double) -> String {
        amount.formatted(.currency(code: "USD").precision(.fractionLength(2)).locale(us))
    }

    /// A strike: "$125", or "$127.50" when it is not a whole dollar.
    public static func strike(_ amount: Double) -> String {
        amount == amount.rounded() ? dollars(amount) : price(amount)
    }

    /// A fraction as a percentage without a sign: 0.109 → "10.9%".
    public static func percent(_ fraction: Double) -> String {
        String(format: "%.1f%%", abs(fraction) * 100)
    }

    private static func date(_ iso: String) -> Date? {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.date(from: iso)
    }

    private static func format(_ iso: String, _ pattern: String) -> String {
        guard let date = date(iso) else { return iso }
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = us
        // Parsed as midnight UTC, so printed in UTC: in the device's own zone
        // anyone west of Greenwich would see the day before.
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = pattern
        return formatter.string(from: date)
    }

    /// "Jan 15, 2027" from "2027-01-15".
    public static func day(_ iso: String) -> String { format(iso, "MMM d, yyyy") }

    /// "Jan 15" from "2027-01-15".
    public static func shortDay(_ iso: String) -> String { format(iso, "MMM d") }

    /// "1 contract", "3 contracts".
    public static func contracts(_ count: Int) -> String {
        count == 1 ? "1 contract" : "\(count) contracts"
    }
}

/// One number on a plan, with the sentence that says what it means.
public struct OptionFigure: Equatable, Sendable, Identifiable {
    public let label: String
    public let value: String
    public let detail: String
    public var id: String { label }
}

/// An option plan: the legs, and everything worked out from them.
///
/// Every number is arithmetic on the legs' own prices (`OptionPayoff`), so a
/// plan read back from the server says exactly what it said when it was built.
public struct OptionPlan: Equatable, Sendable {
    public let symbol: String
    public let strategy: OptionStrategy
    public let legs: [OptionLeg]
    /// The stock's price the plan was built on.
    public let underlyingPrice: Double
    /// The trading day the option quotes are from.
    public let asOf: String
    /// When the stock traded at `underlyingPrice`, for a plan whose option
    /// price is an estimate for that moment. Nil when every price is the
    /// close's on `asOf`, and for a saved plan (see `isEstimated`).
    public let estimatedAt: Date?

    /// Nil unless the legs have exactly the one option leg a strategy here has.
    public init?(
        symbol: String, strategy: OptionStrategy, legs: [OptionLeg], underlyingPrice: Double, asOf: String,
        estimatedAt: Date? = nil
    ) {
        let options = legs.filter { $0.kind != .stock }
        guard options.count == 1, let option = options.first,
              option.strike != nil, option.expiration != nil, underlyingPrice > 0
        else { return nil }
        self.symbol = symbol
        self.strategy = strategy
        self.legs = legs
        self.underlyingPrice = underlyingPrice
        self.asOf = asOf
        self.estimatedAt = estimatedAt
    }

    public var payoff: OptionPayoff { OptionPayoff(legs: legs) }

    /// The option's price is an estimate for a stock price later than the
    /// close its quote is from, not a quote.
    public var isEstimated: Bool { option.quotedPrice != nil }

    public var option: OptionLeg { legs.first { $0.kind != .stock }! }
    public var contracts: Int { option.quantity }
    public var strike: Double { option.strike ?? 0 }
    public var expiration: String { option.expiration ?? "" }
    public var shares: Int { contracts * 100 }

    /// What changes hands today, as a positive amount, and which way.
    public var cashNow: Double { abs(payoff.cashNow) }
    public var paysNow: Bool { payoff.cashNow >= 0 }

    public var maxLoss: Double? { payoff.maxLoss }
    public var maxGain: Double? { payoff.maxGain }
    public var breakeven: Double? { payoff.breakevens.first }

    /// How far the stock is from the breakeven, as a fraction of its price:
    /// positive when the breakeven is above it.
    public var moveToBreakeven: Double? {
        breakeven.map { ($0 - underlyingPrice) / underlyingPrice }
    }

    // MARK: Sentences

    /// The whole trade in a sentence or two.
    public var headline: String {
        let cash = OptionText.dollars(cashNow), k = OptionText.strike(strike), day = OptionText.day(expiration)
        let even = breakeven.map(OptionText.price) ?? k
        switch strategy {
        case .longCall:
            return "Pay \(cash) now. You profit if \(symbol) is above \(even) on \(day)."
        case .longPut:
            return "Pay \(cash) now. You profit if \(symbol) is below \(even) on \(day)."
        case .coveredCall:
            return "Receive \(cash) now. In return you sell your \(shares) \(symbol) shares at \(k) if \(symbol) is above that on \(day)."
        case .protectivePut:
            return "Pay \(cash) now. Until \(day) your \(shares) \(symbol) shares can be sold at \(k), however far the price falls."
        }
    }

    /// Cost, the most that can be lost, what can be made, and the breakeven.
    public var figures: [OptionFigure] {
        let k = OptionText.strike(strike), day = OptionText.shortDay(expiration)
        let cash = OptionText.dollars(cashNow), today = OptionText.price(underlyingPrice)
        let even = breakeven.map(OptionText.price) ?? "—"
        let move = moveToBreakeven.map(OptionText.percent) ?? "—"
        let cost = OptionFigure(
            label: paysNow ? "You pay now" : "You receive now",
            value: cash,
            detail: "\(OptionText.contracts(contracts)) × 100 shares × \(OptionText.price(option.price))"
        )
        let loss: String, gain: String, evenDetail: String
        var gainFigure: OptionFigure?
        switch strategy {
        case .longCall:
            loss = "If \(symbol) is at or below \(k) on \(day)"
            gain = "The further \(symbol) is above \(even), the more you make"
            evenDetail = "\(symbol) needs to rise \(move) from \(today)"
        case .longPut:
            loss = "If \(symbol) is at or above \(k) on \(day)"
            // A put's gain tops out only with the stock at $0, which is not
            // an outcome to headline. Lead with what each $1 of fall is worth
            // and leave the ceiling in the small print.
            let ceiling = maxGain.map(OptionText.dollars) ?? "—"
            gain = "For each $1 \(symbol) is below \(even) on \(day). It tops out at \(ceiling), only if \(symbol) went to $0."
            gainFigure = OptionFigure(
                label: "What you can make",
                value: "\(OptionText.dollars(Double(shares))) per $1 fall",
                detail: gain
            )
            evenDetail = "\(symbol) needs to fall \(move) from \(today)"
        case .coveredCall:
            loss = "If \(symbol) falls to $0. The \(cash) is yours either way"
            gain = "If \(symbol) is at or above \(k) on \(day)"
            evenDetail = "\(symbol) can fall \(move) from \(today) before you are behind"
        case .protectivePut:
            loss = "If \(symbol) is at or below \(k) on \(day)"
            gain = "Your shares still rise with \(symbol)"
            evenDetail = "\(symbol) needs to rise \(move) from \(today) to cover the fee"
        }
        return [
            cost,
            OptionFigure(label: "Most you can lose", value: maxLoss.map(OptionText.dollars) ?? "No limit", detail: loss),
            gainFigure ?? OptionFigure(label: "Most you can make", value: maxGain.map(OptionText.dollars) ?? "No limit", detail: gain),
            OptionFigure(label: "Breakeven", value: even, detail: evenDetail),
        ]
    }

    /// What the plan comes to with the stock at `price` on the expiry, with
    /// the parts that make it up: "If REGN is at $995.00 on Jan 15, the call is
    /// worth $4,500. You paid $4,685, so you lose $185."
    ///
    /// The parts are there so the result can be checked by eye. Jimmy,
    /// 2026-11-24: "at $995 you lose $185" on a $950 call read as wrong; it was
    /// right, because the call cost more ($46.85 a share) than the $45 it is
    /// worth at $995, and the sentence did not say so.
    ///
    /// The total is the sum of the whole-dollar parts shown, so the sentence
    /// always adds up; it can differ by $1 from the chart's exact figure when
    /// a premium has a half cent.
    public func outcome(at price: Double) -> String {
        let at = "If \(symbol) is at \(OptionText.price(price)) on \(OptionText.shortDay(expiration))"
        let n = Double(shares)
        let fee = (option.price * n).rounded()
        let worth = (option.value(at: price) * n).rounded()
        let name = option.kind.rawValue
        let today = OptionText.price(underlyingPrice)
        let total: Double
        let story: String
        switch strategy {
        case .longCall, .longPut:
            total = worth - fee
            let value = worth == 0 ? "the \(name) expires worthless" : "the \(name) is worth \(OptionText.dollars(worth))"
            story = "\(at), \(value). You paid \(OptionText.dollars(fee)), so"
        case .coveredCall:
            if worth == 0 {
                let shares = ((price - underlyingPrice) * n).rounded()
                total = shares + fee
                story = "\(at), the call expires worthless. Your shares are \(Self.change(shares)) from \(today) and you keep the \(OptionText.dollars(fee)) you received, so"
            } else {
                let sold = ((strike - underlyingPrice) * n).rounded()
                total = sold + fee
                story = "\(at), your shares are sold at \(OptionText.strike(strike)), \(Self.gap(sold)) \(today), and you keep the \(OptionText.dollars(fee)) you received, so"
            }
        case .protectivePut:
            if worth == 0 {
                let shares = ((price - underlyingPrice) * n).rounded()
                total = shares - fee
                story = "\(at), the put expires worthless. Your shares are \(Self.change(shares)) from \(today) and the put cost \(OptionText.dollars(fee)), so"
            } else {
                let sold = ((strike - underlyingPrice) * n).rounded()
                total = sold - fee
                story = "\(at), the put lets you sell your shares at \(OptionText.strike(strike)), \(Self.gap(sold)) \(today). The put cost \(OptionText.dollars(fee)), so"
            }
        }
        if total == 0 { return "\(story) you break even." }
        return "\(story) you \(total > 0 ? "make" : "lose") \(OptionText.dollars(abs(total)))."
    }

    /// "up $447", "down $1,553", "unchanged".
    private static func change(_ amount: Double) -> String {
        amount == 0 ? "unchanged" : "\(amount > 0 ? "up" : "down") \(OptionText.dollars(abs(amount)))"
    }

    /// "$947 above", "$553 below", "the same as".
    private static func gap(_ amount: Double) -> String {
        amount == 0 ? "the same as" : "\(OptionText.dollars(abs(amount))) \(amount > 0 ? "above" : "below")"
    }

    /// Something the user should know that the numbers do not show.
    public var caution: String? {
        guard strategy == .coveredCall else { return nil }
        return "The buyer can take your shares at \(OptionText.strike(strike)) before \(OptionText.shortDay(expiration)), most often just before a dividend."
    }

    /// A one-line name for lists: "NVDA $125 call · Jan 15, 2027".
    public var title: String {
        "\(symbol) \(OptionText.strike(strike)) \(option.kind.rawValue) · \(OptionText.day(expiration))"
    }

    /// The stock prices worth drawing: the stock's price, the strike, the
    /// breakeven and the implied range, with room either side.
    public func chartRange(including implied: ClosedRange<Double>? = nil) -> ClosedRange<Double> {
        var marks = [underlyingPrice, strike, breakeven ?? underlyingPrice]
        if let implied { marks += [implied.lowerBound, implied.upperBound] }
        let low = max((marks.min() ?? underlyingPrice) * 0.88, 0)
        let high = (marks.max() ?? underlyingPrice) * 1.12
        return low...high
    }
}

/// The plan written out for a broker's order screen.
public struct OptionTicket: Equatable, Sendable {
    public struct Line: Equatable, Sendable, Identifiable {
        /// "Buy to open" or "Sell to open".
        public let action: String
        /// "1 NVDA Jan 15, 2027 $125 call".
        public let contract: String
        /// "Limit $14.23".
        public let limit: String
        /// The exchange's own symbol for the contract: "NVDA270115C00125000".
        public let contractSymbol: String
        public var id: String { contractSymbol }
    }

    public let lines: [Line]
    /// What must already be in the account, if anything.
    public let requirement: String?
    public let asOf: String
    /// The limit prices are estimates, not quotes, and what they were at the close.
    public let isEstimated: Bool
    private let quotedLimit: String?

    public init(plan: OptionPlan) {
        lines = plan.legs.filter { $0.kind != .stock }.map { leg in
            Line(
                action: leg.side == .buy ? "Buy to open" : "Sell to open",
                contract: "\(leg.quantity) \(plan.symbol) \(OptionText.day(leg.expiration ?? "")) \(OptionText.strike(leg.strike ?? 0)) \(leg.kind.rawValue)",
                limit: "Limit \(OptionText.price(leg.price))",
                contractSymbol: leg.contractID ?? ""
            )
        }
        requirement = plan.strategy.ownsShares ? "You need \(plan.shares) \(plan.symbol) shares in the same account." : nil
        asOf = plan.asOf
        isEstimated = plan.isEstimated
        quotedLimit = plan.option.quotedPrice.map(OptionText.price)
    }

    /// Where the limit price comes from, in a sentence.
    public var priceSource: String {
        guard isEstimated else { return "Prices from the close on \(OptionText.day(asOf))." }
        let quoted = quotedLimit.map { " (\($0) then)" } ?? ""
        return "The limit is an estimate from the stock's price since the close on \(OptionText.day(asOf))\(quoted), not a quote."
    }

    /// How to enter it at a broker, one step at a time.
    public var steps: [String] {
        guard let line = lines.first else { return [] }
        let parts = line.contract.split(separator: " ", maxSplits: 2).map(String.init)
        let symbol = parts.count > 1 ? parts[1] : ""
        let rest = parts.count > 2 ? parts[2] : ""
        let count = Int(parts.first ?? "") ?? 1
        return [
            "Open your broker's app and look up \(symbol) options. Your account has to be approved for options first; most brokers ask a few questions the first time.",
            "Find the contract: \(rest).",
            "Choose \(line.action), \(OptionText.contracts(count)).",
            "Set the order type to Limit. Check the price your broker shows now and set your limit near it; \(line.limit.dropFirst("Limit ".count)) \(isEstimated ? "is an estimate, not a quote" : "was the price at the last close").",
            "Read the broker's summary of the order, then send it.",
        ]
    }

    /// The ticket as text, for the clipboard.
    public var text: String {
        var rows = lines.flatMap { ["\($0.action) \($0.contract)", "\($0.limit) per share", "Contract \($0.contractSymbol)"] }
        if let requirement { rows.append(requirement) }
        rows.append("\(priceSource) Check the live price before you send it.")
        return rows.joined(separator: "\n")
    }
}
