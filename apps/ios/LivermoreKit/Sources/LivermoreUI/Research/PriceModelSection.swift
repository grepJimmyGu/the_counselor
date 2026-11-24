import Charts
import LivermoreKit
import SwiftUI

// MARK: - Trend model

/// A line fitted through the recent price: how fast it has moved, how
/// steadily, and where today's price sits against it.
struct TrendModelCard: View {
    let closes: [DailyClose]

    private enum Window: Int, CaseIterable, Identifiable {
        case quarter = 63, half = 126, year = 252
        var id: Int { rawValue }
        var title: String {
            switch self {
            case .quarter: "3 months"
            case .half: "6 months"
            case .year: "1 year"
            }
        }
    }

    @State private var window: Window = .half

    var body: some View {
        let model = TrendModel(closes: closes, window: window.rawValue)
        Card("Trend model") {
            Picker("Window", selection: $window) {
                ForEach(Window.allCases) { Text($0.title).tag($0) }
            }
            .pickerStyle(.segmented)

            if let model {
                let prices = Array(closes.suffix(model.window))
                let lows = model.points.map(\.lower) + prices.map(\.close)
                let highs = model.points.map(\.upper) + prices.map(\.close)
                let tint = model.annualRate.changeColor
                Chart {
                    ForEach(model.points) { point in
                        AreaMark(x: .value("Date", point.date), yStart: .value("Low", point.lower), yEnd: .value("High", point.upper))
                            .foregroundStyle(tint.opacity(0.10))
                        LineMark(x: .value("Date", point.date), y: .value("Line", point.middle), series: .value("Series", "line"))
                            .foregroundStyle(tint)
                            .lineStyle(StrokeStyle(lineWidth: 1.5, dash: [5, 4]))
                    }
                    ForEach(prices, id: \.date) { bar in
                        LineMark(x: .value("Date", bar.date), y: .value("Price", bar.close), series: .value("Series", "price"))
                            .foregroundStyle(Color.primary)
                            .lineStyle(StrokeStyle(lineWidth: 1.8, lineCap: .round, lineJoin: .round))
                    }
                }
                .chartYScale(domain: ((lows.min() ?? 0) * 0.98)...((highs.max() ?? 1) * 1.02))
                .chartYAxis {
                    AxisMarks(position: .trailing, values: .automatic(desiredCount: 3)) { value in
                        AxisGridLine().foregroundStyle(Color.hairline.opacity(0.5))
                        AxisValueLabel { if let amount = value.as(Double.self) { Text(Fmt.axisPrice(amount)) } }
                    }
                }
                .chartXAxis { AxisMarks(values: .automatic(desiredCount: 4)) { _ in AxisValueLabel(format: .dateTime.month(.abbreviated)) } }
                .frame(height: 170)
                .accessibilityLabel("Price with its fitted trend line and band")

                HStack(spacing: 8) {
                    StatTile(label: "Rate, per year", value: Fmt.percent(model.annualRate, signed: true), tint: tint)
                    StatTile(label: "Fit (R²)", value: String(format: "%.0f%%", model.rSquared * 100))
                    StatTile(label: "From the line", value: String(format: "%+.1fσ", model.deviations))
                }
                Text(model.summary).font(.footnote).foregroundStyle(.inkSecondary)
                Text("The solid line is the price; the dashed line is the fit, with a band two standard deviations either side. It measures the window shown — it does not project beyond it.")
                    .font(.caption2).foregroundStyle(.inkSecondary)
            } else {
                Notice(text: "Not enough price history to fit a trend over this window.")
            }
        }
    }
}

// MARK: - Levels

/// The prices that have mattered recently, laid out above and below today's.
struct LevelsCard: View {
    let levels: PriceLevels
    /// False when no live quote has arrived and the levels are measured from
    /// the last close.
    var isLive = true

