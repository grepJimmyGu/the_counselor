import Charts
import LivermoreAPI
import LivermoreKit
import SwiftUI

/// Where the quarterly filing analysis stands for a company.
enum FilingsState {
    case loading
    case loaded(FilingAnalysis)
    /// No analysis, with the reason when there is one worth showing.
    case unavailable(String?)
}

// MARK: - Latest quarter

/// The latest quarterly report in four numbers, each against last quarter
/// and a year ago, with the filing it came from.
struct LatestQuarterCard: View {
    let analysis: FilingAnalysis

    private var headline: [FilingMetric] {
        // Operating margin where the company reports one; net margin for
        // those (banks, insurers) that do not.
        let keys = ["revenue", analysis.metric("operating_margin") != nil ? "operating_margin" : "net_margin",
                    "eps_diluted", analysis.metric("free_cash_flow") != nil ? "free_cash_flow" : "net_income"]
        return keys.compactMap { analysis.metric($0) }
    }

    var body: some View {
        let latest = analysis.latest
        Card {
            VStack(alignment: .leading, spacing: 4) {
                Text([latest.form, latest.filed.map { "filed \(FilingDate.long($0))" }].compactMap { $0 }.joined(separator: " · "))
                    .eyebrowStyle()
                Text(latest.label).font(.title2.weight(.bold))
                Text("Quarter ended \(FilingDate.long(latest.periodEnd))").font(.subheadline).foregroundStyle(.inkSecondary)
            }
            LazyVGrid(columns: [GridItem(.flexible(), spacing: 8), GridItem(.flexible(), spacing: 8)], spacing: 8) {
                ForEach(headline, id: \.key) { metric in HeadlineTile(metric: metric) }
            }
            if let link = latest.filingUrl.flatMap(URL.init(string:)) {
                Link(destination: link) {
                    Label("Open the \(latest.form ?? "filing") on sec.gov", systemImage: "doc.text.magnifyingglass")
                        .font(.subheadline.weight(.semibold))
                }
                .accessibilityIdentifier("open-filing")
            }
        }
    }
}

private struct HeadlineTile: View {
    let metric: FilingMetric

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(metric.label).font(.caption).foregroundStyle(.inkSecondary).lineLimit(1).minimumScaleFactor(0.75)
            Text(metric.formatted(metric.latest)).font(.title3.weight(.semibold).monospacedDigit())
                .lineLimit(1).minimumScaleFactor(0.7)
            ChangeLine(metric: metric, change: metric.changeYoy, against: "vs a year ago")
            ChangeLine(metric: metric, change: metric.changeQoq, against: "vs last quarter")
        }
        .frame(maxWidth: .infinity, minHeight: 84, alignment: .topLeading)
        .padding(12)
        .background(Color.well, in: RoundedRectangle(cornerRadius: Metrics.tileRadius, style: .continuous))
        .accessibilityElement(children: .combine)
    }
}

/// "+17.9% vs last quarter", coloured by whether that direction is the good one.
struct ChangeLine: View {
    let metric: FilingMetric
    let change: Double?
    let against: String

    var body: some View {
        if let text = metric.formattedChange(change) {
            let improved = metric.isImprovement(change)
            HStack(spacing: 4) {
                Text(text).fontWeight(.semibold)
                    .foregroundStyle(improved == true ? Color.gain : improved == false ? .loss : .inkSecondary)
                Text(against).foregroundStyle(.inkSecondary)
            }
            .font(.caption2.monospacedDigit())
            .lineLimit(1).minimumScaleFactor(0.8)
        }
    }
}

// MARK: - Findings

/// The things in the quarter that moved enough to state, watch items first.
struct FindingsCard: View {
    let analysis: FilingAnalysis

    private func count(_ severity: String) -> Int {
        analysis.findings.filter { $0.severity == severity }.count
    }

    var body: some View {
        Card("What changed this quarter") {
            if analysis.findings.isEmpty {
                Text("Nothing moved past the thresholds this quarter: growth, margins, cash conversion and the balance sheet are all close to where they were.")
                    .font(.subheadline).foregroundStyle(.inkSecondary)
            } else {
                HStack(spacing: 6) {
                    if count("watch") > 0 { Tag("\(count("watch")) to watch", tint: .caution, systemImage: "exclamationmark.triangle.fill") }
                    if count("good") > 0 { Tag("\(count("good")) improved", tint: .gain, systemImage: "checkmark.circle.fill") }
                    if count("info") > 0 { Tag("\(count("info")) to note", tint: .inkSecondary, systemImage: "info.circle.fill") }
                }
                ForEach(Array(analysis.findings.enumerated()), id: \.offset) { index, finding in
                    if index > 0 { Divider() }
                    FindingRow(finding: finding)
                }
            }
            Text("Each line is arithmetic on the figures in the filing. None is a forecast.")
                .font(.caption2).foregroundStyle(.inkSecondary)
        }
    }
}

