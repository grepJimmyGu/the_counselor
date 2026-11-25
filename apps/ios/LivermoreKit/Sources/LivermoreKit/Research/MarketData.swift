import Foundation
import LivermoreAPI
import OpenAPIRuntime

/// A price, the day's move and a month of closes for one symbol.
public typealias MarketSnapshot = Components.Schemas.MarketSnapshotItem

/// One day's closing price, adjusted for splits and dividends.
public struct DailyClose: Equatable, Sendable {
    public let date: Date
    public let close: Double
    /// The day's high and low, adjusted the same way as the close. Equal to
    /// the close when only closes are known.
    public let high: Double
    public let low: Double

    public init(date: Date, close: Double, high: Double? = nil, low: Double? = nil) {
        self.date = date
        self.close = close
        self.high = max(high ?? close, close)
        self.low = min(low ?? close, close)
    }
}

/// The periods the price chart offers.
public enum PerformanceRange: String, CaseIterable, Identifiable, Sendable {
    case oneMonth = "1M"
    case threeMonths = "3M"
    case sixMonths = "6M"
    case yearToDate = "YTD"
    case oneYear = "1Y"
    case fiveYears = "5Y"

    public var id: String { rawValue }

    /// The first day of the period that ends on `end`.
    func start(endingOn end: Date, calendar: Calendar) -> Date {
        switch self {
        case .oneMonth: calendar.date(byAdding: .month, value: -1, to: end) ?? end
        case .threeMonths: calendar.date(byAdding: .month, value: -3, to: end) ?? end
        case .sixMonths: calendar.date(byAdding: .month, value: -6, to: end) ?? end
        case .oneYear: calendar.date(byAdding: .year, value: -1, to: end) ?? end
        case .fiveYears: calendar.date(byAdding: .year, value: -5, to: end) ?? end
        case .yearToDate:
            // From the last close of the previous year, which is what
            // "year to date" is measured against.
            calendar.date(from: DateComponents(year: calendar.component(.year, from: end) - 1, month: 12, day: 25)) ?? end
        }
    }
}

/// A stock's price over a period, with its return and the S&P 500's over
/// the same days.
///
/// Built on the device from daily closes, so the chart, the period return
/// and the comparison all describe exactly the same days — and all end on
/// the stock's last day, which is the price now when the closes were given
/// the session under way (`ending(at:)`).
public struct PerformanceSeries: Equatable, Sendable {
    public struct Point: Equatable, Sendable, Identifiable {
        public let date: Date
        public let price: Double
        /// Return since the start of the period, as a fraction.
        public let stock: Double
        /// The benchmark's return over the same days; nil when it has no
        /// price for the period.
        public let benchmark: Double?

        public var id: Date { date }
    }

    public let range: PerformanceRange
    public let points: [Point]
    /// The stock's prices begin after the period does — a new listing, or a
    /// history shorter than the range. The chart then shows all of it and
    /// must not be titled "past year".
    public let isShorterThanRange: Bool
    /// Trading days in the period (before thinning for the chart).
    public let tradingDays: Int

    /// Charts read no more detail than this on a phone.
    static let maxPoints = 260

