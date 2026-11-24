import LivermoreAPI
import LivermoreKit
import SwiftUI

/// What the company is worth under assumptions the user sets, and what a
/// lasting drop in demand would do to that.
struct ValuationView: View {
    let overview: CompanyOverview
    let price: Double?

    @State private var model: CashFlowModel?
    /// The company's own starting point, to reset to.
    @State private var starting: CashFlowModel?

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: Metrics.sectionSpacing) {
                if let model {
                    result(model)
                    assumptions
                    sensitivity(model)
                    downside(model)
                    footnotes(model)
                } else {
                    Card {
                        Notice(text: "There isn't enough reported data to value \(overview.symbol) on its cash flows: it needs free cash flow, a market value and a price.")
                    }
                }
            }
            .padding(Metrics.screenPadding)
        }
        .screenBackground()
        .navigationTitle("Cash-flow stress test")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .toolbar {
            if let starting, model != starting {
                ToolbarItem(placement: .primaryAction) { Button("Reset") { model = starting } }
            }
        }
        .onAppear {
            guard model == nil else { return }
            starting = CashFlowModel(overview: overview, price: price)
            model = starting
        }
    }

    // MARK: Result

    private func result(_ model: CashFlowModel) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("What these assumptions imply · \(overview.symbol)").eyebrowStyle()
            if let value = model.valuePerShare {
                Text(Fmt.price(value)).font(.hero).contentTransition(.numericText(value: value))
                    .animation(.default, value: value)
                if let price, price > 0 {
                    let gap = value / price - 1
                    HStack(spacing: 8) {
                        Tag("\(Fmt.percent(abs(gap))) \(gap >= 0 ? "above" : "below") the price", tint: gap.changeColor,
                            systemImage: gap >= 0 ? "arrow.up.right" : "arrow.down.right")
                        Text("Price \(Fmt.price(price))").font(.footnote.monospacedDigit()).foregroundStyle(.inkSecondary)
                    }
                }
                Text("Per share. A result of the assumptions below — not a forecast and not a price target.")
                    .font(.footnote).foregroundStyle(.inkSecondary).padding(.top, 2)
            } else if let problem = model.problem {
                Notice(text: problem, systemImage: "exclamationmark.triangle.fill", tint: .caution)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 4)
    }

    // MARK: Assumptions

    private var assumptions: some View {
        Card("Assumptions") {
            AssumptionRow(
                title: "Starting cash flow", detail: "Free cash flow, last fiscal year: \(Fmt.money(starting?.startingCashFlow))",
                value: Fmt.money(model?.startingCashFlow)
            ) {
                // In steps of 5% of the reported figure, so "normalised
                // higher" or "lower" is a deliberate, visible choice.
                let unit = (starting?.startingCashFlow ?? 0) * 0.05
                model?.startingCashFlow = max((model?.startingCashFlow ?? 0) + unit * $0, unit)
            }
            Divider()
            AssumptionRow(title: "5-year growth", detail: growthContext, value: Fmt.percent(model?.growth)) {
                model?.growth = min(max((model?.growth ?? 0) + 0.005 * $0, -0.10), 0.40)
            }
            Divider()
            AssumptionRow(title: "Required return", detail: "The yearly return you want for holding it", value: Fmt.percent(model?.discountRate)) {
                model?.discountRate = min(max((model?.discountRate ?? 0) + 0.005 * $0, 0.05), 0.20)
            }
            Divider()
            AssumptionRow(title: "Long-run growth", detail: "After year five, forever — keep it near the economy's", value: Fmt.percent(model?.terminalGrowth)) {
                model?.terminalGrowth = min(max((model?.terminalGrowth ?? 0) + 0.005 * $0, 0), 0.05)
            }
        }
    }

    private var growthContext: String {
        let check = overview.financialCheck
        if let cagr = check.revenue3yCagr { return "Revenue grew \(Fmt.percent(cagr)) a year over three years" }
        if let yoy = check.revenueYoy { return "Revenue grew \(Fmt.percent(yoy)) last year" }
        return "No revenue history to compare with"
    }

    // MARK: Sensitivity

    private func sensitivity(_ model: CashFlowModel) -> some View {
        let growthSteps = [model.growth - 0.04, model.growth, model.growth + 0.04]
        let rateSteps = [model.discountRate - 0.01, model.discountRate, model.discountRate + 0.01]
        let grid = model.sensitivity(growthSteps: growthSteps, discountSteps: rateSteps)

        return Card("How much the answer moves") {
            Grid(horizontalSpacing: 6, verticalSpacing: 6) {
                GridRow {
                    Text("Growth ↓  Return →").font(.caption2).foregroundStyle(.inkSecondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    ForEach(rateSteps, id: \.self) { rate in
                        Text(Fmt.percent(rate)).font(.caption.weight(.semibold).monospacedDigit())
                            .frame(maxWidth: .infinity)
                    }
                }
                ForEach(Array(growthSteps.enumerated()), id: \.offset) { row, growth in
                    GridRow {
                        Text(Fmt.percent(growth)).font(.caption.weight(.semibold).monospacedDigit())
                            .frame(maxWidth: .infinity, alignment: .leading)
                        ForEach(Array(rateSteps.enumerated()), id: \.offset) { column, _ in
                            let value = grid[row][column]
                            let isCentre = row == 1 && column == 1
                            Text(value.map { Fmt.axisPrice($0) } ?? "—")
                                .font(.subheadline.weight(isCentre ? .bold : .regular).monospacedDigit())
                                .frame(maxWidth: .infinity, minHeight: 40)
                                .foregroundStyle(tint(value))
                                .background(
                                    (isCentre ? Color.brand.opacity(0.12) : Color.well),
                                    in: RoundedRectangle(cornerRadius: 8, style: .continuous)
                                )
                        }
                    }
                }
            }
            Text("Green is above today's price, red below. The spread between the corners is the honest width of the answer.")
                .font(.caption).foregroundStyle(.inkSecondary)
        }
    }

    private func tint(_ value: Double?) -> Color {
        guard let value, let price, price > 0 else { return .primary }
        return (value - price).changeColor
    }

    // MARK: Downside

    @ViewBuilder
    private func downside(_ model: CashFlowModel) -> some View {
        if let ten = RevenueShock(overview: overview, shortfall: 0.10),
           let twenty = RevenueShock(overview: overview, shortfall: 0.20) {
            let segment = overview.revenueMix?.slices.first
            Card("If demand falls and stays down") {
                Text(segment.map { "\($0.name) is \(Fmt.percent($0.share)) of revenue. Suppose its sales fall and do not come back:" }
                    ?? "Suppose revenue falls and does not come back:")
                    .font(.subheadline)
                ShockRow(title: "10% lower", shock: ten, model: model, price: price)
                ShockRow(title: "20% lower", shock: twenty, model: model, price: price)
                Text("Assumes \(Fmt.percent(ten.contribution)) of each lost dollar of sales was cash profit (costs like research don't shrink with sales) and a \(Fmt.percent(ten.taxRate)) tax rate. One unpaid invoice is a one-off; this is the case where the orders stop.")
                    .font(.caption).foregroundStyle(.inkSecondary)
            }
        }
    }

    // MARK: Footnotes

    private func footnotes(_ model: CashFlowModel) -> some View {
        Card("Read this before trusting it") {
            if let share = model.terminalShare {
                DetailRow("Value from after year five", Fmt.percent(share), tint: share > 0.8 ? .caution : nil)
            }
            DetailRow(model.netCash >= 0 ? "Net cash added" : "Net debt subtracted", Fmt.money(abs(model.netCash)))
            DetailRow("Shares", String(format: "%.2fB", model.shares / 1e9))
            if let asOf = overview.asOfDate {
                DetailRow("Financials as of", asOf)
            }
            Text("Five years of free cash flow at one growth rate, then a terminal value, discounted to today. Share count is market value divided by price. A model like this organises a judgement; it does not replace one. Research tool, not advice.")
                .font(.caption).foregroundStyle(.inkSecondary)
        }
    }
}

