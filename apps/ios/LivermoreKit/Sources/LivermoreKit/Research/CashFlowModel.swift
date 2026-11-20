import Foundation
import LivermoreAPI

/// A discounted-cash-flow valuation with its assumptions in the open.
///
/// Five years of free cash flow growing at one rate, then a terminal value;
/// discounted, plus net cash, divided by the share count. It is the model in
/// "Nvidia After the Selloff" (JG, 2026-11-12), and `CashFlowModelTests`
/// reproduces that post's published results from its published inputs.
///
/// Every input is an assumption a person chose. The output is what those
/// assumptions imply — not a forecast, and not a price target.
public struct CashFlowModel: Equatable, Sendable {
    /// Free cash flow in the starting year, in dollars.
    public var startingCashFlow: Double
    /// Growth per year over the forecast, as a fraction (0.12 = 12%).
    public var growth: Double
    /// Return an investor requires, as a fraction.
    public var discountRate: Double
    /// Growth assumed forever after the forecast, as a fraction.
    public var terminalGrowth: Double
    /// Cash minus debt, in dollars. Negative for net debt.
    public var netCash: Double
    public var shares: Double

    public static let forecastYears = 5

    public init(
        startingCashFlow: Double, growth: Double, discountRate: Double,
        terminalGrowth: Double, netCash: Double, shares: Double
    ) {
        self.startingCashFlow = startingCashFlow
        self.growth = growth
        self.discountRate = discountRate
        self.terminalGrowth = terminalGrowth
        self.netCash = netCash
        self.shares = shares
    }

    /// Why the model can't produce a value, or nil when it can.
    public var problem: String? {
        if shares <= 0 { return "The share count isn't known for this company." }
        if startingCashFlow <= 0 {
            return "This company isn't generating free cash flow, so a cash-flow valuation has nothing to discount."
        }
        if discountRate <= terminalGrowth {
            return "The required return has to be higher than the long-run growth rate — otherwise the value is infinite."
        }
        return nil
    }

    /// Present value of the forecast years and of everything after them.
    public var enterpriseValue: Double? {
        guard problem == nil else { return nil }
        var value = 0.0
        var cashFlow = startingCashFlow
        for year in 1...Self.forecastYears {
            cashFlow *= 1 + growth
            value += cashFlow / pow(1 + discountRate, Double(year))
        }
        let terminal = cashFlow * (1 + terminalGrowth) / (discountRate - terminalGrowth)
        return value + terminal / pow(1 + discountRate, Double(Self.forecastYears))
    }

    public var valuePerShare: Double? {
        enterpriseValue.map { ($0 + netCash) / shares }
    }

    /// How much of the value rests on the years after the forecast. A high
    /// figure means the answer is mostly the terminal assumption.
    public var terminalShare: Double? {
        guard let total = enterpriseValue, total > 0 else { return nil }
        var cashFlow = startingCashFlow
        for _ in 1...Self.forecastYears { cashFlow *= 1 + growth }
        let terminal = cashFlow * (1 + terminalGrowth) / (discountRate - terminalGrowth)
        return terminal / pow(1 + discountRate, Double(Self.forecastYears)) / total
    }

    /// The same model with different growth and required return.
    public func with(growth: Double? = nil, discountRate: Double? = nil) -> CashFlowModel {
        var copy = self
        if let growth { copy.growth = growth }
        if let discountRate { copy.discountRate = discountRate }
        return copy
    }

    /// Value per share across a grid of growth (rows) and required return
    /// (columns), so the range of answers is on screen beside the one in the
    /// middle.
    public func sensitivity(growthSteps: [Double], discountSteps: [Double]) -> [[Double?]] {
        growthSteps.map { growth in
            discountSteps.map { rate in with(growth: growth, discountRate: rate).valuePerShare }
        }
    }
}