    public init(
        stock: [DailyClose], benchmark: [DailyClose], range: PerformanceRange,
        calendar: Calendar = PerformanceSeries.utc
    ) {
        self.range = range
        guard let end = stock.last?.date else {
            points = []
            isShorterThanRange = false
            tradingDays = 0
            return
        }
        let start = range.start(endingOn: end, calendar: calendar)
        var window = stock.filter { $0.date >= start && $0.close > 0 }
        var shorter = (stock.first { $0.close > 0 }?.date ?? end) > start
        // Year to date starts from last year's final close, not the first
        // one found after 25 December.
        if range == .yearToDate {
            let year = calendar.component(.year, from: end)
            let previous = window.last { calendar.component(.year, from: $0.date) < year }
            window = (previous.map { [$0] } ?? []) + window.filter { calendar.component(.year, from: $0.date) == year }
            shorter = previous == nil
        }
        isShorterThanRange = shorter
        tradingDays = window.count
        guard let first = window.first else {
            points = []
            return
        }

        // The benchmark's close on or before each day, so a holiday on one
        // side does not open a gap.
        let sorted = benchmark.filter { $0.close > 0 }
        var cursor = 0
        func benchmarkClose(onOrBefore date: Date) -> Double? {
            while cursor + 1 < sorted.count, sorted[cursor + 1].date <= date { cursor += 1 }
            guard cursor < sorted.count, sorted[cursor].date <= date else { return nil }
            return sorted[cursor].close
        }
        let benchmarkBase = benchmarkClose(onOrBefore: first.date)

        let step = max(1, window.count / Self.maxPoints)
        var built: [Point] = []
        for (index, bar) in window.enumerated() {
            let level = benchmarkClose(onOrBefore: bar.date)
            guard index % step == 0 || index == window.count - 1 else { continue }
            built.append(Point(
                date: bar.date, price: bar.close, stock: bar.close / first.close - 1,
                benchmark: benchmarkBase.flatMap { base in level.map { $0 / base - 1 } }
            ))
        }
        points = built
    }

    public static var utc: Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        return calendar
    }

    /// Return over the whole period.
    public var stockReturn: Double? { points.last?.stock }
    public var benchmarkReturn: Double? { points.last?.benchmark }

    /// How far ahead of (or behind) the benchmark, in fraction points.
    public var excessReturn: Double? {
        guard let stock = stockReturn, let benchmark = benchmarkReturn else { return nil }
        return stock - benchmark
    }
}

/// Daily price histories, fetched once per symbol and kept while the app
/// runs: cheap to hold for the handful a session looks at, and expensive to
/// refetch on every range change.
///
/// A history that has fallen behind (a close has passed since its last day)
/// is brought up to date with the days after it, not downloaded again, and
/// not more often than every five minutes: after a close the new day can
/// take a while to be published.
@MainActor
public final class PriceHistory {
    /// The closes for a symbol: all that are kept when `since` is nil,
    /// otherwise the days from `since` on.
    public typealias Fetch = @Sendable (_ symbol: String, _ since: Date?) async throws -> [DailyClose]

    public static let benchmarkSymbol = "SPY"
    static let capacity = 8
    /// How far back a history is asked for. The longest chart range and the
    /// plan test both read five years; the sixth is room for a range that
    /// starts just before the first bar. A stock listed since 1999 has 27
    /// years of bars (1.2 MB of JSON), which the app was downloading and
    /// decoding for every company page, twice, with the benchmark.
    public nonisolated static let yearsKept = 6
    /// How often a history that is behind is looked up again.
    public nonisolated static let recheckEvery: TimeInterval = 300

    private let fetch: Fetch
    private let now: @Sendable () -> Date
    private var cache: [String: [DailyClose]] = [:]
    private var order: [String] = []
    private var checked: [String: Date] = [:]

    public init(now: @escaping @Sendable () -> Date = { .now }, fetch: @escaping Fetch) {
        self.now = now
        self.fetch = fetch
    }

    public func closes(for symbol: String) async throws -> [DailyClose] {
        let symbol = symbol.uppercased()
        if let cached = cache[symbol] {
            order.removeAll { $0 == symbol }
            order.append(symbol)
            return await caughtUp(symbol, cached)
        }
        let loaded = try await fetch(symbol, nil)
        cache[symbol] = loaded
        checked[symbol] = now()
        order.append(symbol)
        // The benchmark is on every chart; never evict it.
        while order.count > Self.capacity, let oldest = order.first(where: { $0 != Self.benchmarkSymbol }) {
            order.removeAll { $0 == oldest }
            cache[oldest] = nil
            checked[oldest] = nil
        }
        return loaded
    }