private struct FindingRow: View {
    let finding: FilingFinding

    private var tint: Color {
        switch finding.severity {
        case "watch": .caution
        case "good": .gain
        default: .inkSecondary
        }
    }

    private var symbol: String {
        switch finding.severity {
        case "watch": "exclamationmark.triangle.fill"
        case "good": "checkmark.circle.fill"
        default: "info.circle.fill"
        }
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: symbol)
                .font(.footnote.weight(.bold)).foregroundStyle(tint)
                .frame(width: 30, height: 30)
                .background(tint.opacity(0.12), in: Circle())
            VStack(alignment: .leading, spacing: 3) {
                Text(finding.title).font(.subheadline.weight(.semibold))
                Text(finding.detail).font(.footnote).foregroundStyle(.inkSecondary)
            }
        }
        .accessibilityElement(children: .combine)
    }
}

// MARK: - Metric trends

/// One group of metrics ("Cash"), each as a row: the run of quarters as
/// bars, the latest figure, and how it has moved in a year.
struct MetricGroupCard: View {
    let name: String
    let metrics: [FilingMetric]
    let analysis: FilingAnalysis

    @State private var selected: FilingMetric?

    var body: some View {
        Card(name) {
            ForEach(Array(metrics.enumerated()), id: \.element.key) { index, metric in
                if index > 0 { Divider() }
                Button {
                    selected = metric
                } label: {
                    MetricRow(metric: metric, series: analysis.series(metric.key))
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("metric-\(metric.key)")
            }
        }
        .sheet(item: $selected) { metric in
            MetricDetailView(metric: metric, analysis: analysis)
        }
    }
}

extension Components.Schemas.FilingMetric: Identifiable {
    public var id: String { key }
}

private struct MetricRow: View {
    let metric: FilingMetric
    let series: [Double?]

    var body: some View {
        HStack(alignment: .center, spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text(metric.label).font(.subheadline).lineLimit(2)
                if let note = metric.shortNote {
                    Text(note).font(.caption2).foregroundStyle(.inkSecondary).lineLimit(2)
                }
            }
            Spacer(minLength: 4)
            MiniBars(values: series, better: metric.better)
                .frame(width: 58, height: 26)
            VStack(alignment: .trailing, spacing: 2) {
                Text(metric.formatted(metric.latest)).font(.subheadline.weight(.semibold).monospacedDigit())
                if let text = metric.formattedChange(metric.changeYoy ?? metric.changeQoq) {
                    let improved = metric.isImprovement(metric.changeYoy ?? metric.changeQoq)
                    Text(text + (metric.changeYoy == nil ? " q/q" : " y/y"))
                        .font(.caption2.weight(.semibold).monospacedDigit())
                        .foregroundStyle(improved == true ? Color.gain : improved == false ? .loss : .inkSecondary)
                }
            }
            .frame(minWidth: 84, alignment: .trailing)
            Image(systemName: "chevron.right").font(.caption2.weight(.semibold)).foregroundStyle(.tertiary)
        }
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}

/// A run of quarters as small bars, the latest one in the brand colour.
/// Bars grow from zero; a negative quarter hangs below the line.
struct MiniBars: View {
    let values: [Double?]
    let better: String

    var body: some View {
        GeometryReader { proxy in
            let known = values.compactMap { $0 }
            let top = max(known.max() ?? 0, 0)
            let bottom = min(known.min() ?? 0, 0)
            let span = max(top - bottom, .leastNonzeroMagnitude)
            let width = proxy.size.width / CGFloat(max(values.count, 1))
            let zero = proxy.size.height * CGFloat(top / span)
            ForEach(Array(values.enumerated()), id: \.offset) { index, value in
                if let value {
                    let height = max(proxy.size.height * CGFloat(abs(value) / span), 1.5)
                    RoundedRectangle(cornerRadius: 1.5, style: .continuous)
                        .fill(index == values.count - 1 ? Color.brand : Color.inkSecondary.opacity(0.35))
                        .frame(width: max(width - 2, 1), height: height)
                        .position(x: width * (CGFloat(index) + 0.5), y: value >= 0 ? zero - height / 2 : zero + height / 2)
                }
            }
        }
        .accessibilityHidden(true)
    }
}

/// One metric across the quarters: the chart, every figure, and the filing
/// each came from.
struct MetricDetailView: View {
    @Environment(\.dismiss) private var dismiss
    let metric: FilingMetric
    let analysis: FilingAnalysis

    private struct Bar: Identifiable {
        let label: String
        let value: Double
        let isLatest: Bool
        var id: String { label }
    }

