import Foundation
import LivermoreAPI

public typealias StrategyJSON = Components.Schemas.StrategyJSON
public typealias BacktestResult = Components.Schemas.BacktestResult
public typealias BacktestMetrics = Components.Schemas.BacktestMetrics

/// One of the website's strategy templates: the explanation a user reads, and
/// the strategy it runs.
///
/// The catalogue is data in `apps/web/src/lib/contracts.ts`, not something the
/// backend serves, so the app carries an export of it (`templates.json`, made
/// by `scripts/gen_templates.mjs`).
public struct StrategyTemplate: Codable, Identifiable, Equatable, Sendable {
    public struct PerformanceContext: Codable, Equatable, Sendable {
        public var returnRange: String?
        public var sharpeRange: String?
        public var worstStretch: String?
    }

    public struct AcademicReference: Codable, Equatable, Sendable {
        public var citation: String?
        public var note: String?
    }

    public var id: String
    public var name: String
    public var category: String
    public var description: String
    public var whatItCaptures: String?
    public var whatItTests: String
    public var dataRequirement: String
    public var universeDescription: String
    public var defaultTickers: [String]
    public var multiTicker: Bool
    public var tickerLabel: String
    public var minTickers: Int?
    public var availability: String
    public var etfProxyCaveat: String?
    public var evidenceTier: String?
    public var horizonBadge: String?
    public var caveats: [String]?
    public var whenInCopy: String?
    public var whenOutCopy: String?
    public var perfContext: PerformanceContext?
    public var academicRef: AcademicReference?
    public var comingSoon: Bool?
    public var strategy: StrategyJSON

    /// Runnable today. "proxy" templates run on an ETF stand-in and say so.
    public var isRunnable: Bool {
        (availability == "ready" || availability == "proxy") && comingSoon != true
    }

    /// Fewest tickers this template needs to produce a meaningful result.
    public var minimumTickers: Int {
        minTickers ?? 1
    }
}

public enum TemplateCatalog {
    private struct File: Decodable {
        let templates: [StrategyTemplate]
    }

    /// Every template the website defines, in its order.
    public static let all: [StrategyTemplate] = {
        guard let url = Bundle.module.url(forResource: "templates", withExtension: "json"),
              let data = try? Data(contentsOf: url),
              let file = try? JSONDecoder().decode(File.self, from: data)
        else { return [] }
        return file.templates
    }()

    /// The templates a user can run now.
    public static var runnable: [StrategyTemplate] { all.filter(\.isRunnable) }
}

public enum BacktestRange: String, CaseIterable, Identifiable, Sendable {
    case threeYears = "3Y"
    case fiveYears = "5Y"
    case tenYears = "10Y"

    public var id: String { rawValue }

    var years: Int {
        switch self {
        case .threeYears: 3
        case .fiveYears: 5
        case .tenYears: 10
        }
    }
}

public enum StrategyBuilder {
    private static var utc: Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        return calendar
    }

    private static func isoDay(_ date: Date) -> String {
        let parts = utc.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", parts.year ?? 0, parts.month ?? 0, parts.day ?? 0)
    }

    /// Splits what a user typed — "aapl, msft nvda" — into tickers.
    public static func tickers(from text: String) -> [String] {
        var seen = Set<String>()
        return text
            .split(whereSeparator: { $0 == "," || $0.isWhitespace })
            .map { $0.uppercased() }
            .filter { !$0.isEmpty && seen.insert($0).inserted }
    }

    /// "Trend Following — AAPL", "Low Volatility — AAPL, MSFT +13" — the web's
    /// `autoName`.
    public static func name(for template: StrategyTemplate, tickers: [String]) -> String {
        let suffix: String
        if tickers.isEmpty {
            suffix = template.defaultTickers.prefix(2).joined(separator: ", ")
        } else if tickers.count <= 3 {
            suffix = tickers.joined(separator: ", ")
        } else {
            suffix = tickers.prefix(2).joined(separator: ", ") + " +\(tickers.count - 2)"
        }
        return "\(template.name) — \(suffix)"
    }

    /// A strategy re-dated to end today and start `range` years back — for
    /// testing a saved strategy again on current data.
    public static func redated(_ strategy: StrategyJSON, range: BacktestRange, today: Date = .now) -> StrategyJSON {
        var next = strategy
        next.endDate = isoDay(today)
        next.startDate = isoDay(utc.date(byAdding: .year, value: -range.years, to: today) ?? today)
        return next
    }

    /// The strategy a template runs for the chosen tickers and period — the
    /// web's `buildStrategyFromTemplate`: the template's own rules, with the
    /// universe, the dates and the name replaced.
    public static func strategy(
        from template: StrategyTemplate,
        tickers: [String],
        range: BacktestRange,
        today: Date = .now
    ) -> StrategyJSON {
        var strategy = template.strategy
        strategy.universe = tickers.isEmpty ? template.defaultTickers : tickers
        strategy.strategyName = name(for: template, tickers: tickers)
        strategy.endDate = isoDay(today)
        strategy.startDate = isoDay(utc.date(byAdding: .year, value: -range.years, to: today) ?? today)
        return strategy
    }
}
