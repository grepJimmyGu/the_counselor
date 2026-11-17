import Testing

@testable import LivermoreKit

/// The inputs "Nvidia After the Selloff" (JG, 2026-11-12) publishes in its
/// methodology note: $160B starting free cash flow, 12% growth for five
/// years, 9.5% discount rate, 3.5% terminal growth, ~$23.2B net cash,
/// 24.3B shares.
private let post = CashFlowModel(
    startingCashFlow: 160e9, growth: 0.12, discountRate: 0.095,
    terminalGrowth: 0.035, netCash: 23.2e9, shares: 24.3e9
)

private func shock(_ shortfall: Double) -> RevenueShock {
    // "$400B illustrative annual revenue run rate … 92.5% Data Center share …
    // 70% assumed cash operating contribution and a 17% illustrative tax rate"
    RevenueShock(revenue: 400e9, segmentShare: 0.925, shortfall: shortfall, contribution: 0.70, taxRate: 0.17)
}

@Suite("cash-flow valuation reproduces the published analysis")
struct CashFlowModelTests {
    @Test("the central case is about $163 a share")
    func central() throws {
        let value = try #require(post.valuePerShare)
        #expect(abs(value - 163) < 1, "got \(value)")
    }

    @Test("a lasting 10% and 20% Data Center shortfall give about $142 and $120")
    func downside() throws {
        let ten = try #require(shock(0.10).applied(to: post).valuePerShare)
        let twenty = try #require(shock(0.20).applied(to: post).valuePerShare)
        #expect(abs(ten - 142) < 1, "got \(ten)")
        #expect(abs(twenty - 120) < 1, "got \(twenty)")
        // $400B × 92.5% × 10% × 70% × (1 − 17%)
        #expect(abs(shock(0.10).cashFlowLost - 21.497e9) < 0.01e9)
    }

    @Test("the sensitivity range brackets the post's $113–$245")
    func sensitivity() {
        let grid = post.sensitivity(growthSteps: [0.08, 0.12, 0.16], discountSteps: [0.085, 0.095, 0.105])
        let values = grid.flatMap { $0 }.compactMap { $0 }
        #expect(values.count == 9)
        // Higher growth and a lower required return both raise the value.
        #expect(grid[2][0]! > grid[1][1]!)
        #expect(grid[0][2]! < grid[1][1]!)
        #expect(abs(grid[1][1]! - 163) < 1)
        #expect(values.min()! < 130 && values.max()! > 220)
    }

    @Test("most of the value sits beyond the five forecast years, and the model says so")
    func terminalShare() throws {
        let share = try #require(post.terminalShare)
        #expect(share > 0.7 && share < 0.85)
    }

    @Test("a model that can't be valued says why instead of returning a number")
    func problems() {
        var burning = post
        burning.startingCashFlow = -5e9
        #expect(burning.valuePerShare == nil)
        #expect(burning.problem?.contains("free cash flow") == true)

        var impossible = post
        impossible.terminalGrowth = 0.10
        #expect(impossible.valuePerShare == nil)
        #expect(impossible.problem?.contains("higher than") == true)

        var unknown = post
        unknown.shares = 0
        #expect(unknown.problem != nil)
    }

    @Test("a shock larger than the cash flow leaves none, not a negative amount")
    func floor() {
        let total = RevenueShock(revenue: 400e9, segmentShare: 1, shortfall: 1, contribution: 0.9, taxRate: 0)
        #expect(total.applied(to: post).startingCashFlow == 0)
    }
}

@Suite("where each $100 of sales goes")
struct SalesDollarTests {
    @Test("Nvidia's latest quarter: about $25 product, $9 running the business, $66 profit")
    func nvidia() throws {
        // The post: "$25 paid direct product costs, $7 paid R&D, $1 paid sales
        // and administration, and $66 remained as operating profit".
        let dollar = try #require(SalesDollar(grossMargin: 0.75, operatingMargin: 0.662))
        #expect(abs(dollar.costOfSales - 25) < 0.01)
        #expect(abs(dollar.operatingCosts - 8.8) < 0.01)
        #expect(abs(dollar.operatingProfit - 66.2) < 0.01)
        #expect(abs(dollar.costOfSales + dollar.operatingCosts + dollar.operatingProfit - 100) < 1e-9)
    }

    @Test("a loss-making company still adds up; contradictory margins are refused")
    func edges() throws {
        let losing = try #require(SalesDollar(grossMargin: 0.40, operatingMargin: -0.10))
        #expect(abs(losing.operatingCosts - 50) < 1e-9)
        #expect(SalesDollar(grossMargin: 0.30, operatingMargin: 0.50) == nil)
        #expect(SalesDollar(grossMargin: nil, operatingMargin: 0.2) == nil)
    }
}
