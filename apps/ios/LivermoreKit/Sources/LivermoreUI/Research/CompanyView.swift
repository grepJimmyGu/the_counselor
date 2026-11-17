import Charts
import LivermoreAPI
import LivermoreKit
import SwiftUI

/// One company: price, the three scores, the price trend, fundamentals,
/// business and market position.
struct CompanyView: View {
    @Environment(AppSession.self) private var session
    let symbol: String

    private enum Phase {
        case loading
        case loaded(CompanyOverview)
        case failed(ResearchError)
    }

    @State private var phase: Phase = .loading
    @State private var trend: CompanyTrend?
    @State private var trendFailed = false
    @State private var isTrading = false
    @State private var tradeSide: TradeSide = .buy

    private enum TradeSide: String, CaseIterable, Identifiable {
        case buy = "Buy"
        case sell = "Sell"
        var id: String { rawValue }
    }

    var body: some View {
        Group {
            switch phase {
            case .loading:
                ProgressView("Loading \(symbol)…")
            case .failed(let error):
                failure(error)
            case .loaded(let overview):
                content(overview)
            }
        }
        .navigationTitle(symbol)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .liveQuotes([symbol])
        .sheet(isPresented: $isTrading) { tradeSheet }
        .task(id: session.isSignedIn) {
            // Whether to offer a trade depends on the brokerage link, which a
            // signed-in user may never have opened the Actions tab to load.
            if session.isSignedIn, session.brokerageLink.status == nil { await session.brokerageLink.refresh() }
        }
        .task(id: symbol) {
            // `.task` runs again every time this screen reappears — including
            // on the way back from Sentiment or Supply chain. Reloading there
            // would throw away the page and the scroll position, and repeat
            // the slowest request in the app.
            if case .loaded(let overview) = phase, overview.symbol == symbol { return }
            await load()
        }
    }

    // The three calls are independent, so they run together and each part of
    // the page appears as its own data arrives. The overview is the slow one.
    private func load() async {
        phase = .loading
        trend = nil
        trendFailed = false
        let research = session.research
        async let trendResult: CompanyTrend? = try? research.trend(symbol)

        do throws(ResearchError) {
            phase = .loaded(try await research.overview(symbol))
        } catch {
            phase = .failed(error)
        }
        trend = await trendResult
        trendFailed = trend == nil
    }

    /// Buy, or — when the broker shows a holding — choose between buying
    /// more and selling it.
    @ViewBuilder
    private var tradeSheet: some View {
        if let holding = session.brokerageLink.holding(of: symbol) {
            VStack(spacing: 0) {
                Picker("Side", selection: $tradeSide) {
                    ForEach(TradeSide.allCases) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.segmented)
                .padding()
                OrderTicketView(
                    symbol: symbol,
                    side: tradeSide == .sell ? .sell(holding: holding, suggested: nil) : .buy(suggestedDollars: nil)
                )
                // A different side is a different order: start the ticket over.
                .id(tradeSide)
            }
        } else {
            OrderTicketView(symbol: symbol, side: .buy(suggestedDollars: nil))
        }
    }

    @ViewBuilder
    private func failure(_ error: ResearchError) -> some View {
        if case .upgradeRequired = error {
            ContentUnavailableView {
                Label("Not in your plan", systemImage: "lock")
            } description: {
                Text(error.message)
            }
        } else {
            ContentUnavailableView {
                Label("Couldn't load \(symbol)", systemImage: "exclamationmark.triangle")
            } description: {
                Text(error.message)
            } actions: {
                Button("Try again") { Task { await load() } }
            }
        }
    }

