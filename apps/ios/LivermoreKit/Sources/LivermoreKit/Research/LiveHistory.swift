import Foundation

// Daily closes stop at the last session that finished. During a session the
// price a person is looking at is somewhere else: on 2026-11-25 NVDA's newest
// close was $155.38 (and the app's copy stopped a day earlier, at $165.05)
// while the stock traded at $145.72. A chart, a trend line or a test built on
// closes alone was describing a price nobody could trade at.
//
// So the session under way is added as one more day, from the live quote.

extension MarketHours {
    /// The trading day a moment falls in: its New York calendar day, as the
    /// date a `DailyClose` carries (midnight UTC of that day).
    public static func tradingDay(of moment: Date) -> Date {
        var newYork = Calendar(identifier: .gregorian)
        newYork.timeZone = TimeZone(identifier: "America/New_York") ?? .gmt
        let parts = newYork.dateComponents([.year, .month, .day], from: moment)
        return PerformanceSeries.utc.date(from: parts) ?? moment
    }

    /// The most recent weekday whose 4 pm New York close has passed, as a
    /// `DailyClose` date. Holidays are not known here and count as sessions;
    /// that only means looking for a close that will not arrive.
    public static func lastCompletedSession(at now: Date) -> Date {
        var newYork = Calendar(identifier: .gregorian)
        newYork.timeZone = TimeZone(identifier: "America/New_York") ?? .gmt
        let utc = PerformanceSeries.utc
        var day = tradingDay(of: now)
        if newYork.component(.hour, from: now) < 16 {
            day = utc.date(byAdding: .day, value: -1, to: day) ?? day
        }
        // 1 is Sunday, 7 is Saturday.
        while [1, 7].contains(utc.component(.weekday, from: day)) {
            day = utc.date(byAdding: .day, value: -1, to: day) ?? day
        }
        return day
    }
}

extension Array where Element == DailyClose {
    /// These closes with the session under way added from the live quote, so
    /// whatever is built on them ends at the price now.
    ///
    /// The quote's own trade time says which day it belongs to. A quote from
    /// a day that already has its close (overnight, a weekend, before the
    /// open) adds nothing: the close is the better record of that day.
    public func ending(at quote: LiveQuote?) -> [DailyClose] {
        guard let quote, quote.price > 0, let tradedAt = quote.asOf, let last else { return self }
        let day = MarketHours.tradingDay(of: Date(timeIntervalSince1970: tradedAt))
        guard day > last.date else { return self }
        return self + [DailyClose(date: day, close: quote.price, high: quote.dayHigh, low: quote.dayLow)]
    }

    /// Whether the last day here is a session still under way at `now`,
    /// rather than a finished close.
    public func endsLive(at now: Date) -> Bool {
        guard let last else { return false }
        return last.date > MarketHours.lastCompletedSession(at: now)
    }
}
