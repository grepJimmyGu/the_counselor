import Charts
import LivermoreKit
import SwiftUI

/// A word from the options vocabulary that explains itself when tapped, so
/// nobody has to read an introduction first.
struct TermButton: View {
    let term: OptionTerm
    var label: String?
    @State private var isShown = false

    var body: some View {
        Button {
            isShown = true
        } label: {
            HStack(spacing: 3) {
                Text(label ?? term.title)
                Image(systemName: "info.circle").imageScale(.small)
            }
        }
        .buttonStyle(.plain)
        .accessibilityHint("Explains what \(term.title.lowercased()) means")
        .popover(isPresented: $isShown) {
            Text(term.meaning)
                .font(.footnote)
                .fixedSize(horizontal: false, vertical: true)
                .frame(width: 270, alignment: .leading)
                .padding(14)
                .presentationCompactAdaptation(.popover)
        }
    }
}

/// The trade in a sentence, under the day its prices are from.
struct OptionHeadlineCard: View {
    let plan: OptionPlan

    var body: some View {
        Card {
            HStack(spacing: 8) {
                Text(plan.strategy.name).eyebrowStyle()
                TermButton(term: plan.strategy.optionKind == .call ? .call : .put, label: "What is a \(plan.strategy.optionKind.rawValue)?")
                    .font(.caption2.weight(.semibold)).foregroundStyle(.brand)
            }
            Text(plan.headline)
                .font(.title3.weight(.semibold))
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("option-headline")
        }
    }
}

/// Cost, the most that can be lost, the most that can be made, the breakeven.
struct OptionFiguresGrid: View {
    let plan: OptionPlan

    var body: some View {
        let figures = plan.figures
        Grid(horizontalSpacing: 10, verticalSpacing: 10) {
            GridRow {
                tile(figures[0], term: .fee)
                tile(figures[1], tint: .loss)
            }
            GridRow {
                tile(figures[2], tint: .gain)
                tile(figures[3], term: .breakeven)
            }
        }
    }

    private func tile(_ figure: OptionFigure, tint: Color? = nil, term: OptionTerm? = nil) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Group {
                if let term {
                    TermButton(term: term, label: figure.label)
                } else {
                    Text(figure.label)
                }
            }
            .font(.caption).foregroundStyle(.inkSecondary)
            Text(figure.value)
                .font(.title3.weight(.semibold).monospacedDigit())
                .foregroundStyle(tint ?? .primary)
                .lineLimit(1).minimumScaleFactor(0.7)
                .contentTransition(.numericText())
            Text(figure.detail)
                .font(.caption2).foregroundStyle(.inkSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .padding(12)
        .background(Color.surface, in: RoundedRectangle(cornerRadius: Metrics.tileRadius, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: Metrics.tileRadius, style: .continuous)
                .strokeBorder(Color.hairline.opacity(0.6), lineWidth: 0.5)
        )
        .accessibilityElement(children: .combine)
    }
}

/// Profit or loss at expiry for every price the stock could be at.
struct PayoffCard: View {
    let plan: OptionPlan
    /// The range option prices imply by the plan's expiry, when it is known.
    var impliedRange: ClosedRange<Double>?

    @State private var probe: Double?

    private struct Point: Identifiable {
        let price: Double
        let profit: Double
        var id: Double { price }
    }

    /// A round step for the "what if" slider: about 150 stops across the chart.
    private static func step(for span: Double) -> Double {
        [0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 25, 50].first { $0 >= span / 150 } ?? 100
    }

