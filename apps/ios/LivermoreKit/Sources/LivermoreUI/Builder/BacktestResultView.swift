import Charts
import LivermoreAPI
import LivermoreKit
import SwiftUI

/// How a strategy would have done: headline numbers, growth against the
/// benchmark, yearly returns and the trades behind them.
struct BacktestResultView: View {
    @Environment(AppSession.self) private var session
    @Environment(\.dismiss) private var dismiss
    let result: BacktestResult
    let templateID: String?

    private enum SaveState: Equatable {
        case idle, saving, saved
        case failed(String)
    }

    @State private var saveState: SaveState = .idle

    private var strategy: StrategyJSON { result.strategyJson }
    private var metrics: BacktestMetrics { result.metrics }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 4) {
                    // The period first: every number below describes it.
                    Text("\(strategy.startDate) TO \(strategy.endDate)")
                        .font(.caption2.weight(.semibold)).tracking(0.8).foregroundStyle(.secondary)
                    Text(strategy.strategyName).font(.title3.weight(.semibold))
                    Text(strategy.universe.joined(separator: ", ")).font(.subheadline).foregroundStyle(.secondary)
                }

                ForEach(result.warnings, id: \.self) { warning in
                    Label(warning, systemImage: "exclamationmark.triangle")
                        .font(.footnote).foregroundStyle(.orange)
                }

                Card("Result") {
                    Grid(horizontalSpacing: 12, verticalSpacing: 12) {
                        GridRow {
                            Stat("Total return", Fmt.percent(metrics.totalReturn, signed: true), tint: metrics.totalReturn.changeColor)
                            Stat("\(strategy.benchmark) over the same period", Fmt.percent(metrics.benchmarkTotalReturn, signed: true))
                        }
                        GridRow {
                            Stat("Per year", Fmt.percent(metrics.annualizedReturn, signed: true))
                            Stat("Worst drop", Fmt.percent(metrics.maxDrawdown))
                        }
                        GridRow {
                            Stat("Sharpe ratio", String(format: "%.2f", metrics.sharpeRatio))
                            Stat("Time invested", Fmt.percent(metrics.timeInMarket))
                        }
                        GridRow {
                            Stat("Trades", "\(metrics.numberOfTrades)")
                            Stat("Winning trades", Fmt.percent(metrics.winRate))
                        }
                    }
                }

                GrowthChart(result: result, benchmark: strategy.benchmark)

                if !result.annualReturns.isEmpty {
                    Card("By year") {
                        ForEach(result.annualReturns, id: \.year) { year in
                            HStack {
                                Text(String(year.year)).font(.subheadline.monospacedDigit())
                                Spacer()
                                Text(Fmt.percent(year.returnPct, signed: true))
                                    .font(.subheadline.weight(.semibold).monospacedDigit())
                                    .foregroundStyle(year.returnPct.changeColor)
                            }
                        }
                    }
                }

                if !result.tradeLog.isEmpty {
                    let recent = Array(result.tradeLog.suffix(20).reversed())
                    Card(result.tradeLog.count > recent.count ? "Last \(recent.count) of \(result.tradeLog.count) trades" : "Trades") {
                        ForEach(Array(recent.enumerated()), id: \.offset) { index, trade in
                            if index > 0 { Divider() }
                            HStack(alignment: .firstTextBaseline) {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(trade.symbol).font(.subheadline.weight(.semibold))
                                    Text("\(trade.entryDate) → \(trade.exitDate) · \(trade.holdingPeriodDays) days")
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                                Spacer()
                                Text(Fmt.percent(trade.returnPct, signed: true))
                                    .font(.subheadline.monospacedDigit())
                                    .foregroundStyle(trade.returnPct.changeColor)
                            }
                        }
                    }
                }

                settingsSection

                saveSection

                Text("This backtest shows how the strategy would have performed against historical data. Real-world execution differs (slippage, fees, market regime shifts). Research tool, not advice.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            .padding()
        }
        .background(Color.groupedBackground)
        .navigationTitle("Backtest")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
    }

    /// What produced these numbers, and the way back to change it.
    private var settingsSection: some View {
        Card("Settings used") {
            LabeledContent("Starting capital", value: Fmt.wholeMoney(strategy.initialCapital))
            LabeledContent("Costs per trade", value: costSummary)
            if strategy.positionSizing.method == .volTarget, let target = strategy.positionSizing.targetVolAnnual {
                LabeledContent("Volatility target", value: Fmt.percent(target))
            }
            if let ladder = strategy.riskManagement?.exitLadder, !ladder.isEmpty {
                Divider()
                Text("Exit plan").font(.subheadline.weight(.semibold))
                ForEach(Array(ladder.enumerated()), id: \.offset) { _, tier in
                    LabeledContent(
                        tier.label ?? Fmt.percent(tier.triggerPct, signed: true),
                        value: tier.action == .sellAll
                            ? "Sell everything"
                            : "Sell \(Int(((tier.fraction ?? 0) * 100).rounded()))% of the position"
                    )
                }
            }
            Button {
                dismiss()
            } label: {
                Label("Change settings and run again", systemImage: "slider.horizontal.3")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
            .accessibilityIdentifier("adjust-and-rerun")
        }
        .font(.subheadline)
    }

    private var costSummary: String {
        let total = (strategy.transactionCostBps ?? 0) + (strategy.slippageBps ?? 0)
        return total == 0 ? "None" : String(format: "%.2f%%", total / 100)
    }

    @ViewBuilder
    private var saveSection: some View {
        Card("Keep this strategy") {
            if !session.isSignedIn {
                Text("Sign in from the Account tab to save strategies and track positions against them.")
                    .font(.subheadline).foregroundStyle(.secondary)
            } else {
                switch saveState {
                case .saved:
                    Label("Saved. It's in your Strategies tab.", systemImage: "checkmark.circle.fill")
                        .font(.subheadline).foregroundStyle(.green)
                default:
                    Button(action: save) {
                        HStack {
                            Text(saveState == .saving ? "Saving…" : "Save strategy")
                            if saveState == .saving { ProgressView() }
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(saveState == .saving)
                    .accessibilityIdentifier("save-strategy")
                    if case .failed(let message) = saveState {
                        Text(message).font(.footnote).foregroundStyle(.red)
                    }
                }
            }
        }
    }

    private func save() {
        saveState = .saving
        Task {
            do throws(APIFailure) {
                _ = try await session.backtests.save(
                    title: strategy.strategyName, strategy: strategy, backtestID: result.backtestId
                )
                saveState = .saved
            } catch {
                if error == .notSignedIn { session.signOut() }
                saveState = .failed(error.message)
            }
        }
    }
}

private struct GrowthChart: View {
    let result: BacktestResult
    let benchmark: String

    private struct Point: Identifiable {
        let series: String
        let date: Date
        let value: Double
        var id: String { "\(series)-\(date.timeIntervalSince1970)" }
    }

    private var points: [Point] {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd"
        func series(_ name: String, _ curve: [Components.Schemas.CurvePoint]) -> [Point] {
            // A daily curve over ten years is ~2,500 points per line; a phone
            // chart shows no more detail past a few hundred.
            let step = max(1, curve.count / 300)
            return curve.enumerated().compactMap { index, point in
                guard index % step == 0 || index == curve.count - 1,
                      let date = formatter.date(from: String(point.date.prefix(10)))
                else { return nil }
                return Point(series: name, date: date, value: point.value)
            }
        }
        return series("Strategy", result.equityCurve) + series(benchmark, result.benchmarkCurve)
    }

    private var yDomain: ClosedRange<Double> {
        let values = points.map(\.value)
        guard let low = values.min(), let high = values.max(), high > low else { return 0...1 }
        let pad = (high - low) * 0.08
        return (low - pad)...(high + pad)
    }

    var body: some View {
        Card("Growth of your starting capital") {
            Chart(points) { point in
                LineMark(x: .value("Date", point.date), y: .value("Value", point.value))
                    .foregroundStyle(by: .value("Series", point.series))
            }
            .chartForegroundStyleScale(["Strategy": Color.blue, benchmark: Color.gray])
            // Scaled to the data: starting the axis at zero flattens both
            // lines into the top of the chart.
            .chartYScale(domain: yDomain)
            .chartYAxis {
                AxisMarks { value in
                    AxisGridLine()
                    AxisValueLabel {
                        if let amount = value.as(Double.self) { Text(Fmt.compactMoney(amount)) }
                    }
                }
            }
            .frame(height: 200)
            .accessibilityLabel("Strategy value against \(benchmark) over the test period")
        }
    }
}
