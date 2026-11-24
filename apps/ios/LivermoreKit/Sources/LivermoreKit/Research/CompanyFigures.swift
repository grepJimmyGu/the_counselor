import Foundation
import LivermoreAPI

/// One fiscal year's figure, for the financial charts.
public struct YearFigure: Identifiable, Equatable, Sendable {
    public let year: String
    public let value: Double

    public var id: String { year }
}

/// One slice of the revenue mix.
public struct RevenueSlice: Identifiable, Equatable, Sendable {
    public let name: String
    public let amount: Double
    /// Share of the year's total, 0–1.
    public let share: Double

    public var id: String { name }
}

/// The backend sends its yearly series as free-form objects
/// (`{"date": "2026-01-25", "revenue": …}`); this reads one number out of
/// each, oldest first.
private func yearly<Row: Encodable>(_ rows: [Row]?, key: String) -> [YearFigure] {
    guard let rows,
          let data = try? JSONEncoder().encode(rows),
          let objects = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]
    else { return [] }
    let figures: [YearFigure] = objects.compactMap { object in
        guard let date = object["date"] as? String, date.count >= 4,
              let value = (object[key] as? NSNumber)?.doubleValue
        else { return nil }
        return YearFigure(year: String(date.prefix(4)), value: value)
    }
    return figures.sorted { $0.year < $1.year }
}

extension Components.Schemas.FinancialCheckSection {
    public var revenueByYear: [YearFigure] { yearly(revenueSeries, key: "revenue") }
    public var freeCashFlowByYear: [YearFigure] { yearly(fcfSeries, key: "fcf") }
    public var operatingMarginByYear: [YearFigure] { yearly(revenueSeries, key: "operating_margin") }
}

extension Components.Schemas.CompanyOverviewResponse {
    /// What the company sold in its most recent reported year, largest first.
    public var revenueMix: (year: Int, slices: [RevenueSlice])? {
        guard let latest = revenueSegments?.productYears?.max(by: { $0.year < $1.year }) else { return nil }
        let amounts = (latest.segments?.additionalProperties ?? [:]).filter { $0.value > 0 }
        let total = amounts.values.reduce(0, +)
        guard total > 0 else { return nil }
        let slices = amounts
            .map { RevenueSlice(name: $0.key, amount: $0.value, share: $0.value / total) }
            .sorted { $0.amount > $1.amount }
        return (latest.year, slices)
    }
}
