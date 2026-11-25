import LivermoreAPI
import LivermoreKit
import SwiftUI

/// The two views of a company: what its filings show, and what its price
/// is doing. Both end in the same decision.
enum CompanyTab: String, CaseIterable, Identifiable {
    case financials = "Financials"
    case price = "Price"

    var id: String { rawValue }
}

/// A segmented control in the app's own style.
struct CompanyTabBar: View {
    @Binding var selection: CompanyTab

    var body: some View {
        HStack(spacing: 4) {
            ForEach(CompanyTab.allCases) { tab in
                Button {
                    withAnimation(.easeInOut(duration: 0.18)) { selection = tab }
                } label: {
                    Text(tab.rawValue)
                        .font(.subheadline.weight(.semibold))
                        .lineLimit(1).minimumScaleFactor(0.8)
                        .frame(maxWidth: .infinity, minHeight: 36)
                        .foregroundStyle(tab == selection ? Color.white : .inkSecondary)
                        .background(tab == selection ? Color.brand : Color.clear, in: Capsule())
                        .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("company-tab-\(tab.id)")
                .accessibilityAddTraits(tab == selection ? .isSelected : [])
            }
        }
        .padding(3)
        .background(Color.well, in: Capsule())
        .sensoryFeedback(.selection, trigger: selection)
    }
}

// MARK: - Shared rows

struct RevenueSliceRow: View {
    let slice: RevenueSlice

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(slice.name).font(.subheadline)
                Spacer()
                Text(Fmt.percent(slice.share)).font(.subheadline.weight(.semibold).monospacedDigit())
            }
            GeometryReader { proxy in
                ZStack(alignment: .leading) {
                    Capsule().fill(Color.well)
                    Capsule().fill(Color.brand).frame(width: max(proxy.size.width * slice.share, 3))
                }
            }
            .frame(height: 5)
        }
        .accessibilityElement(children: .combine)
    }
}

/// Competitors as chips; tap one to open its page.
struct RivalChips: View {
    let rivals: [String]

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(rivals, id: \.self) { rival in
                    NavigationLink(value: rival) {
                        Text(rival)
                            .font(.subheadline.weight(.semibold).monospaced())
                            .padding(.horizontal, 12).padding(.vertical, 8)
                            .background(Color.well, in: Capsule())
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }
}

// MARK: - Price & signals

/// The setup in a headline, a tally and a sentence.
struct SetupCard: View {
    let read: TechnicalRead
    /// The read ends on the session under way, at the price now.
    var isLive = false

    private var tint: Color {
        switch read.trend {
        case .up: .gain
        case .down: .loss
        case .mixed: .caution
        }
    }

    var body: some View {
        Card {
            Text(isLive ? "The setup · price now, \(Fmt.tradingDay(read.asOf))" : "The setup · close of \(Fmt.tradingDay(read.asOf))").eyebrowStyle()
            HStack(spacing: 10) {
                Image(systemName: read.trend == .up ? "arrow.up.right" : read.trend == .down ? "arrow.down.right" : "arrow.left.and.right")
                    .font(.title3.weight(.bold)).foregroundStyle(.white)
                    .frame(width: 44, height: 44)
                    .background(tint, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                Text(read.headline).font(.title2.weight(.bold))
            }
            // One segment per signal: green leans up, red down, grey neither.
            HStack(spacing: 4) {
                ForEach(0..<read.upCount, id: \.self) { _ in Capsule().fill(Color.gain) }
                ForEach(0..<read.neutralCount, id: \.self) { _ in Capsule().fill(Color.inkSecondary.opacity(0.35)) }
                ForEach(0..<read.downCount, id: \.self) { _ in Capsule().fill(Color.loss) }
            }
            .frame(height: 8)
            .accessibilityHidden(true)
            Text(read.summary).font(.subheadline).foregroundStyle(.inkSecondary)
        }
        .accessibilityElement(children: .combine)
    }
}

/// Each signal: which way it leans, what it says, the number behind it.
struct SignalsCard: View {
    let read: TechnicalRead