    private func content(_ overview: CompanyOverview) -> some View {
        let metrics = StockMetrics(overview: overview, trend: trend)
        let health = StockScoring.health(metrics)
        let valuation = StockScoring.valuation(metrics)
        let trendScore = StockScoring.trend(metrics)

        return ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                CompanyHeader(overview: overview, quote: session.quotes.quotes[symbol.uppercased()], trend: trend)

                Card("Fundamental analysis") {
                    ScoreRow(title: "Asset health", question: "Is the business fundamentally healthy?", score: health)
                    Divider()
                    ScoreRow(title: "Valuation", question: "Is the asset cheap, fair or expensive?", score: valuation)
                    Divider()
                    if trend != nil {
                        ScoreRow(title: "Market trend", question: "Is the market moving for or against it?", score: trendScore)
                        Divider()
                        OverallRow(score: StockScoring.overall(health: health, valuation: valuation, trend: trendScore))
                    } else if trendFailed {
                        Text("Market trend is unavailable for this company, so there is no overall score.")
                            .font(.footnote).foregroundStyle(.secondary)
                    } else {
                        HStack { ProgressView(); Text("Loading market trend…").font(.footnote).foregroundStyle(.secondary) }
                    }
                }

                if let trend {
                    TrendCard(trend: trend)
                }

                FundamentalsCard(check: overview.financialCheck)
                BusinessCard(map: overview.businessMap)
                MarketPositionCard(position: overview.marketPosition)

                Card("More on \(overview.symbol)") {
                    NavigationLink {
                        TemplateGalleryView(presetTicker: overview.symbol)
                    } label: {
                        MoreRow(title: "Test a strategy on \(overview.symbol)", systemImage: "chart.xyaxis.line")
                    }
                    Divider()
                    if session.brokerageLink.canTrade {
                        Button {
                            isTrading = true
                        } label: {
                            MoreRow(
                                title: session.brokerageLink.holding(of: overview.symbol) == nil
                                    ? "Buy \(overview.symbol) at your broker"
                                    : "Trade \(overview.symbol) at your broker",
                                systemImage: "arrow.left.arrow.right.circle"
                            )
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("trade-at-broker")
                        Divider()
                    }
                    NavigationLink {
                        SentimentView(symbol: overview.symbol)
                    } label: {
                        MoreRow(title: "News & sentiment", systemImage: "newspaper")
                    }
                    Divider()
                    NavigationLink {
                        SupplyChainView(symbol: overview.symbol)
                    } label: {
                        MoreRow(title: "Supply chain", systemImage: "point.3.connected.trianglepath.dotted")
                    }
                }

                if let disclaimer = overview.disclaimer {
                    Text(disclaimer).font(.caption).foregroundStyle(.secondary)
                }
            }
            .padding()
        }
        .background(Color.groupedBackground)
    }
}

// MARK: - Header

private struct CompanyHeader: View {
    let overview: CompanyOverview
    let quote: LiveQuote?
    let trend: CompanyTrend?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            // Date first and legible: what day these numbers describe.
            if let asOf = overview.asOfDate {
                Text("AS OF \(asOf)")
                    .font(.caption2.weight(.semibold))
                    .tracking(0.8)
                    .foregroundStyle(.secondary)
            }
            Text(overview.name).font(.title2.weight(.semibold))
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                LivePriceText(price: quote?.price ?? trend?.latestPrice ?? overview.price)
                    .font(.title.weight(.bold))
                if let quote {
                    Text("\(Fmt.signedMoney(quote.change)) (\(Fmt.percentPoints(quote.changePercent)))")
                        .font(.subheadline.weight(.semibold).monospacedDigit())
                        .foregroundStyle(quote.changePercent.changeColor)
                }
            }
            if quote != nil {
                QuoteFreshnessLabel()
                if let low = quote?.dayLow, let high = quote?.dayHigh {
                    Text("Today \(Fmt.price(low)) – \(Fmt.price(high))")
                        .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                }
            }
            Text([overview.sector, overview.industry, overview.exchange].compactMap { $0 }.joined(separator: " · "))
                .font(.subheadline).foregroundStyle(.secondary)
            if let cap = overview.marketCap {
                Text("\(Fmt.money(cap)) market cap").font(.subheadline).foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - Scores

private struct ScoreRow: View {
    let title: String
    let question: String
    let score: Int

    var body: some View {
        let status = StockScoring.status(score)
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(title).font(.subheadline.weight(.semibold))
                Spacer()
                Text(status.label.uppercased())
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(status.color)
            }
            Text(question).font(.caption).foregroundStyle(.secondary)
            HStack(spacing: 10) {
                Text("\(score)").font(.title2.weight(.bold).monospacedDigit()).foregroundStyle(status.color)
                Text("/ 100").font(.caption).foregroundStyle(.secondary)
                ProgressView(value: Double(score), total: 100).tint(status.color)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(title): \(score) out of 100, \(status.label)")
    }
}

private struct OverallRow: View {
    let score: Int

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text("Overall").font(.subheadline.weight(.semibold))
                Text(StockScoring.label(forOverall: score)).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            Text("\(score)").font(.title.weight(.bold).monospacedDigit())
            Text("/ 100").font(.caption).foregroundStyle(.secondary)
        }
    }
}

