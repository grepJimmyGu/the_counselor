import Foundation
import LivermoreAPI
import OpenAPIRuntime

public typealias FilingAnalysis = Components.Schemas.FilingAnalysisResponse
public typealias FilingQuarter = Components.Schemas.FilingQuarter
public typealias FilingMetric = Components.Schemas.FilingMetric
public typealias FilingFinding = Components.Schemas.FilingFinding

extension ResearchService {
    /// What the latest 10-Q or 10-K shows, against the quarters before it.
    ///
    /// `.unavailable` carries the backend's reason when there is one worth
    /// showing: a foreign filer, a ticker the SEC does not list.
    public func filings(_ symbol: String) async throws(ResearchError) -> FilingAnalysis {
        let output = try await APIFailure.perform {
            try await client.getCompanyFilingsApiCompanySymbolFilingsGet(path: .init(symbol: symbol))
        }
        switch output {
        case .ok(let ok):
            guard case .json(let analysis) = ok.body else { throw .server(status: 200) }
            return analysis
        case .unprocessableContent:
            throw .server(status: 422)
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }
}

extension Components.Schemas.FilingQuarter {
    /// A figure for this quarter by its key, or nil when the company does
    /// not report it.
    public func value(_ key: String) -> Double? {
        values?.additionalProperties[key]
    }

    /// "Q2 '27" — short enough for a chart axis.
    public var shortLabel: String {
        guard let fiscalPeriod, let fiscalYear else { return label }
        return "\(fiscalPeriod) '\(String(format: "%02d", fiscalYear % 100))"
    }
}

extension Components.Schemas.FilingAnalysisResponse {
    /// A metric's value in each quarter, oldest first; nil where unreported.
    public func series(_ key: String) -> [Double?] {
        quarters.map { $0.value(key) }
    }

    public func metric(_ key: String) -> FilingMetric? {
        metrics.first { $0.key == key }
    }

    /// Metric groups in the order the backend lists them.
    public var metricGroups: [(name: String, metrics: [FilingMetric])] {
        var order: [String] = []
        for metric in metrics where !order.contains(metric.group) { order.append(metric.group) }
        return order.map { name in (name, metrics.filter { $0.group == name }) }
    }
}

extension Components.Schemas.FilingMetric {
    /// A value of this metric, in its own unit: "$96.2B", "75.0%", "60 days".
    public func formatted(_ value: Double?) -> String {
        guard let value else { return "—" }
        switch unit {
        case "usd": return Self.money(value)
        case "per_share": return String(format: "$%.2f", value)
        case "shares": return Self.count(value)
        case "percent": return String(format: "%.1f%%", value * 100)
        case "ratio": return String(format: "%.2f×", value)
        case "days": return "\(Int(value.rounded())) days"
        default: return String(format: "%.2f", value)
        }
    }

    /// A change in this metric: "+17.9%" for money, "+2.6 pts" for a
    /// margin, "+14 days", "+$3.2B" for a figure that can cross zero.
    public func formattedChange(_ change: Double?) -> String? {
        guard let change else { return nil }
        switch changeKind {
        case "relative": return String(format: "%+.1f%%", change * 100)
        case "points": return String(format: "%+.1f pts", change * 100)
        default:
            switch unit {
            case "days": return String(format: "%+.0f days", change)
            case "usd": return (change >= 0 ? "+" : "−") + Self.money(abs(change))
            default: return String(format: "%+.2f", change)
            }
        }
    }

    /// Whether a change is in the direction that is good for this metric.
    /// nil when the metric has no good direction (capital spending), or the
    /// change is nil or negligible.
    public func isImprovement(_ change: Double?) -> Bool? {
        guard let change, better != "none" else { return nil }
        let negligible = changeKind == "relative" || changeKind == "points" ? 0.0005 : 0.5
        if abs(change) < negligible { return nil }
        return better == "up" ? change > 0 : change < 0
    }

    static func money(_ value: Double) -> String {
        let sign = value < 0 ? "−" : ""
        let amount = abs(value)
        if amount >= 1e12 { return String(format: "%@$%.2fT", sign, amount / 1e12) }
        if amount >= 1e9 { return String(format: "%@$%.1fB", sign, amount / 1e9) }
        if amount >= 1e6 { return String(format: "%@$%.0fM", sign, amount / 1e6) }
        return String(format: "%@$%.0f", sign, amount)
    }

    static func count(_ value: Double) -> String {
        if value >= 1e9 { return String(format: "%.2fB", value / 1e9) }
        if value >= 1e6 { return String(format: "%.0fM", value / 1e6) }
        return String(format: "%.0f", value)
    }
}

extension FilingMetric {
    /// The note in the few words a list row has room for: "Highest of the
    /// last 9 quarters." reads as "9-quarter high". Anything else is passed
    /// through unchanged.
    public var shortNote: String? {
        guard let note else { return nil }
        for (prefix, word) in [("Highest of the last ", "high"), ("Lowest of the last ", "low")] where note.hasPrefix(prefix) {
            let count = note.dropFirst(prefix.count).prefix { $0.isNumber }
            if !count.isEmpty { return "\(count)-quarter \(word)" }
        }
        return note
    }
}