/// One assumption: what it is, what the company's history says, and a
/// stepper to change it.
private struct AssumptionRow: View {
    let title: String
    let detail: String
    let value: String
    /// Called with +1 or −1.
    let step: (Double) -> Void

    var body: some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.subheadline.weight(.semibold))
                Text(detail).font(.caption).foregroundStyle(.inkSecondary)
            }
            Spacer(minLength: 8)
            Text(value).font(.body.weight(.semibold).monospacedDigit())
            Stepper(title) { step(1) } onDecrement: { step(-1) }
                .labelsHidden()
        }
        .sensoryFeedback(.selection, trigger: value)
    }
}

private struct ShockRow: View {
    let title: String
    let shock: RevenueShock
    let model: CashFlowModel
    let price: Double?

    var body: some View {
        let value = shock.applied(to: model).valuePerShare
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.subheadline.weight(.semibold))
                Text("\(Fmt.money(shock.cashFlowLost)) less cash a year").font(.caption).foregroundStyle(.inkSecondary)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                Text(value.map { Fmt.price($0) } ?? "—").font(.body.weight(.semibold).monospacedDigit())
                if let value, let price, price > 0 {
                    Text("\(Fmt.percent(value / price - 1, signed: true)) vs price")
                        .font(.caption.monospacedDigit()).foregroundStyle((value - price).changeColor)
                }
            }
        }
        .padding(12)
        .background(Color.well, in: RoundedRectangle(cornerRadius: Metrics.tileRadius, style: .continuous))
        .accessibilityElement(children: .combine)
    }
}