    var body: some View {
        let raw = plan.chartRange(including: impliedRange)
        let step = Self.step(for: raw.upperBound - raw.lowerBound)
        // Whole steps at both ends, so the slider can reach each end exactly.
        let range = ((raw.lowerBound / step).rounded(.down) * step)...((raw.upperBound / step).rounded(.up) * step)
        let points = plan.payoff.curve(from: range.lowerBound, to: range.upperBound).map { Point(price: $0.price, profit: $0.profit) }
        let profits = points.map(\.profit)
        let top = max(profits.max() ?? 0, 0), bottom = min(profits.min() ?? 0, 0)
        let pad = max((top - bottom) * 0.12, 1)
        let picked = probe.map { min(max($0, range.lowerBound), range.upperBound) }
        let day = OptionText.shortDay(plan.expiration)

        Card("On \(day), at each share price") {
            Chart {
                if let impliedRange {
                    RectangleMark(
                        xStart: .value("Low", impliedRange.lowerBound),
                        xEnd: .value("High", impliedRange.upperBound),
                        yStart: .value("Bottom", bottom - pad),
                        yEnd: .value("Top", top + pad)
                    )
                    .foregroundStyle(Color.inkSecondary.opacity(0.10))
                }
                ForEach(points) { point in
                    AreaMark(
                        x: .value("Price", point.price),
                        yStart: .value("Zero", 0),
                        yEnd: .value("Profit", max(point.profit, 0)),
                        series: .value("Side", "gain")
                    )
                    .foregroundStyle(Color.gain.opacity(0.20))
                    AreaMark(
                        x: .value("Price", point.price),
                        yStart: .value("Zero", 0),
                        yEnd: .value("Loss", min(point.profit, 0)),
                        series: .value("Side", "loss")
                    )
                    .foregroundStyle(Color.loss.opacity(0.20))
                }
                RuleMark(y: .value("Zero", 0))
                    .foregroundStyle(Color.inkSecondary.opacity(0.6))
                    .lineStyle(StrokeStyle(lineWidth: 1))
                RuleMark(x: .value("Close", plan.underlyingPrice))
                    .foregroundStyle(Color.inkSecondary)
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))
                ForEach(points) { point in
                    LineMark(x: .value("Price", point.price), y: .value("Profit", point.profit), series: .value("Line", "payoff"))
                        .foregroundStyle(Color.primary)
                        .lineStyle(StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
                }
                if let breakeven = plan.breakeven, range.contains(breakeven) {
                    PointMark(x: .value("Breakeven", breakeven), y: .value("Zero", 0))
                        .foregroundStyle(Color.brand).symbolSize(70)
                }
                if let picked {
                    RuleMark(x: .value("Picked", picked)).foregroundStyle(Color.inkSecondary.opacity(0.7))
                    PointMark(x: .value("Picked", picked), y: .value("Profit", plan.payoff.profit(at: picked)))
                        .foregroundStyle(Color.primary).symbolSize(60)
                }
            }
            .chartXScale(domain: range)
            .chartYScale(domain: (bottom - pad)...(top + pad))
            .chartYAxis {
                AxisMarks(position: .trailing, values: .automatic(desiredCount: 4)) { value in
                    AxisGridLine().foregroundStyle(Color.hairline.opacity(0.5))
                    AxisValueLabel {
                        if let amount = value.as(Double.self) {
                            Text(amount == 0 ? "$0" : (amount > 0 ? "+" : "−") + Fmt.compactMoney(abs(amount)))
                        }
                    }
                }
            }
            .chartXAxis {
                AxisMarks(values: .automatic(desiredCount: 4)) { value in
                    AxisValueLabel {
                        if let amount = value.as(Double.self) { Text(Fmt.axisPrice(amount)) }
                    }
                }
            }
            .frame(height: 210)
            .accessibilityLabel("Profit or loss on \(day) by \(plan.symbol) share price")
            .accessibilityIdentifier("option-payoff-chart")

            // A slider, not a drag on the chart: a sideways drag on the chart
            // is taken by the system as "go back" and closes the screen.
            VStack(alignment: .leading, spacing: 2) {
                Text(picked.map(plan.outcome(at:)) ?? "Move the slider to see what you make or lose at any share price.")
                    .font(.subheadline)
                    .foregroundStyle(picked == nil ? Color.inkSecondary : .primary)
                    .frame(minHeight: 40, alignment: .topLeading)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("option-outcome")
                Slider(
                    value: Binding(get: { picked ?? plan.underlyingPrice }, set: { probe = $0 }),
                    in: range, step: step
                )
                .accessibilityLabel("\(plan.symbol) share price on \(day)")
                .accessibilityValue(OptionText.price(picked ?? plan.underlyingPrice))
                .accessibilityIdentifier("option-what-if")
            }
            .sensoryFeedback(.selection, trigger: picked)

            VStack(alignment: .leading, spacing: 6) {
                legend(line: true, dashed: true, color: .inkSecondary, text: "\(plan.symbol) closed at \(OptionText.price(plan.underlyingPrice))")
                if let breakeven = plan.breakeven {
                    legend(line: false, dashed: false, color: .brand, text: "Breakeven \(OptionText.price(breakeven))")
                }
                if let impliedRange {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        RoundedRectangle(cornerRadius: 2).fill(Color.inkSecondary.opacity(0.22)).frame(width: 14, height: 10)
                        Text("Option prices imply \(OptionText.price(impliedRange.lowerBound)) to \(OptionText.price(impliedRange.upperBound)) by \(day)")
                        TermButton(term: .impliedRange, label: "").foregroundStyle(.brand)
                    }
                }
            }
            .font(.caption).foregroundStyle(.inkSecondary)
        }
    }

    private func legend(line: Bool, dashed: Bool, color: Color, text: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Group {
                if line {
                    Rectangle().fill(color).frame(width: 14, height: 1.5)
                        .overlay { if dashed { HStack(spacing: 3) { Color.surface.frame(width: 3) } } }
                } else {
                    Circle().fill(color).frame(width: 9, height: 9).frame(width: 14)
                }
            }
            .alignmentGuide(.firstTextBaseline) { $0[.bottom] + 3 }
            Text(text)
        }
    }
}

/// The date a plan's prices are from, where it cannot be missed.
struct OptionPricesDate: View {
    let asOf: String

    var body: some View {
        Label("Prices from the close on \(OptionText.day(asOf))", systemImage: "calendar")
            .font(.eyebrow).tracking(0.6).textCase(.uppercase).foregroundStyle(.inkSecondary)
            .accessibilityIdentifier("option-prices-date")
    }
}
