import Charts
import LivermoreAPI
import LivermoreKit
import SwiftUI

/// How a strategy would have done: the headline against the benchmark, the
/// growth of the money, the numbers behind it, and what to do next.
struct BacktestResultView: View {
    @Environment(AppSession.self) private var session
    @Environment(\.dismiss) private var dismiss
    let result: BacktestResult
    let templateID: String?

    private enum SaveState: Equatable {
        case idle, saving
        case saved(SavedStrategy)
        case failed(String)
    }

    @State private var saveState: SaveState = .idle
    @State private var showsAllTrades = false

    private var strategy: StrategyJSON { result.strategyJson }
    private var metrics: BacktestMetrics { result.metrics }
    private var edge: Double { metrics.totalReturn - metrics.benchmarkTotalReturn }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: Metrics.sectionSpacing) {
                hero
                ForEach(result.warnings, id: \.self) { warning in
                    Notice(text: warning, systemImage: "exclamationmark.triangle.fill", tint: .caution)
                }
                GrowthChart(result: result, benchmark: strategy.benchmark)
                numbers
                if result.annualReturns.count > 1 { byYear }
                if !result.tradeLog.isEmpty { trades }
                settings
                Text("This backtest shows how the strategy would have performed against historical data. Real-world execution differs (slippage, fees, market regime shifts). Research tool, not advice.")
                    .font(.caption2).foregroundStyle(.inkSecondary).padding(.horizontal, 4)
            }
            .padding(Metrics.screenPadding)
        }
        .screenBackground()
        .navigationTitle("Backtest")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .bottomBar { actions }
        .sensoryFeedback(.success, trigger: saveState) { _, new in
            if case .saved = new { true } else { false }
        }
    }

    // MARK: Sections

    private var hero: some View {
        VStack(alignment: .leading, spacing: 6) {
            // The period first: every number below describes it.
            Text("\(strategy.startDate) to \(strategy.endDate)").eyebrowStyle()
            Text(strategy.strategyName).font(.title3.weight(.semibold))
            Text(Fmt.percent(metrics.totalReturn, signed: true))
                .font(.hero).foregroundStyle(metrics.totalReturn.changeColor)
            HStack(spacing: 8) {
                Tag("\(Fmt.points(edge)) vs \(strategy.benchmark)", tint: edge.changeColor,
                    systemImage: edge >= 0 ? "arrow.up.right" : "arrow.down.right")
                Text("\(strategy.benchmark) returned \(Fmt.percent(metrics.benchmarkTotalReturn, signed: true))")
                    .font(.footnote.monospacedDigit()).foregroundStyle(.inkSecondary)
            }
            Text(verdict).font(.subheadline).foregroundStyle(.inkSecondary).padding(.top, 2)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 4)
    }

    /// The result in a sentence, stated as what happened and nothing more.
    private var verdict: String {
        let ending = Fmt.wholeMoney(strategy.initialCapital * (1 + metrics.totalReturn))
        let start = Fmt.wholeMoney(strategy.initialCapital)
        let comparison = edge >= 0 ? "ahead of" : "behind"
        return "\(start) became \(ending), \(comparison) simply holding \(strategy.benchmark), while invested \(Fmt.percent(metrics.timeInMarket)) of the time."
    }

    private var numbers: some View {
        Card("The numbers") {
            LazyVGrid(columns: [GridItem(.flexible(), spacing: 8), GridItem(.flexible(), spacing: 8)], spacing: 8) {
                StatTile(label: "Per year", value: Fmt.percent(metrics.annualizedReturn, signed: true), tint: metrics.annualizedReturn.changeColor)
                StatTile(label: "Worst drop", value: Fmt.percent(metrics.maxDrawdown), tint: .loss)
                StatTile(label: "Sharpe ratio", value: String(format: "%.2f", metrics.sharpeRatio), note: "Return per unit of risk")
                StatTile(label: "Time invested", value: Fmt.percent(metrics.timeInMarket))
                StatTile(label: "Trades", value: "\(metrics.numberOfTrades)")
                StatTile(label: "Winning trades", value: Fmt.percent(metrics.winRate))
            }
        }
    }

    private var byYear: some View {
        Card("Year by year") {
            Chart(result.annualReturns, id: \.year) { year in
                BarMark(x: .value("Year", String(year.year)), y: .value("Return", year.returnPct), width: .ratio(0.6))
                    .foregroundStyle(year.returnPct >= 0 ? Color.gain : Color.loss)
                    .cornerRadius(4)
                    .annotation(position: year.returnPct >= 0 ? .top : .bottom, spacing: 3) {
                        Text(Fmt.percent(year.returnPct, signed: true))
                            .font(.caption2.monospacedDigit()).foregroundStyle(.inkSecondary)
                    }
            }
            .chartYAxis(.hidden)
            .frame(height: 150)
            .accessibilityLabel("Return in each calendar year")
        }
    }

    private var trades: some View {
        let all = Array(result.tradeLog.reversed())
        let shown = showsAllTrades ? Array(all.prefix(50)) : Array(all.prefix(5))
        return Card("Trades", accessory: {
            Text("\(result.tradeLog.count)").font(.subheadline.monospacedDigit()).foregroundStyle(.inkSecondary)
        }, content: {
            ForEach(Array(shown.enumerated()), id: \.offset) { index, trade in
                if index > 0 { Divider() }
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(trade.symbol).font(.subheadline.weight(.semibold).monospaced())
                        Text("\(trade.entryDate) → \(trade.exitDate) · \(trade.holdingPeriodDays) days")
                            .font(.caption).foregroundStyle(.inkSecondary)
                    }
                    Spacer()
                    ChangePill(fraction: trade.returnPct, compact: true)
                }
            }
            if all.count > 5 {
                Button(showsAllTrades ? "Show fewer" : all.count <= 50 ? "Show all \(all.count)" : "Show the last 50") {
                    withAnimation { showsAllTrades.toggle() }
                }
                .font(.subheadline.weight(.semibold))
            }
        })
    }

    /// What produced these numbers.
    private var settings: some View {
        Card("Settings used") {
            DetailRow("Tickers", strategy.universe.joined(separator: ", "))
            DetailRow("Starting capital", Fmt.wholeMoney(strategy.initialCapital))
            DetailRow("Costs per trade", costSummary)
            if strategy.positionSizing.method == .volTarget, let target = strategy.positionSizing.targetVolAnnual {
                DetailRow("Volatility target", Fmt.percent(target))
            }
            if let ladder = strategy.riskManagement?.exitLadder, !ladder.isEmpty {
                Divider()
                Text("Exit plan").eyebrowStyle()
                ForEach(Array(ladder.enumerated()), id: \.offset) { _, tier in
                    DetailRow(
                        tier.label ?? Fmt.percent(tier.triggerPct, signed: true),
                        tier.action == .sellAll
                            ? "Sell everything"
                            : "Sell \(Int(((tier.fraction ?? 0) * 100).rounded()))% of the position",
                        tint: tier.triggerPct < 0 ? .loss : .gain
                    )
                }
            } else {
                Notice(text: "No stop or targets. Add an exit plan in Settings to have Livermore watch a position against this strategy.")
            }
        }
    }

    private var costSummary: String {
        let total = (strategy.transactionCostBps ?? 0) + (strategy.slippageBps ?? 0)
        return total == 0 ? "None" : String(format: "%.2f%%", total / 100)
    }

    // MARK: Actions

    @ViewBuilder
    private var actions: some View {
        if case .failed(let message) = saveState {
            Text(message).font(.footnote).foregroundStyle(.loss).frame(maxWidth: .infinity, alignment: .leading)
        }
        if case .saved(let saved) = saveState {
            // Straight on to acting on it: buy at the broker, or track a
            // position already held.
            NavigationLink {
                StrategyDetailView(strategy: saved, trackedPositions: [])
            } label: {
                Label(saved.tracksExits ? "Saved — put it to work" : "Saved — open the strategy", systemImage: "checkmark.circle.fill")
            }
            .buttonStyle(PrimaryButtonStyle(tint: .gain))
            .accessibilityIdentifier("open-saved-strategy")
        } else {
            HStack(spacing: 10) {
                Button {
                    dismiss()
                } label: {
                    Label("Adjust", systemImage: "slider.horizontal.3")
                }
                .buttonStyle(SecondaryButtonStyle())
                .accessibilityIdentifier("adjust-and-rerun")

                if session.isSignedIn {
                    Button(action: save) {
                        HStack(spacing: 8) {
                            if saveState == .saving { ProgressView().tint(.white) }
                            Text(saveState == .saving ? "Saving…" : "Save strategy")
                        }
                    }
                    .buttonStyle(PrimaryButtonStyle())
                    .disabled(saveState == .saving)
                    .accessibilityIdentifier("save-strategy")
                }
            }
            if !session.isSignedIn {
                Text("Sign in from the Account tab to save this strategy and track positions against it.")
                    .font(.footnote).foregroundStyle(.inkSecondary).frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    private func save() {
        saveState = .saving
        Task {
            do throws(APIFailure) {
                let saved = try await session.backtests.save(
                    title: strategy.strategyName, strategy: strategy, backtestID: result.backtestId
                )
                saveState = .saved(saved)
            } catch {
                if error == .notSignedIn { session.signOut() }
                saveState = .failed(error.message)
            }
        }
    }
}

/// The strategy's value over the test against the benchmark's. Touch and
/// drag to read both on any day.
private struct GrowthChart: View {
    let result: BacktestResult
    let benchmark: String

    @State private var selectedDate: Date?

    private struct Point: Identifiable {
        let date: Date
        let strategy: Double
        let benchmark: Double?
        var id: Date { date }
    }

    private var points: [Point] {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd"
        var benchmarkByDay: [String: Double] = [:]
        for point in result.benchmarkCurve { benchmarkByDay[String(point.date.prefix(10))] = point.value }
        // A daily curve over ten years is ~2,500 points; a phone chart shows
        // no more detail past a few hundred.
        let curve = result.equityCurve
        let step = max(1, curve.count / 300)
        return curve.enumerated().compactMap { index, point in
            let day = String(point.date.prefix(10))
            guard index % step == 0 || index == curve.count - 1, let date = formatter.date(from: day) else { return nil }
            return Point(date: date, strategy: point.value, benchmark: benchmarkByDay[day])
        }
    }

    var body: some View {
        let points = points
        let selected = selectedDate.flatMap { date in
            points.min { abs($0.date.timeIntervalSince(date)) < abs($1.date.timeIntervalSince(date)) }
        }
        let shown = selected ?? points.last
        let values = points.flatMap { [$0.strategy] + ($0.benchmark.map { [$0] } ?? []) }
        let low = values.min() ?? 0
        let high = values.max() ?? 1
        let pad = max((high - low) * 0.08, 1)

        Card {
            VStack(alignment: .leading, spacing: 6) {
                Text(selected.map { Fmt.tradingDay($0.date) } ?? "Growth of your starting capital")
                    .eyebrowStyle()
                HStack(spacing: 16) {
                    LegendValue(name: "Strategy", value: shown.map { Fmt.wholeMoney($0.strategy) }, color: .brand)
                    LegendValue(name: benchmark, value: shown?.benchmark.map { Fmt.wholeMoney($0) }, color: .inkSecondary)
                }
            }
            if points.count > 1 {
                Chart {
                    ForEach(points) { point in
                        if let value = point.benchmark {
                            LineMark(x: .value("Date", point.date), y: .value("Value", value), series: .value("Series", benchmark))
                                .foregroundStyle(Color.inkSecondary.opacity(0.7))
                                .lineStyle(StrokeStyle(lineWidth: 1.5, lineCap: .round, lineJoin: .round))
                        }
                        LineMark(x: .value("Date", point.date), y: .value("Value", point.strategy), series: .value("Series", "Strategy"))
                            .foregroundStyle(Color.brand)
                            .lineStyle(StrokeStyle(lineWidth: 2.2, lineCap: .round, lineJoin: .round))
                    }
                    if let selected {
                        RuleMark(x: .value("Date", selected.date)).foregroundStyle(Color.inkSecondary.opacity(0.6))
                        PointMark(x: .value("Date", selected.date), y: .value("Value", selected.strategy))
                            .foregroundStyle(Color.brand).symbolSize(70)
                    }
                }
                // Scaled to the data: starting the axis at zero flattens
                // both lines into the top of the chart.
                .chartYScale(domain: (low - pad)...(high + pad))
                .chartYAxis {
                    AxisMarks(position: .trailing, values: .automatic(desiredCount: 4)) { value in
                        AxisGridLine().foregroundStyle(Color.hairline.opacity(0.5))
                        AxisValueLabel {
                            if let amount = value.as(Double.self) { Text(Fmt.compactMoney(amount)) }
                        }
                    }
                }
                .chartXAxis {
                    AxisMarks(values: .automatic(desiredCount: 4)) { _ in
                        AxisValueLabel(format: .dateTime.year())
                    }
                }
                .chartXSelection(value: $selectedDate)
                .frame(height: 210)
                .sensoryFeedback(.selection, trigger: selected?.date)
                .accessibilityLabel("Strategy value against \(benchmark) over the test period")
            }
        }
    }
}

private struct LegendValue: View {
    let name: String
    let value: String?
    let color: Color

    var body: some View {
        HStack(spacing: 6) {
            Circle().fill(color).frame(width: 8, height: 8)
            Text(name).font(.caption).foregroundStyle(.inkSecondary)
            Text(value ?? "—").font(.subheadline.weight(.semibold).monospacedDigit())
        }
        .accessibilityElement(children: .combine)
    }
}