    var body: some View {
        let quarters = analysis.quarters
        let bars = quarters.enumerated().compactMap { index, quarter in
            quarter.value(metric.key).map { Bar(label: quarter.shortLabel, value: $0, isLatest: index == quarters.count - 1) }
        }
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Metrics.sectionSpacing) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("\(analysis.symbol) · \(metric.group)").eyebrowStyle()
                        Text(metric.formatted(metric.latest)).font(.hero)
                        ChangeLine(metric: metric, change: metric.changeYoy, against: "vs a year ago")
                        ChangeLine(metric: metric, change: metric.changeQoq, against: "vs last quarter")
                        if let note = metric.note { Text(note).font(.subheadline).foregroundStyle(.inkSecondary) }
                    }
                    .padding(.horizontal, 4)

                    Card {
                        Chart(bars) { bar in
                            BarMark(x: .value("Quarter", bar.label), y: .value(metric.label, bar.value), width: .ratio(0.6))
                                .foregroundStyle(bar.isLatest ? Color.brand : Color.inkSecondary.opacity(0.45))
                                .cornerRadius(3)
                        }
                        .chartXScale(domain: bars.map(\.label))
                        .chartYAxis {
                            AxisMarks(position: .trailing, values: .automatic(desiredCount: 4)) { value in
                                AxisGridLine().foregroundStyle(Color.hairline.opacity(0.5))
                                AxisValueLabel {
                                    if let amount = value.as(Double.self) { Text(metric.formatted(amount)) }
                                }
                            }
                        }
                        .chartXAxis {
                            AxisMarks { _ in AxisValueLabel().font(.system(size: 9)) }
                        }
                        .frame(height: 190)
                        .accessibilityLabel("\(metric.label) by quarter")
                    }

                    Card("Every quarter") {
                        ForEach(Array(quarters.reversed().enumerated()), id: \.offset) { index, quarter in
                            if index > 0 { Divider() }
                            HStack(alignment: .firstTextBaseline) {
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(quarter.label).font(.subheadline.weight(.semibold))
                                    Text([quarter.form, quarter.filed.map { "filed \(FilingDate.long($0))" }].compactMap { $0 }.joined(separator: " · "))
                                        .font(.caption2).foregroundStyle(.inkSecondary)
                                }
                                Spacer()
                                Text(metric.formatted(quarter.value(metric.key)))
                                    .font(.subheadline.monospacedDigit())
                                    .foregroundStyle(quarter.value(metric.key) == nil ? Color.inkSecondary : .primary)
                            }
                        }
                    }

                    Text(Self.explanation(metric.key))
                        .font(.caption).foregroundStyle(.inkSecondary).padding(.horizontal, 4)
                }
                .padding(Metrics.screenPadding)
            }
            .screenBackground()
            .navigationTitle(metric.label)
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
        }
    }

    /// What the figure is and how it is worked out — a definition, not a view.
    static func explanation(_ key: String) -> String {
        switch key {
        case "revenue_growth_yoy": "Revenue against the same quarter a year earlier."
        case "gross_margin": "Gross profit as a share of revenue: what is left after the direct cost of what was sold."
        case "operating_margin": "Operating income as a share of revenue: what is left after running the business, before interest and tax."
        case "net_margin": "Net income as a share of revenue."
        case "operating_expenses": "Research and development plus selling, general and administrative expense."
        case "free_cash_flow": "Operating cash flow less capital spending. Cash flow statements are year-to-date, so a quarter is the year so far less the quarters before it."
        case "free_cash_flow_margin": "Free cash flow as a share of revenue."
        case "cash_conversion": "Operating cash flow divided by net income. Below 1, less cash came in than the profit reported."
        case "cash_and_investments": "Cash plus marketable securities, short- and long-term."
        case "net_cash": "Cash and investments less debt. Negative means net debt."
        case "days_sales_outstanding": "Receivables divided by a day's revenue: how many days of sales have been billed and not yet collected."
        case "days_inventory": "Inventory divided by a day's cost of sales: how many days of sales the inventory on hand would cover."
        case "diluted_shares": "Weighted average diluted shares. The 10-K gives only the year's average, so the fourth quarter is four times that less the other three."
        case "returned_to_shareholders": "Cash paid for share repurchases plus dividends."
        case "stock_compensation_share": "Stock-based compensation as a share of revenue."
        case "eps_diluted": "Diluted earnings per share. The fourth quarter is the year's figure less the first three quarters'."
        default: "As reported in the company's 10-Q and 10-K filings, from the SEC's XBRL data."
        }
    }
}

// MARK: - Dates

/// Filing dates arrive as "2026-08-26" and are shown as "Aug 26, 2026".
enum FilingDate {
    static func long(_ iso: String) -> String {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd"
        guard let date = formatter.date(from: String(iso.prefix(10))) else { return iso }
        return Fmt.tradingDay(date)
    }
}