    var body: some View {
        Card("Key levels") {
            let above = levels.levels.filter(\.isAbove)
            let below = levels.levels.filter { !$0.isAbove }
            ForEach(above) { LevelRow(level: $0) }
            HStack {
                Text(isLive ? "Price now" : "Last close").font(.subheadline.weight(.bold))
                Spacer()
                Text(Fmt.price(levels.price)).font(.subheadline.weight(.bold).monospacedDigit())
            }
            .padding(.horizontal, 10).padding(.vertical, 8)
            .background(Color.brand.opacity(0.12), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
            ForEach(below) { LevelRow(level: $0) }
            Divider()
            DetailRow("A typical day's range", "\(Fmt.price(levels.averageRange)) · \(Fmt.percent(levels.averageRangeShare))")
            Text("Averages, the highs and lows of the last 20 days and 52 weeks, and the most recent turning points, each with its distance from the price. A turning point is a high or low not passed for five days either side.")
                .font(.caption2).foregroundStyle(.inkSecondary)
        }
    }
}

private struct LevelRow: View {
    let level: PriceLevel

    var body: some View {
        HStack {
            Text(level.name).font(.subheadline).foregroundStyle(.inkSecondary)
            Spacer(minLength: 8)
            Text(Fmt.price(level.price)).font(.subheadline.monospacedDigit())
            Text(Fmt.percent(level.distance, signed: true))
                .font(.caption.weight(.semibold).monospacedDigit())
                .foregroundStyle(.inkSecondary)
                .frame(width: 62, alignment: .trailing)
        }
        .padding(.horizontal, 10)
        .accessibilityElement(children: .combine)
    }
}

// MARK: - Entry / exit test

/// Set an entry, a stop and a target, and see how often each was reached
/// when the same plan was tried on every day of the past five years.
struct EntryExitCard: View {
    @Environment(AppSession.self) private var session
    let symbol: String
    let closes: [DailyClose]
    let levels: PriceLevels?
    /// The live price, when there is one: the dollar levels are for a trade
    /// placed now, not at yesterday's close.
    var livePrice: Double?
    let onBuy: () -> Void

    @State private var plan: BracketPlan
    @State private var isDefault = true

    init(symbol: String, closes: [DailyClose], levels: PriceLevels?, livePrice: Double? = nil, onBuy: @escaping () -> Void) {
        self.symbol = symbol
        self.closes = closes
        self.levels = levels
        self.livePrice = livePrice
        self.onBuy = onBuy
        _plan = State(initialValue: BracketPlan.sized(to: levels))
    }

    var body: some View {
        let price = livePrice ?? closes.last?.close ?? 0
        let reference = livePrice == nil ? "the close" : "the price now"
        let entry = price * (1 - plan.entryDiscount)
        let outcome = BracketTest.run(closes: closes, plan: plan)

        Card("Test an entry and exit") {
            Text("Choose where you would buy, where you would give up, and where you would take the gain. The test tries that plan on every trading day of the past five years.")
                .font(.footnote).foregroundStyle(.inkSecondary)

            PlanRow(
                title: "Buy at", price: entry,
                detail: plan.entryDiscount == 0 ? reference : "\(Fmt.percent(plan.entryDiscount)) below \(reference)",
                tint: .brand
            ) { step in
                plan.entryDiscount = min(max(((plan.entryDiscount + 0.01 * step) * 100).rounded() / 100, 0), 0.20)
            }
            PlanRow(title: "Stop", price: entry * (1 - plan.stop), detail: "\(Fmt.percent(plan.stop)) below entry", tint: .loss) { step in
                plan.stop = min(max(((plan.stop + 0.005 * step) * 200).rounded() / 200, 0.005), 0.40)
            }
            PlanRow(title: "Target", price: entry * (1 + plan.target), detail: "\(Fmt.percent(plan.target)) above entry", tint: .gain) { step in
                plan.target = min(max(((plan.target + 0.01 * step) * 100).rounded() / 100, 0.01), 1.00)
            }
            Picker("Give it", selection: $plan.maxDays) {
                Text("1 month").tag(21)
                Text("3 months").tag(60)
                Text("6 months").tag(126)
            }
            .pickerStyle(.segmented)

            if let outcome {
                Divider()
                ResultBlock(title: "Every day, \(years(outcome.all))", result: outcome.all, plan: plan)
                if let similar = outcome.similar, let similarity = outcome.similarity {
                    Divider()
                    ResultBlock(title: "Only \(similarity)", result: similar, plan: plan)
                }
                Text("To break even, the target has to be reached on \(Fmt.percent(plan.breakevenWinRate)) of trades that end at one or the other. Each day starts its own trial, so these overlap: they count how often, not how reliably. A day that touched both levels is counted as stopped.")
                    .font(.caption2).foregroundStyle(.inkSecondary)
            } else {
                Notice(text: "Not enough price history to try this plan.")
            }

            NavigationLink {
                if let template = TemplateCatalog.runnable.first(where: { $0.id == "trend-following" }) {
                    TemplateSetupView(
                        template: template, presetTickers: [symbol],
                        presetExitPlan: ExitPlan(stopPercent: plan.stop * 100, finalTargetPercent: plan.target * 100)
                    )
                }
            } label: {
                Label("Backtest a strategy with this stop and target", systemImage: "chart.xyaxis.line")
            }
            .buttonStyle(SecondaryButtonStyle())
            .accessibilityIdentifier("bracket-to-strategy")

            if session.brokerageLink.canTrade {
                Button(action: onBuy) { Label("Buy \(symbol) at your broker", systemImage: "arrow.down.left.circle.fill") }
                    .buttonStyle(PrimaryButtonStyle())
                    .accessibilityIdentifier("bracket-buy")
            }
        }
        .sensoryFeedback(.selection, trigger: plan)
    }

