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

    /// The headline range out of a longer line: "+3% to +12% annual (varies
    /// widely…)" → "+3% to +12%". Nil when the line has no percentages.
    public static func headlineRange(_ text: String?) -> String? {
        guard let text else { return nil }
        let pattern = #"[+−\-–]?\d+(?:\.\d+)?%(?:\s*to\s*[+−\-–]?\d+(?:\.\d+)?%)?"#
        guard let range = text.range(of: pattern, options: .regularExpression) else { return nil }
        return String(text[range])
    }

    /// The first sentence of the description — enough for a card.
    public var summary: String {
        let text = whatItCaptures ?? description
        guard let end = text.range(of: ". ") else { return text }
        return String(text[..<end.lowerBound]) + "."
    }

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

    /// A strategy re-dated to the chosen period — for testing a saved
    /// strategy again, on current data or over a stretch of the past.
    public static func redated(_ strategy: StrategyJSON, range: BacktestPeriod, today: Date = .now) -> StrategyJSON {
        var next = strategy
        next.endDate = isoDay(range.end(today: today))
        next.startDate = isoDay(range.start(today: today))
        return next
    }

    /// The strategy a template runs for the chosen tickers and period — the
    /// web's `buildStrategyFromTemplate`: the template's own rules, with the
    /// universe, the dates and the name replaced.
    public static func strategy(
        from template: StrategyTemplate,
        tickers: [String],
        range: BacktestPeriod,
        today: Date = .now
    ) -> StrategyJSON {
        var strategy = template.strategy
        strategy.universe = tickers.isEmpty ? template.defaultTickers : tickers
        strategy.strategyName = name(for: template, tickers: tickers)
        strategy.endDate = isoDay(range.end(today: today))
        strategy.startDate = isoDay(range.start(today: today))
        return strategy
    }
}