    var body: some View {
        Card("Signals") {
            ForEach(Array(read.signals.enumerated()), id: \.element.id) { index, signal in
                if index > 0 { Divider() }
                SignalRow(signal: signal)
            }
            Divider()
            // Stretch is not a direction, so it sits apart from the tally.
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: "gauge.with.needle")
                    .font(.body.weight(.semibold)).foregroundStyle(stretchTint)
                    .frame(width: 30, height: 30)
                    .background(stretchTint.opacity(0.12), in: Circle())
                VStack(alignment: .leading, spacing: 2) {
                    Text("How stretched · RSI").font(.subheadline.weight(.semibold))
                    Text(stretchReading).font(.footnote).foregroundStyle(.inkSecondary)
                }
                Spacer(minLength: 8)
                Text(read.rsi.map { String(format: "%.0f", $0) } ?? "—")
                    .font(.subheadline.weight(.semibold).monospacedDigit()).foregroundStyle(stretchTint)
            }
            .accessibilityElement(children: .combine)
        }
    }

    private var stretchTint: Color {
        read.stretch == .normal ? .inkSecondary : .caution
    }

    private var stretchReading: String {
        switch read.stretch {
        case .oversold: "Below 30: it has fallen fast enough to count as oversold. Rebounds often start here; so do longer declines."
        case .overbought: "Above 70: it has risen fast enough to count as overbought. Pullbacks often start here; strong trends stay here for months."
        case .normal: "Between 30 and 70: neither oversold nor overbought."
        }
    }
}

private struct SignalRow: View {
    let signal: TechnicalSignal

    private var tint: Color {
        switch signal.lean {
        case .up: .gain
        case .down: .loss
        case .neutral: .inkSecondary
        }
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: signal.lean == .up ? "arrow.up" : signal.lean == .down ? "arrow.down" : "minus")
                .font(.footnote.weight(.bold)).foregroundStyle(tint)
                .frame(width: 30, height: 30)
                .background(tint.opacity(0.12), in: Circle())
            VStack(alignment: .leading, spacing: 2) {
                Text(signal.title).font(.subheadline.weight(.semibold))
                Text(signal.reading).font(.footnote).foregroundStyle(.inkSecondary)
            }
            Spacer(minLength: 8)
            Text(signal.value).font(.subheadline.weight(.semibold).monospacedDigit()).foregroundStyle(tint)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(signal.title): \(signal.reading)")
    }
}

/// Is the price high or low — against its own year, its recent returns, and
/// what the business earns.
struct PriceContextCard: View {
    let overview: CompanyOverview
    let read: TechnicalRead?
    let trend: CompanyTrend?
    let price: Double?

    var body: some View {
        let check = overview.financialCheck
        Card("The price in context") {
            if let read {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Past 52 weeks").eyebrowStyle()
                    GeometryReader { proxy in
                        ZStack(alignment: .leading) {
                            Capsule().fill(
                                LinearGradient(colors: [Color.loss.opacity(0.3), Color.well, Color.gain.opacity(0.3)],
                                               startPoint: .leading, endPoint: .trailing)
                            )
                            .frame(height: 6)
                            Circle().fill(Color.primary)
                                .overlay(Circle().stroke(Color.surface, lineWidth: 2))
                                .frame(width: 14, height: 14)
                                .offset(x: (proxy.size.width - 14) * read.rangePosition)
                        }
                        .frame(height: 14)
                    }
                    .frame(height: 14)
                    HStack {
                        Text("Low \(Fmt.price(read.low52Week))")
                        Spacer()
                        Text("\(Fmt.percent(abs(read.fromHigh))) below the high")
                        Spacer()
                        Text("High \(Fmt.price(read.high52Week))")
                    }
                    .font(.caption2.monospacedDigit()).foregroundStyle(.inkSecondary)
                }
                .accessibilityElement(children: .combine)
            }

            if let trend {
                HStack(spacing: 8) {
                    StatTile(label: "1 month", value: Fmt.percent(trend.perf1m, signed: true), tint: trend.perf1m?.changeColor)
                    StatTile(label: "3 months", value: Fmt.percent(trend.perf3m, signed: true), tint: trend.perf3m?.changeColor)
                    StatTile(label: "12 months", value: Fmt.percent(trend.perf12m, signed: true), tint: trend.perf12m?.changeColor)
                }
            }

            Divider()
            if let pe = check.peRatio { DetailRow("Price to earnings", Fmt.multiple(pe)) }
            if let yield = check.fcfYield { DetailRow("Free cash flow yield", Fmt.percent(yield)) }
            if let volatility = read?.volatility {
                DetailRow("Recent volatility, per year", Fmt.percent(volatility))
            }
            if let model = CashFlowModel(overview: overview, price: price), let value = model.valuePerShare, let price, price > 0 {
                NavigationLink {
                    ValuationView(overview: overview, price: price)
                } label: {
                    HStack {
                        VStack(alignment: .leading, spacing: 1) {
                            Text("What the cash flows imply").font(.subheadline.weight(.semibold))
                            Text("\(Fmt.price(value)) a share on last year's cash flow at \(Fmt.percent(model.growth)) growth — change the assumptions")
                                .font(.caption).foregroundStyle(.inkSecondary)
                        }
                        Spacer()
                        Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(.tertiary)
                    }
                    .padding(12)
                    .background(Color.well, in: RoundedRectangle(cornerRadius: Metrics.tileRadius, style: .continuous))
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        }
    }
}

// MARK: - Decide

/// The two ways to act on what the page shows: decide yourself, or pick a
/// rule and let it decide.
struct DecisionCard: View {
    @Environment(AppSession.self) private var session
    let symbol: String
    let read: TechnicalRead?
    let peers: [String]
    let onBuy: () -> Void
    let onSell: () -> Void

