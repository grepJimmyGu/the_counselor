import Foundation
import LivermoreAPI

extension StockMetrics {
    /// Builds the scoring inputs from the API responses — the same mapping as
    /// `bridgeFromOverview` + `mergeTrend` in the web's
    /// `evaluation-dashboard.tsx`. The trend arrives separately and later; until
    /// it does, the trend score is the neutral 50.
    public init(overview: CompanyOverview, trend: CompanyTrend?) {
        self.init()
        let fc = overview.financialCheck
        price = trend?.latestPrice ?? overview.price
        revenueYoy = fc.revenueYoy
        grossMargin = fc.grossMargin
        operatingMargin = fc.operatingMargin
        roe = fc.roe
        fcfMargin = fc.fcfMargin
        fcfConversion = fc.fcfConversion
        netDebt = fc.netDebt
        debtToEquity = fc.debtToEquity
        currentRatio = fc.currentRatio
        peRatio = fc.peRatio
        pegRatio = fc.pegRatio
        evEbitda = fc.evEbitda
        fcfYield = fc.fcfYield
        perf3m = trend?.perf3m
        perf12m = trend?.perf12m
        ma50 = trend?.ma50
        ma200 = trend?.ma200
        // Three-month excess return over SPY stands in for sector strength,
        // as it does on the web.
        rsVsSector = trend?.rsVsSpy3m
    }
}

public struct PricePoint: Equatable, Sendable, Identifiable {
    public let date: Date
    public let price: Double
    public var id: Date { date }
}

extension Components.Schemas.TrendSection {
    /// The 90-day closing prices. The schema types each point as a free-form
    /// object, so it is read by key here.
    public var pricePoints: [PricePoint] {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd"
        return (priceSeries90d ?? []).compactMap { point in
            let fields = point.additionalProperties.value
            guard let text = fields["date"] as? String, let date = formatter.date(from: text) else { return nil }
            let price: Double? = (fields["price"] as? Double) ?? (fields["price"] as? Int).map(Double.init)
            guard let price else { return nil }
            return PricePoint(date: date, price: price)
        }
    }
}