/// A lasting loss of revenue in one part of the business, and what it does
/// to the cash the model starts from.
///
/// This is a demand shock, not a bad debt: a customer that stops paying one
/// invoice is a balance-sheet event; a customer that stops ordering is a
/// lower cash flow in every year that follows.
public struct RevenueShock: Equatable, Sendable {
    /// Annual revenue the shock is measured against, in dollars.
    public var revenue: Double
    /// The affected segment's share of that revenue (0–1).
    public var segmentShare: Double
    /// How much of the segment's revenue is lost (0.10 = 10%).
    public var shortfall: Double
    /// Cash profit lost per dollar of revenue lost. Higher than the operating
    /// margin, because research and overhead do not shrink with sales.
    public var contribution: Double
    public var taxRate: Double

    public init(revenue: Double, segmentShare: Double, shortfall: Double, contribution: Double, taxRate: Double) {
        self.revenue = revenue
        self.segmentShare = segmentShare
        self.shortfall = shortfall
        self.contribution = contribution
        self.taxRate = taxRate
    }

    /// Free cash flow lost each year.
    public var cashFlowLost: Double {
        revenue * segmentShare * shortfall * contribution * (1 - taxRate)
    }

    /// The model with that cash gone for good.
    public func applied(to model: CashFlowModel) -> CashFlowModel {
        var shocked = model
        shocked.startingCashFlow = max(model.startingCashFlow - cashFlowLost, 0)
        return shocked
    }
}

/// Where each $100 of sales goes: the product, running the business, and
/// what is left as operating profit.
public struct SalesDollar: Equatable, Sendable {
    public let costOfSales: Double
    public let operatingCosts: Double
    public let operatingProfit: Double

    /// From the two margins every income statement gives. Nil when either is
    /// missing or they contradict each other.
    public init?(grossMargin: Double?, operatingMargin: Double?) {
        guard let grossMargin, let operatingMargin,
              (0...1).contains(grossMargin), operatingMargin <= grossMargin, operatingMargin >= -1
        else { return nil }
        costOfSales = (1 - grossMargin) * 100
        operatingCosts = (grossMargin - operatingMargin) * 100
        operatingProfit = operatingMargin * 100
    }
}

extension CashFlowModel {
    /// Starting assumptions for a company, from what the overview reports.
    ///
    /// The cash flow, net cash and share count are the company's own. Growth
    /// starts from its three-year revenue growth, held between 0% and 15% —
    /// few businesses compound faster than that for five more years, and a
    /// default that assumes they will is a default that flatters. The
    /// required return and long-run growth are conventional starting points.
    /// All of them are meant to be changed.
    public init?(overview: Components.Schemas.CompanyOverviewResponse, price: Double?) {
        let check = overview.financialCheck
        guard let cashFlow = check.freeCashFlow,
              let marketCap = overview.marketCap, marketCap > 0,
              let price = price ?? overview.price, price > 0
        else { return nil }
        let history = check.revenue3yCagr ?? check.revenueYoy ?? 0.05
        self.init(
            startingCashFlow: cashFlow,
            growth: (min(max(history, 0), 0.15) * 200).rounded() / 200,
            discountRate: 0.095,
            terminalGrowth: 0.03,
            netCash: -(check.netDebt ?? 0),
            shares: marketCap / price
        )
    }
}

extension RevenueShock {
    /// A shock to the company's largest line of business, sized from its
    /// latest reported year.
    public init?(overview: Components.Schemas.CompanyOverviewResponse, shortfall: Double) {
        let check = overview.financialCheck
        guard let revenue = check.revenueByYear.last?.value, revenue > 0 else { return nil }
        // Lost sales take their gross profit with them; operating costs stay.
        // Halfway between the two margins is the usual working assumption.
        let gross = check.grossMargin ?? 0.5
        let operating = check.operatingMargin ?? gross / 2
        self.init(
            revenue: revenue,
            segmentShare: overview.revenueMix?.slices.first?.share ?? 1,
            shortfall: shortfall,
            contribution: min(max((gross + operating) / 2, 0.05), 0.95),
            taxRate: 0.21
        )
    }
}
