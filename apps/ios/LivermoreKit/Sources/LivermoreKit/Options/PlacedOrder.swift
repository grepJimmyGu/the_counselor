import Foundation
import LivermoreAPI

public typealias OptionOrderLookup = Components.Schemas.OptionOrderLookup
public typealias OptionOrderAtBroker = Components.Schemas.OptionOrderView

/// A broker's own app, opened so the user can enter an order there.
///
/// Neither address takes an order: it only brings the right app forward at
/// the nearest screen. Both are paths the broker itself declares its app
/// opens (its published `apple-app-site-association`, read 2026-11-23).
public struct BrokerApp: Equatable, Sendable {
    /// "Schwab", as the button names it.
    public let name: String
    public let url: URL

    /// Nil for a broker with no known address; the user switches apps by hand.
    public init?(institution: String?, symbol: String) {
        let broker = (institution ?? "").lowercased()
        let ticker = symbol.uppercased().addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? ""
        if broker.contains("schwab") {
            name = "Schwab"
            // The trade ticket. Schwab documents no way to name the symbol.
            url = URL(string: "https://client.schwab.com/secure/cc/trade/allinone")!
        } else if broker.contains("robinhood"), !ticker.isEmpty {
            name = "Robinhood"
            // The stock's page; options are under Trade from there.
            url = URL(string: "https://robinhood.com/stocks/\(ticker)")!
        } else {
            return nil
        }
    }
}

/// What the user's broker has on file for a plan's option order, in words.
///
/// The order was typed in at the broker by hand, so this is the only way the
/// app learns it is there. It reports what the broker says and nothing more.
public struct PlacedOrderReading: Equatable, Sendable {
    public enum Outcome: Equatable, Sendable {
        /// At the broker and still open.
        case placed
        case filled
        /// An order for this contract is there, but not the one in the plan.
        case differs
        /// Cancelled, rejected or expired.
        case ended
        /// The broker has an order whose status this app does not know.
        case unclear
        case notFound
    }

    public let outcome: Outcome
    public let headline: String
    public let detail: String

    /// `accountName` gives the name to show for an account id ("Schwab ···374").
    public init(
        plan: OptionPlan,
        lookup: OptionOrderLookup,
        accountName: (String) -> String? = { _ in nil },
        timeZone: TimeZone = .current
    ) {
        guard let order = Self.mostRelevant(lookup.orders) else {
            outcome = .notFound
            headline = "No order for this contract at your broker yet."
            detail = lookup.live
                ? "Livermore read your orders from the last week, open ones included. Place the order, then check again."
                : "Your broker's recent orders couldn't be read just now, only a copy that is refreshed once a day. An order placed today may not show until tomorrow."
            return
        }
        let broker = accountName(order.accountId) ?? "your broker"
        let description = Self.describe(order, timeZone: timeZone)
        let mismatch = Self.mismatch(order, plan: plan)

        switch order.state {
        case "working", "partly_filled", "filled":
            if let mismatch {
                outcome = .differs
                headline = "There is an order at \(broker), but it isn't this plan."
                detail = "\(mismatch) \(description)"
            } else if order.state == "filled" {
                outcome = .filled
                headline = "Filled at \(broker)."
                detail = description
            } else if order.state == "partly_filled" {
                outcome = .placed
                headline = "Placed at \(broker). Partly filled."
                detail = description
            } else {
                outcome = .placed
                headline = "Placed at \(broker). Waiting to fill."
                detail = description
            }
        case "ended":
            outcome = .ended
            headline = "The order at \(broker) is no longer open."
            detail = "\(Self.sentenceCase(broker)) reports it as \(Self.plain(order.status)). \(description)"
        default:
            outcome = .unclear
            headline = "\(Self.sentenceCase(broker)) has an order for this contract."
            detail = "It reports the status as \(Self.plain(order.status)). \(description)"
        }
    }

    /// An open order says the most about "is it in?", then a filled one, then
    /// one that ended. Within each, the newest; the list arrives newest first.
    static func mostRelevant(_ orders: [OptionOrderAtBroker]) -> OptionOrderAtBroker? {
        let rank = ["working": 0, "partly_filled": 0, "filled": 1, "unknown": 2, "ended": 3]
        return orders.enumerated()
            .min { (rank[$0.element.state] ?? 2, $0.offset) < (rank[$1.element.state] ?? 2, $1.offset) }?
            .element
    }

    /// How the order differs from the plan, or nil when it is the plan's.
    static func mismatch(_ order: OptionOrderAtBroker, plan: OptionPlan) -> String? {
        let action = (order.action ?? "").uppercased()
        if action.contains("CLOSE") {
            return "It closes a position; this plan opens one."
        }
        let plansToBuy = plan.option.side == .buy
        if action.hasPrefix("BUY"), !plansToBuy {
            return "It is a buy; this plan sells the contract."
        }
        if action.hasPrefix("SELL"), plansToBuy {
            return "It is a sell; this plan buys the contract."
        }
        if let quantity = order.quantity, Int(quantity.rounded()) != plan.contracts {
            return "It is for \(OptionText.contracts(Int(quantity.rounded()))); this plan is for \(OptionText.contracts(plan.contracts))."
        }
        return nil
    }

    /// "Buy 1 contract, limit $9.50 per share, good for the day. Placed Nov 23, 8:31 PM."
    static func describe(_ order: OptionOrderAtBroker, timeZone: TimeZone) -> String {
        var parts: [String] = []
        let action = (order.action ?? "").uppercased()
        let verb = action.hasPrefix("BUY") ? "Buy" : action.hasPrefix("SELL") ? "Sell" : "Order for"
        if let quantity = order.quantity {
            parts.append("\(verb) \(OptionText.contracts(Int(quantity.rounded())))")
        } else {
            parts.append(verb == "Order for" ? "Order" : verb)
        }
        if let filled = order.filledQuantity, let quantity = order.quantity, filled > 0, filled < quantity {
            parts.append("\(Int(filled.rounded())) filled so far")
        }
        if let limit = order.limitPrice {
            parts.append("limit \(OptionText.price(limit)) per share")
        } else if let type = order.orderType, !type.isEmpty {
            parts.append("\(type.lowercased()) order")
        }
        switch (order.timeInForce ?? "").uppercased() {
        case "DAY": parts.append("good for the day")
        case "GTC": parts.append("good until cancelled")
        default: break
        }
        var sentence = parts.joined(separator: ", ") + "."
        if let placed = order.timePlaced.flatMap(Self.date) {
            let formatter = DateFormatter()
            formatter.locale = Locale(identifier: "en_US")
            formatter.timeZone = timeZone
            formatter.dateFormat = "MMM d, h:mm a"
            sentence += " Placed \(formatter.string(from: placed))."
        }
        return sentence
    }

    private static func date(_ text: String) -> Date? {
        let plain = ISO8601DateFormatter()
        if let date = plain.date(from: text) { return date }
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return fractional.date(from: text)
    }

    /// "PARTIAL_CANCELED" → "partial canceled".
    private static func plain(_ status: String?) -> String {
        guard let status, !status.isEmpty else { return "unknown" }
        return status.replacingOccurrences(of: "_", with: " ").lowercased()
    }

    private static func sentenceCase(_ text: String) -> String {
        text.prefix(1).uppercased() + text.dropFirst()
    }
}