    var body: some View {
        let link = session.brokerageLink
        let holding = link.holding(of: symbol)
        let ideas = StrategyAdvisor.suggestions(for: read, symbol: symbol, peers: peers)

        Card("What do you want to do?") {
            VStack(alignment: .leading, spacing: 8) {
                Label("Decide yourself", systemImage: "person.fill").font(.subheadline.weight(.semibold))
                if link.canTrade {
                    if let holding {
                        Text("You hold \(Fmt.shares(holding.units)) shares at your broker.")
                            .font(.footnote).foregroundStyle(.inkSecondary)
                    }
                    HStack(spacing: 10) {
                        Button("Buy", action: onBuy).buttonStyle(PrimaryButtonStyle(tint: .gain))
                            .accessibilityIdentifier("decide-buy")
                        if holding != nil {
                            Button("Sell", action: onSell).buttonStyle(PrimaryButtonStyle(tint: .loss))
                                .accessibilityIdentifier("decide-sell")
                        }
                    }
                    Text("You set the size and see your broker's price before anything is sent.")
                        .font(.caption).foregroundStyle(.inkSecondary)
                } else if session.isSignedIn {
                    Text(link.isLinked
                        ? "Your broker is linked for viewing. Place the order in your brokerage app."
                        : "Link your broker to buy or sell \(symbol) from here.")
                        .font(.footnote).foregroundStyle(.inkSecondary)
                    if !link.isLinked {
                        NavigationLink { BrokerageView() } label: { Label("Link a brokerage", systemImage: "link") }
                            .buttonStyle(SecondaryButtonStyle())
                    }
                } else {
                    Text("Sign in from the Account tab and link your broker to buy or sell \(symbol) from here.")
                        .font(.footnote).foregroundStyle(.inkSecondary)
                }
            }

            Divider()

            VStack(alignment: .leading, spacing: 8) {
                Label("Let a rule decide", systemImage: "chart.xyaxis.line").font(.subheadline.weight(.semibold))
                Text("Test a strategy on \(symbol)'s history first. If it holds up, save it and Livermore tells you when its rule says to act.")
                    .font(.footnote).foregroundStyle(.inkSecondary)
                ForEach(ideas) { idea in
                    NavigationLink {
                        TemplateSetupView(template: idea.template, presetTickers: idea.tickers)
                    } label: {
                        HStack(alignment: .top, spacing: 12) {
                            CategoryIcon(category: idea.template.category, size: 38)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(idea.template.name).font(.subheadline.weight(.semibold))
                                Text(idea.why).font(.caption).foregroundStyle(.inkSecondary)
                            }
                            Spacer(minLength: 4)
                            Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(.tertiary)
                        }
                        .padding(12)
                        .background(Color.well, in: RoundedRectangle(cornerRadius: Metrics.tileRadius, style: .continuous))
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("idea-\(idea.template.id)")
                }
                NavigationLink { TemplateGalleryView(presetTicker: symbol) } label: {
                    Text("Browse all strategies").font(.subheadline.weight(.semibold))
                }
            }

            Text("Signals describe the past year of prices. They are not a recommendation. Research tool, not advice.")
                .font(.caption2).foregroundStyle(.inkSecondary)
        }
    }
}