// MARK: - Trend

private struct TrendCard: View {
    let trend: CompanyTrend

    var body: some View {
        let points = trend.pricePoints
        Card("Price, last 90 days") {
            if points.count > 1 {
                let low = points.map(\.price).min() ?? 0
                let high = points.map(\.price).max() ?? 1
                Chart(points) { point in
                    LineMark(x: .value("Date", point.date), y: .value("Price", point.price))
                        .interpolationMethod(.monotone)
                }
                .chartYScale(domain: (low * 0.98)...(high * 1.02))
                .frame(height: 160)
                .accessibilityLabel("Closing price over the last 90 days")
            }
            Grid(horizontalSpacing: 12, verticalSpacing: 10) {
                GridRow {
                    Stat("1 month", Fmt.percent(trend.perf1m, signed: true), tint: trend.perf1m?.changeColor)
                    Stat("3 months", Fmt.percent(trend.perf3m, signed: true), tint: trend.perf3m?.changeColor)
                }
                GridRow {
                    Stat("6 months", Fmt.percent(trend.perf6m, signed: true), tint: trend.perf6m?.changeColor)
                    Stat("12 months", Fmt.percent(trend.perf12m, signed: true), tint: trend.perf12m?.changeColor)
                }
                GridRow {
                    Stat("vs 50-day average", Fmt.percent(trend.priceVsMa50, signed: true), tint: trend.priceVsMa50?.changeColor)
                    Stat("vs 200-day average", Fmt.percent(trend.priceVsMa200, signed: true), tint: trend.priceVsMa200?.changeColor)
                }
                GridRow {
                    Stat("vs S&P 500, 3 months", Fmt.percent(trend.rsVsSpy3m, signed: true), tint: trend.rsVsSpy3m?.changeColor)
                    Stat("vs S&P 500, 12 months", Fmt.percent(trend.rsVsSpy12m, signed: true), tint: trend.rsVsSpy12m?.changeColor)
                }
            }
            if let date = trend.latestDate {
                Text("Prices through \(date)").font(.caption).foregroundStyle(.secondary)
            }
        }
    }
}

// MARK: - Fundamentals

private struct FundamentalsCard: View {
    let check: Components.Schemas.FinancialCheckSection

    var body: some View {
        Card("Financials") {
            ForEach(summaries, id: \.title) { item in
                VStack(alignment: .leading, spacing: 2) {
                    Text(item.title).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    Text(item.text).font(.subheadline)
                }
            }
            Divider()
            Grid(horizontalSpacing: 12, verticalSpacing: 10) {
                GridRow {
                    Stat("Revenue growth", Fmt.percent(check.revenueYoy, signed: true))
                    Stat("Gross margin", Fmt.percent(check.grossMargin))
                }
                GridRow {
                    Stat("Operating margin", Fmt.percent(check.operatingMargin))
                    Stat("Free cash flow", Fmt.money(check.freeCashFlow))
                }
                GridRow {
                    Stat("P/E", Fmt.multiple(check.peRatio))
                    Stat("EV / EBITDA", Fmt.multiple(check.evEbitda))
                }
                GridRow {
                    Stat("FCF yield", Fmt.percent(check.fcfYield))
                    Stat("Net debt", Fmt.money(check.netDebt))
                }
            }
            ForEach(check.warnings ?? [], id: \.self) { warning in
                Label(warning, systemImage: "exclamationmark.triangle").font(.footnote).foregroundStyle(.orange)
            }
        }
    }

    private var summaries: [(title: String, text: String)] {
        [
            ("Growth", check.growthSummary), ("Profitability", check.profitabilitySummary),
            ("Cash flow", check.cashFlowSummary), ("Balance sheet", check.balanceSheetSummary),
            ("Valuation", check.valuationSummary),
        ].compactMap { title, text in text.map { (title, $0) } }
    }
}

