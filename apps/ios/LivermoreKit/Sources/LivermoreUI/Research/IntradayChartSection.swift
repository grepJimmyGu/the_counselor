import Charts
import LivermoreKit
import SwiftUI

/// The 1D and 1W charts: prices through the day, measured from the close
/// before them, ending on the live price while today's session is open.
/// Touch and drag to read any bar.
struct IntradayChartSection: View {
    @Environment(AppSession.self) private var session
    let symbol: String
    let range: IntradayRange

    @State private var charts: [IntradayRange: IntradayChart] = [:]
    @State private var failed: Set<IntradayRange> = []
    @State private var selectedX: Double?

    private var quote: LiveQuote? { session.quotes.quotes[symbol.uppercased()] }

    var body: some View {
        let series = charts[range].map {
            IntradaySeries(chart: $0, range: range, livePrice: quote?.price, liveAt: session.quotes.lastChecked)
        }
        let selected = selectedX.flatMap { series?.point(nearest: $0) }

        Group {
            header(series, selected: selected)
            if let series, series.points.count > 1 {
                chart(series, selected: selected)
                Text(caption(series))
                    .font(.caption).foregroundStyle(.inkSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            } else if failed.contains(range) {
                Notice(text: "Prices through the day aren't available for \(symbol) right now.", systemImage: "chart.line.downtrend.xyaxis")
                    .frame(height: 200, alignment: .center)
            } else {
                SkeletonBlock(height: 200)
            }
        }
        .task(id: range) { await keepFresh() }
    }

    // MARK: Loading

    /// Loads the chart, then again every minute while a session is open so
    /// the line keeps up. The live price moves the line's end in between.
    private func keepFresh() async {
        selectedX = nil
        while !Task.isCancelled {
            await load(range)
            let wait: Duration = MarketHours.isRegularSession(at: .now) ? .seconds(60) : .seconds(15 * 60)
            try? await Task.sleep(for: wait)
        }
    }

    private func load(_ range: IntradayRange) async {
        do throws(APIFailure) {
            charts[range] = try await session.research.intraday(symbol, range: range)
            failed.remove(range)
        } catch {
            // A failed refresh keeps the chart already on screen.
            if charts[range] == nil { failed.insert(range) }
        }
    }

    // MARK: Header

    private func title(_ series: IntradaySeries) -> String {
        switch range {
        case .oneDay:
            let day = series.isToday ? "Today" : series.sessionStarts.last.map { Fmt.weekdayTradingDay($0.day) } ?? "Latest session"
            return series.measuredFromOpen ? "\(day) · from the open" : day
        case .oneWeek:
            let count = series.sessionCount
            if count >= IntradayRange.oneWeek.sessions { return "Past week" }
            guard let first = series.sessionStarts.first else { return "Past week" }
            return "Since \(Fmt.weekdayTradingDay(first.day)) · \(count) trading day\(count == 1 ? "" : "s")"
        }
    }

    private func readout(_ point: IntradaySeries.Point) -> String {
        let time = "\(Fmt.marketTime(point.time)) ET"
        if point.isLive { return "Live · \(time)" }
        guard range == .oneWeek else { return time }
        let parts = IntradaySeries.newYork.dateComponents([.year, .month, .day], from: point.time)
        let day = PerformanceSeries.utc.date(from: parts).map(Fmt.weekdayTradingDay) ?? ""
        return "\(day) · \(time)"
    }

    @ViewBuilder
    private func header(_ series: IntradaySeries?, selected: IntradaySeries.Point?) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            if let selected {
                Text(readout(selected)).eyebrowStyle()
                Text(Fmt.price(selected.price)).font(.title3.weight(.semibold).monospacedDigit())
            } else if let series {
                let change = series.change
                HStack(spacing: 6) {
                    Text(title(series)).eyebrowStyle()
                    if series.endsLive {
                        HStack(spacing: 3) {
                            Circle().fill(Color.brand).frame(width: 6, height: 6)
                            Text("LIVE").font(.caption2.weight(.bold)).tracking(0.6).foregroundStyle(Color.brand)
                        }
                        .accessibilityLabel("Live")
                    }
                }
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(Fmt.percent(change, signed: true))
                        .font(.title3.weight(.semibold).monospacedDigit()).foregroundStyle((change ?? 0).changeColor)
                    if let base = series.base, let last = series.points.last {
                        Text(Fmt.signedMoney(last.price - base))
                            .font(.subheadline.monospacedDigit()).foregroundStyle(.inkSecondary)
                    }
                }
            } else {
                Text(range == .oneDay ? "Today" : "Past week").eyebrowStyle()
            }
        }
        .frame(maxWidth: .infinity, minHeight: 44, alignment: .topLeading)
    }

    /// "Previous close $165.05 · 5-min prices to 12:25 PM ET, then live", or
    /// for a week "From the Nov 17 close, $158.20 · …".
    private func caption(_ series: IntradaySeries) -> String {
        var parts: [String] = []
        if let close = series.previousClose {
            let amount = "\(series.previousCloseIsApproximate ? "≈ " : "")\(Fmt.price(close))"
            if range == .oneWeek, let day = series.previousCloseDay {
                parts.append("From the \(Fmt.shortTradingDay(day)) close, \(amount)")
            } else {
                parts.append("Previous close \(amount)")
            }
        } else {
            parts.append("From the first price shown")
        }
        var prices = "\(series.intervalMinutes)-min prices"
        if series.isToday, let through = series.barsThrough {
            prices += " to \(Fmt.marketTime(through)) ET"
            if series.endsLive { prices += ", then live" }
        } else {
            prices += ", times ET"
        }
        parts.append(prices)
        return parts.joined(separator: " · ")
    }

    // MARK: Chart

    /// Where the x axis is labelled: the hours of a day, or the middle of
    /// each day of a week.
    private func axisLabels(_ series: IntradaySeries) -> [(x: Double, text: String)] {
        switch range {
        case .oneDay:
            return [(30.0, "10 AM"), (150.0, "12 PM"), (270.0, "2 PM")].map { (series.x(minutesAfterOpen: $0.0), $0.1) }
        case .oneWeek:
            return series.sessionStarts.map { start in
                (start.x + series.slotsPerSession / 2, start.day.formatted(Fmt.utc(.dateTime.weekday(.abbreviated))))
            }
        }
    }

    private func chart(_ series: IntradaySeries, selected: IntradaySeries.Point?) -> some View {
        let color = (series.change ?? 0).changeColor
        let prices = series.points.map(\.price) + [series.previousClose].compactMap { $0 }
        let low = prices.min() ?? 0
        let high = prices.max() ?? 1
        let pad = max((high - low) * 0.08, high * 0.002)
        let labels = axisLabels(series)

        return Chart {
            ForEach(series.points) { point in
                AreaMark(
                    x: .value("Time", point.x),
                    yStart: .value("Floor", low - pad),
                    yEnd: .value("Price", point.price)
                )
                .foregroundStyle(LinearGradient(colors: [color.opacity(0.22), color.opacity(0)], startPoint: .top, endPoint: .bottom))
                LineMark(x: .value("Time", point.x), y: .value("Price", point.price))
                    .foregroundStyle(color)
                    .lineStyle(StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
            }
            if let close = series.previousClose {
                RuleMark(y: .value("Previous close", close))
                    .foregroundStyle(Color.inkSecondary.opacity(0.5))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))
            }
            // Where one day ends and the next begins.
            ForEach(series.sessionStarts.dropFirst()) { start in
                RuleMark(x: .value("Day", start.x))
                    .foregroundStyle(Color.hairline.opacity(0.8))
                    .lineStyle(StrokeStyle(lineWidth: 1))
            }
            if let last = series.points.last, last.isLive {
                PointMark(x: .value("Time", last.x), y: .value("Price", last.price))
                    .foregroundStyle(color).symbolSize(45)
            }
            if let selected {
                RuleMark(x: .value("Time", selected.x)).foregroundStyle(Color.inkSecondary.opacity(0.6))
                PointMark(x: .value("Time", selected.x), y: .value("Price", selected.price))
                    .foregroundStyle(color).symbolSize(70)
            }
        }
        .chartXScale(domain: series.domain)
        .chartYScale(domain: (low - pad)...(high + pad))
        .chartYAxis {
            AxisMarks(position: .trailing, values: .automatic(desiredCount: 3)) { value in
                AxisGridLine().foregroundStyle(Color.hairline.opacity(0.5))
                AxisValueLabel {
                    if let amount = value.as(Double.self) { Text(Fmt.axisPrice(amount)) }
                }
            }
        }
        .chartXAxis {
            AxisMarks(values: labels.map(\.x)) { value in
                AxisValueLabel {
                    if let x = value.as(Double.self), let label = labels.first(where: { abs($0.x - x) < 0.001 }) {
                        Text(label.text)
                    }
                }
            }
        }
        .chartXSelection(value: $selectedX)
        .frame(height: 200)
        .sensoryFeedback(.selection, trigger: selected?.time)
        .accessibilityLabel("\(symbol) price, \(range == .oneDay ? "today" : "past week")")
    }
}