    private func years(_ result: BracketResult) -> String {
        guard let from = result.from, let to = result.to else { return "past five years" }
        let calendar = Calendar(identifier: .gregorian)
        return "\(calendar.component(.year, from: from))–\(calendar.component(.year, from: to))"
    }
}

private struct PlanRow: View {
    let title: String
    let price: Double
    let detail: String
    let tint: Color
    /// Called with +1 or −1.
    let step: (Double) -> Void

    var body: some View {
        HStack(spacing: 10) {
            RoundedRectangle(cornerRadius: 2).fill(tint).frame(width: 4, height: 34)
            VStack(alignment: .leading, spacing: 1) {
                Text(title).font(.subheadline.weight(.semibold))
                Text(detail).font(.caption).foregroundStyle(.inkSecondary)
            }
            Spacer(minLength: 8)
            Text(Fmt.price(price)).font(.body.weight(.semibold).monospacedDigit())
            Stepper(title) { step(1) } onDecrement: { step(-1) }
                .labelsHidden()
        }
        .accessibilityElement(children: .combine)
    }
}

/// What happened across the tries: a bar split three ways, then the counts.
private struct ResultBlock: View {
    let title: String
    let result: BracketResult
    let plan: BracketPlan

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).eyebrowStyle()
            if result.entered == 0 {
                Text("The price never came down to the entry within \(plan.fillDays) trading days on any of \(result.tried) tries.")
                    .font(.subheadline)
            } else {
                GeometryReader { proxy in
                    HStack(spacing: 2) {
                        Rectangle().fill(Color.gain).frame(width: proxy.size.width * result.targetRate)
                        Rectangle().fill(Color.inkSecondary.opacity(0.4)).frame(width: proxy.size.width * result.timeoutRate)
                        Rectangle().fill(Color.loss)
                    }
                    .clipShape(Capsule())
                }
                .frame(height: 12)
                HStack(alignment: .top) {
                    Share(value: result.targetRate, label: "reached the target", color: .gain)
                    Share(value: result.timeoutRate, label: "reached neither", color: .inkSecondary)
                    Share(value: result.stopRate, label: "hit the stop", color: .loss)
                }
                DetailRow("Average result per trade", Fmt.percent(result.averageReturn, signed: true), tint: result.averageReturn.changeColor)
                DetailRow("Typical time in the trade", "\(result.medianDays) trading days")
                if plan.entryDiscount > 0 {
                    DetailRow("Entry price was reached", "\(Fmt.percent(result.fillRate)) of \(result.tried) tries")
                } else {
                    DetailRow("Days tried", result.entered.formatted(.number))
                }
            }
        }
        .accessibilityElement(children: .combine)
    }
}

private struct Share: View {
    let value: Double
    let label: String
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(String(format: "%.0f%%", value * 100)).font(.headline.monospacedDigit()).foregroundStyle(color)
            Text(label).font(.caption2).foregroundStyle(.inkSecondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