// MARK: - Business and market position

private struct BusinessCard: View {
    let map: Components.Schemas.BusinessMapSection

    var body: some View {
        let rows: [(String, String?)] = [
            ("What it does", map.oneLineSummary), ("Role in the value chain", map.primaryValueChainRole),
            ("How it makes money", map.revenueModel), ("Margins", map.marginImplication),
            ("Pricing power", map.pricingPowerImplication), ("Cyclicality", map.cyclicalityImplication),
        ]
        let shown = rows.compactMap { title, text in text.map { (title, $0) } }
        if !shown.isEmpty {
            Card("Business") {
                ForEach(shown, id: \.0) { title, text in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(title).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                        Text(text).font(.subheadline)
                    }
                }
                SourceNotes(notes: map.sourceNotes)
            }
        }
    }
}

private struct MarketPositionCard: View {
    let position: Components.Schemas.MarketPositionSection

    var body: some View {
        Card("Market position") {
            if let category = position.marketCategory {
                Text(category).font(.subheadline.weight(.semibold))
            }
            let tags = [position.competitivePositionLabel, position.marketGrowthLabel.map { "\($0) market" }].compactMap { $0 }
            if !tags.isEmpty {
                Text(tags.joined(separator: " · ")).font(.caption).foregroundStyle(.secondary)
            }
            if let notes = position.marketShareNotes {
                Text(notes).font(.subheadline)
            }
            BulletList(title: "Growth drivers", items: position.keyGrowthDrivers)
            BulletList(title: "Risks", items: position.keyRisks)
            let rivals = (position.keyCompetitors ?? []).filter { !$0.contains(".") }
            if !rivals.isEmpty {
                Text("Competitors").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack {
                        ForEach(rivals, id: \.self) { rival in
                            NavigationLink(value: rival) {
                                Text(rival).font(.footnote.monospaced().weight(.semibold))
                                    .padding(.horizontal, 10).padding(.vertical, 6)
                                    .background(.quaternary, in: Capsule())
                            }
                        }
                    }
                }
            }
            SourceNotes(notes: position.sourceNotes)
        }
    }
}

// MARK: - Building blocks

struct Card<Content: View>: View {
    let title: String
    @ViewBuilder let content: Content

    init(_ title: String, @ViewBuilder content: () -> Content) {
        self.title = title
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(title).font(.headline)
            content
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 14))
    }
}

struct Stat: View {
    let label: String
    let value: String
    let tint: Color?

    init(_ label: String, _ value: String, tint: Color? = nil) {
        self.label = label
        self.value = value
        self.tint = tint
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.caption).foregroundStyle(.secondary)
            Text(value).font(.subheadline.weight(.semibold).monospacedDigit()).foregroundStyle(tint ?? .primary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct BulletList: View {
    let title: String
    let items: [String]?

    var body: some View {
        if let items, !items.isEmpty {
            VStack(alignment: .leading, spacing: 4) {
                Text(title).font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                ForEach(items, id: \.self) { item in
                    Text("• \(item)").font(.subheadline)
                }
            }
        }
    }
}

private struct SourceNotes: View {
    let notes: [String]?

    var body: some View {
        if let notes, !notes.isEmpty {
            Text("Source: " + notes.joined(separator: "; ")).font(.caption2).foregroundStyle(.tertiary)
        }
    }
}

private struct MoreRow: View {
    let title: String
    let systemImage: String

    var body: some View {
        HStack {
            Label(title, systemImage: systemImage)
            Spacer()
            Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(.tertiary)
        }
        .contentShape(Rectangle())
    }
}

extension Color {
    static var groupedBackground: Color {
        #if os(iOS)
        Color(uiColor: .systemGroupedBackground)
        #else
        Color(nsColor: .windowBackgroundColor)
        #endif
    }

    static var cardBackground: Color {
        #if os(iOS)
        Color(uiColor: .secondarySystemGroupedBackground)
        #else
        Color(nsColor: .controlBackgroundColor)
        #endif
    }
}