    /// `cached`, with any closes that have passed since its last day. A
    /// failed look leaves what there is.
    private func caughtUp(_ symbol: String, _ cached: [DailyClose]) async -> [DailyClose] {
        let moment = now()
        guard let last = cached.last, last.date < MarketHours.lastCompletedSession(at: moment),
              moment.timeIntervalSince(checked[symbol] ?? .distantPast) >= Self.recheckEvery
        else { return cached }
        checked[symbol] = moment
        // From the last day held, so a day that was corrected is replaced.
        guard let newer = try? await fetch(symbol, last.date), let firstNew = newer.first else { return cached }
        let merged = cached.filter { $0.date < firstNew.date } + newer
        // Evicted while the request was out: hand back the answer, keep nothing.
        if cache[symbol] != nil { cache[symbol] = merged }
        return merged
    }
}

extension ResearchService {
    /// The endpoint's cap on symbols per request.
    static let snapshotBatch = 12

    /// Price, day's move and a month of closes for each symbol. Slow when
    /// the backend has not seen a symbol recently, so screens show the live
    /// quote first and let this fill in the sparkline.
    public func snapshots(_ symbols: [String]) async throws(ResearchError) -> [String: MarketSnapshot] {
        var result: [String: MarketSnapshot] = [:]
        for start in stride(from: 0, to: symbols.count, by: Self.snapshotBatch) {
            let batch = symbols[start..<min(start + Self.snapshotBatch, symbols.count)]
            let output = try await APIFailure.perform {
                try await client.getMarketOverviewApiMarketOverviewGet(query: .init(symbols: batch.joined(separator: ",")))
            }
            switch output {
            case .ok(let ok):
                guard case .json(let rows) = ok.body else { throw .server(status: 200) }
                for row in rows { result[row.symbol.uppercased()] = row }
            case .unprocessableContent:
                continue
            case .undocumented(let status, let payload):
                throw await APIFailure.from(status: status, payload: payload)
            }
        }
        return result
    }

    /// The first day to ask for: `years` before `now`, as the backend reads dates.
    static func historyStart(years: Int, now: Date) -> String {
        let calendar = PerformanceSeries.utc
        let start = calendar.date(byAdding: .year, value: -years, to: now) ?? now
        let parts = calendar.dateComponents([.year, .month, .day], from: start)
        return String(format: "%04d-%02d-%02d", parts.year ?? 0, parts.month ?? 1, parts.day ?? 1)
    }

    /// A `DailyClose` date as the backend reads dates.
    static func isoDay(_ day: Date) -> String {
        let parts = PerformanceSeries.utc.dateComponents([.year, .month, .day], from: day)
        return String(format: "%04d-%02d-%02d", parts.year ?? 0, parts.month ?? 1, parts.day ?? 1)
    }

    /// The daily closes for `symbol`, oldest first: over the last `years`
    /// years, or from `since` on when a history is only being brought up to date.
    public func dailyCloses(
        _ symbol: String, years: Int = PriceHistory.yearsKept, since: Date? = nil, now: Date = .now
    ) async throws(ResearchError) -> [DailyClose] {
        let start = since.map(Self.isoDay) ?? Self.historyStart(years: years, now: now)
        let output = try await APIFailure.perform {
            try await client.getDailyPricesApiDataDailySymbolGet(
                path: .init(symbol: symbol), query: .init(start: start)
            )
        }
        switch output {
        case .ok(let ok):
            guard case .json(let rows) = ok.body else { throw .server(status: 200) }
            let formatter = DateFormatter()
            formatter.calendar = Calendar(identifier: .gregorian)
            formatter.locale = Locale(identifier: "en_US_POSIX")
            formatter.timeZone = TimeZone(identifier: "UTC")
            formatter.dateFormat = "yyyy-MM-dd"
            return rows
                .compactMap { row in
                    formatter.date(from: String(row.tradingDate.prefix(10))).map { date in
                        // Splits and dividends are folded into the adjusted
                        // close; the same factor puts the high and low on
                        // that scale.
                        let factor = row.close > 0 ? row.adjustedClose / row.close : 1
                        return DailyClose(
                            date: date, close: row.adjustedClose, high: row.high * factor, low: row.low * factor
                        )
                    }
                }
                .sorted { $0.date < $1.date }
        case .unprocessableContent:
            throw .server(status: 422)
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }
}
