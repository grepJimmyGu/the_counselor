import Foundation
import LivermoreAPI
import OpenAPIRuntime

/// A price, the day's move and a month of closes for one symbol.
public typealias MarketSnapshot = Components.Schemas.MarketSnapshotItem

/// One day's closing price, adjusted for splits and dividends.
public struct DailyClose: Equatable, Sendable {
    public let date: Date
    public let close: Double

    public init(date: Date, close: Double) {
        self.date = date
        self.close = close
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
/// the stock's latest close.
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

    /// Charts read no more detail than this on a phone.
    static let maxPoints = 260

    public init(
        stock: [DailyClose], benchmark: [DailyClose], range: PerformanceRange,
        calendar: Calendar = PerformanceSeries.utc
    ) {
        self.range = range
        guard let end = stock.last?.date else {
            points = []
            return
        }
        let start = range.start(endingOn: end, calendar: calendar)
        var window = stock.filter { $0.date >= start && $0.close > 0 }
        // Year to date starts from last year's final close, not the first
        // one found after 25 December.
        if range == .yearToDate {
            let year = calendar.component(.year, from: end)
            let previous = window.last { calendar.component(.year, from: $0.date) < year }
            window = (previous.map { [$0] } ?? []) + window.filter { calendar.component(.year, from: $0.date) == year }
        }
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
/// runs. A history is ~200 KB, so the handful a session looks at is cheap to
/// hold and expensive to refetch on every range change.
@MainActor
public final class PriceHistory {
    public static let benchmarkSymbol = "SPY"
    static let capacity = 8

    private let fetch: @Sendable (String) async throws -> [DailyClose]
    private var cache: [String: [DailyClose]] = [:]
    private var order: [String] = []

    public init(fetch: @escaping @Sendable (String) async throws -> [DailyClose]) {
        self.fetch = fetch
    }

    public func closes(for symbol: String) async throws -> [DailyClose] {
        let symbol = symbol.uppercased()
        if let cached = cache[symbol] {
            order.removeAll { $0 == symbol }
            order.append(symbol)
            return cached
        }
        let loaded = try await fetch(symbol)
        cache[symbol] = loaded
        order.append(symbol)
        // The benchmark is on every chart; never evict it.
        while order.count > Self.capacity, let oldest = order.first(where: { $0 != Self.benchmarkSymbol }) {
            order.removeAll { $0 == oldest }
            cache[oldest] = nil
        }
        return loaded
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

    /// Every daily close the backend has for `symbol`, oldest first.
    public func dailyCloses(_ symbol: String) async throws(ResearchError) -> [DailyClose] {
        let output = try await APIFailure.perform {
            try await client.getDailyPricesApiDataDailySymbolGet(path: .init(symbol: symbol))
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
                    formatter.date(from: String(row.tradingDate.prefix(10))).map { DailyClose(date: $0, close: row.adjustedClose) }
                }
                .sorted { $0.date < $1.date }
        case .unprocessableContent:
            throw .server(status: 422)
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }
}
