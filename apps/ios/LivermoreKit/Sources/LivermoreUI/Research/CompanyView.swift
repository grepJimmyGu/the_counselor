import Charts
import LivermoreAPI
import LivermoreKit
import SwiftUI

/// One company, top to bottom in the order an investor asks: what is it
/// worth now, how has it moved, is it any good, what are the numbers, what
/// does it do, who is it up against.
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
    @State private var tab: CompanyTab = .financials
    @State private var filings: FilingsState = .loading
    /// The stock's and the benchmark's daily closes, once fetched: the chart
    /// and the signals both read these.
    @State private var history: (stock: [DailyClose], benchmark: [DailyClose])?
    @State private var historyFailed = false

    private enum TradeSide: String, CaseIterable, Identifiable {
        case buy = "Buy"
        case sell = "Sell"
        var id: String { rawValue }
    }

    private var quote: LiveQuote? { session.quotes.quotes[symbol.uppercased()] }

    var body: some View {
        Group {
            switch phase {
            case .loading:
                CompanySkeleton()
            case .failed(let error):
                failure(error)
            case .loaded(let overview):
                content(overview)
            }
        }
        .screenBackground()
        .navigationTitle(symbol)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .toolbar {
            if case .loaded(let overview) = phase {
                ToolbarItem(placement: .primaryAction) {
                    let following = session.watchlist.contains(symbol)
                    Button {
                        session.watchlist.toggle(symbol, name: overview.name)
                    } label: {
                        Image(systemName: following ? "star.fill" : "star")
                    }
                    .tint(following ? .caution : .brand)
                    .sensoryFeedback(.selection, trigger: following)
                    .accessibilityLabel(following ? "Remove from watchlist" : "Add to watchlist")
                    .accessibilityIdentifier("toggle-watchlist")
                }
            }
        }
        .liveQuotes([symbol])
        .sheet(isPresented: $isTrading) { tradeSheet }
        .task(id: session.isSignedIn) {
            // Whether to offer a trade depends on the brokerage link, which a
            // signed-in user may never have opened the Actions tab to load.
            if session.isSignedIn, session.brokerageLink.status == nil { await session.brokerageLink.refresh() }
        }
        .task(id: symbol) { await loadHistory() }
        .task(id: symbol) { await loadFilings() }
        .task(id: symbol) {
            // `.task` runs again every time this screen reappears — including
            // on the way back from Sentiment or Supply chain. Reloading there
            // would throw away the page and the scroll position, and repeat
            // the slowest request in the app.
            if case .loaded(let overview) = phase, overview.symbol == symbol { return }
            await load()
        }
    }

    // The calls are independent, so they run together and each part of the
    // page appears as its own data arrives. The overview is the slow one.
    private func load() async {
        trendFailed = false
        let research = session.research
        // A company looked at in the last few minutes is shown from memory:
        // no skeleton, and no request for an answer that cannot have changed.
        let recentTrend = session.recentTrends.value(for: symbol)
        trend = recentTrend
        async let trendResult: CompanyTrend? = recentTrend == nil ? try? research.trend(symbol) : recentTrend

        if let recent = session.recentOverviews.value(for: symbol) {
            phase = .loaded(recent)
            session.watchlist.viewed(symbol, name: recent.name)
        } else {
            phase = .loading
            do throws(ResearchError) {
                let overview = try await research.overview(symbol)
                session.recentOverviews.store(overview, for: symbol)
                phase = .loaded(overview)
                session.watchlist.viewed(symbol, name: overview.name)
            } catch {
                phase = .failed(error)
            }
        }
        trend = await trendResult
        trendFailed = trend == nil
        if recentTrend == nil, let trend { session.recentTrends.store(trend, for: symbol) }
    }

    private func loadFilings() async {
        if case .loaded(let analysis) = filings, analysis.symbol == symbol.uppercased() { return }
        if let recent = session.recentFilings.value(for: symbol) {
            filings = .loaded(recent)
            return
        }
        filings = .loading
        do throws(ResearchError) {
            let analysis = try await session.research.filings(symbol)
            session.recentFilings.store(analysis, for: symbol)
            filings = .loaded(analysis)
        } catch {
            // The backend explains a company it cannot read (a foreign filer,
            // one the SEC does not list); anything else is just "not now".
            if case .unavailable(let reason) = error, !reason.isEmpty, reason != "Not Found" {
                filings = .unavailable(reason)
            } else {
                filings = .unavailable(nil)
            }
        }
    }

    private func loadHistory() async {
        guard history == nil else { return }
        do {
            // The benchmark is shared by every chart and fetched once per
            // launch; if only it fails the price still shows.
            async let benchmark = try? session.priceHistory.closes(for: PriceHistory.benchmarkSymbol)
            let stock = try await session.priceHistory.closes(for: symbol)
            history = (stock, await benchmark ?? [])
            historyFailed = false
        } catch {
            historyFailed = true
        }
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

    private func decision(_ overview: CompanyOverview, _ read: TechnicalRead?) -> some View {
        DecisionCard(
            symbol: symbol, read: read, peers: overview.marketPosition.keyCompetitors ?? [],
            onBuy: {
                tradeSide = .buy
                isTrading = true
            },
            onSell: {
                tradeSide = .sell
                isTrading = true
            }
        )
    }

    /// What the filings show: the latest quarter, what changed in it, and
    /// every metric's run — then how the market prices it.
    @ViewBuilder
    private func financials(_ overview: CompanyOverview, _ price: Double?) -> some View {
        switch filings {
        case .loading:
            Card { SkeletonBlock(height: 22, width: 160); SkeletonBlock(height: 150) }
            Card { SkeletonBlock(); SkeletonBlock(); SkeletonBlock() }
        case .loaded(let analysis):
            LatestQuarterCard(analysis: analysis)
            FindingsCard(analysis: analysis)
            ForEach(analysis.metricGroups, id: \.name) { group in
                MetricGroupCard(name: group.name, metrics: group.metrics, analysis: analysis)
            }
        case .unavailable(let reason):
            Card {
                Notice(
                    text: reason ?? "The quarter-by-quarter reading of \(overview.symbol)'s filings isn't available right now. Annual figures are below.",
                    systemImage: "doc.text.magnifyingglass"
                )
            }
            // The annual figures the overview carries, so the tab is not empty.
            FinancialsCard(check: overview.financialCheck)
        }

        KeyStatsCard(overview: overview)
        ValuationCard(overview: overview, price: price)

        if let mix = overview.revenueMix {
            Card("Where sales came from") {
                Text("Fiscal \(String(mix.year)), by segment").eyebrowStyle()
                ForEach(mix.slices.prefix(5)) { slice in RevenueSliceRow(slice: slice) }
            }
        }

        Card("More on \(overview.symbol)") {
            let rivals = overview.marketPosition.keyCompetitors ?? []
            if !rivals.isEmpty {
                Text("Compare with").eyebrowStyle()
                RivalChips(rivals: rivals)
                Divider()
            }
            NavigationLink { SentimentView(symbol: overview.symbol) } label: {
                MoreRow(title: "News & sentiment", detail: "What is being written and how it reads", systemImage: "newspaper")
            }
            Divider()
            NavigationLink { SupplyChainView(symbol: overview.symbol) } label: {
                MoreRow(title: "Supply chain", detail: "Where it sits and what could choke it", systemImage: "point.3.connected.trianglepath.dotted")
            }
            Divider()
            NavigationLink { OptionGoalView(symbol: overview.symbol) } label: {
                MoreRow(title: "Options", detail: "What a call or put would make or lose", systemImage: "arrow.triangle.branch")
            }
            .accessibilityIdentifier("company-options")
        }
        .buttonStyle(.plain)
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
                Button("Try again") { Task { await load() } }.buttonStyle(.borderedProminent)
            }
        }
    }

    private func content(_ overview: CompanyOverview) -> some View {
        let price = quote?.price ?? trend?.latestPrice ?? overview.price
        let read = history.flatMap { TechnicalRead(closes: $0.stock, benchmark: $0.benchmark) }
        let levels = history.flatMap { PriceLevels(closes: $0.stock, price: quote?.price) }
        return ScrollView {
            LazyVStack(alignment: .leading, spacing: Metrics.sectionSpacing) {
                CompanyHeader(overview: overview, quote: quote, fallbackPrice: price)
                CompanyTabBar(selection: $tab)

                switch tab {
                case .financials:
                    financials(overview, price)
                case .price:
                    PerformanceCard(symbol: symbol, trend: trend, history: history, historyFailed: historyFailed)
                    if let history, let read {
                        SetupCard(read: read)
                        SignalsCard(read: read)
                        TrendModelCard(closes: history.stock)
                        if let levels { LevelsCard(levels: levels, isLive: quote != nil) }
                        EntryExitCard(symbol: symbol, closes: history.stock, levels: levels, livePrice: quote?.price) {
                            tradeSide = .buy
                            isTrading = true
                        }
                    } else if historyFailed {
                        Card { Notice(text: "The price history isn't available right now, so the signals and models can't be worked out.", systemImage: "chart.line.downtrend.xyaxis") }
                    } else {
                        Card { SkeletonBlock(height: 120) }
                    }
                    PriceContextCard(overview: overview, read: read, trend: trend, price: price)
                }
                decision(overview, read)

                if let disclaimer = overview.disclaimer {
                    Text(disclaimer).font(.caption2).foregroundStyle(.inkSecondary)
                }
            }
            .padding(Metrics.screenPadding)
        }
        .bottomBar {
            HStack(spacing: 10) {
                NavigationLink {
                    TemplateGalleryView(presetTicker: overview.symbol)
                } label: {
                    Label("Test a strategy", systemImage: "chart.xyaxis.line")
                }
                .buttonStyle(PrimaryButtonStyle())
                .accessibilityIdentifier("test-strategy")

                if session.brokerageLink.canTrade {
                    Button {
                        isTrading = true
                    } label: {
                        Label("Trade", systemImage: "arrow.left.arrow.right")
                    }
                    .buttonStyle(SecondaryButtonStyle())
                    .accessibilityIdentifier("trade-at-broker")
                }
            }
        }
    }
}

// MARK: - Header

private struct CompanyHeader: View {
    let overview: CompanyOverview
    let quote: LiveQuote?
    let fallbackPrice: Double?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text([overview.exchange, overview.sector].compactMap { $0 }.joined(separator: " · ")).eyebrowStyle()
            Text(overview.name).font(.title2.weight(.bold))
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                LivePriceText(price: quote?.price ?? fallbackPrice).font(.hero)
                if let quote {
                    VStack(alignment: .leading, spacing: 2) {
                        // The endpoint reports the day's move in percent points.
                        ChangePill(fraction: quote.changePercent / 100)
                        Text("\(Fmt.signedMoney(quote.change)) today")
                            .font(.caption.monospacedDigit()).foregroundStyle(quote.change.changeColor)
                    }
                }
            }
            if quote != nil {
                QuoteFreshnessLabel()
            } else if let asOf = overview.asOfDate {
                Text("Close of \(asOf)").eyebrowStyle()
            }
            if let low = quote?.dayLow, let high = quote?.dayHigh, let price = quote?.price, high > low {
                DayRange(low: low, high: high, price: price)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 4)
    }
}

/// Where today's price sits between the day's low and high.
struct DayRange: View {
    let low: Double
    let high: Double
    let price: Double

    var body: some View {
        HStack(spacing: 8) {
            Text(Fmt.price(low))
            GeometryReader { proxy in
                ZStack(alignment: .leading) {
                    Capsule().fill(Color.well).frame(height: 4)
                    Circle().fill(Color.primary).frame(width: 8, height: 8)
                        .offset(x: (proxy.size.width - 8) * CGFloat(min(max((price - low) / (high - low), 0), 1)))
                }
                .frame(maxHeight: .infinity)
            }
            .frame(height: 10)
            Text(Fmt.price(high))
        }
        .font(.caption2.monospacedDigit()).foregroundStyle(.inkSecondary)
        .padding(.top, 2)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Today's range \(Fmt.price(low)) to \(Fmt.price(high))")
    }
}

// MARK: - Performance chart

/// Price over a chosen period, with the S&P 500 for comparison. Touch and
/// drag to read any day.
struct PerformanceCard: View {
    let symbol: String
    let trend: CompanyTrend?
    /// The stock's and the benchmark's daily closes, once the page has them.
    let history: (stock: [DailyClose], benchmark: [DailyClose])?
    let historyFailed: Bool

    @State private var range: PerformanceRange = .oneYear
    /// 1D or 1W: prices through the day instead of daily closes.
    @State private var intraday: IntradayRange?
    @State private var selectedDate: Date?

    private struct PricePoint: Identifiable {
        let date: Date
        let price: Double
        var id: Date { date }
    }

    private var series: PerformanceSeries? {
        history.map { PerformanceSeries(stock: $0.stock, benchmark: $0.benchmark, range: range) }
    }

    private func pricePoints(_ series: PerformanceSeries?) -> [PricePoint] {
        if let series, series.points.count > 1 {
            return series.points.map { PricePoint(date: $0.date, price: $0.price) }
        }
        // Until the history arrives (or if it can't be had), the 90 days
        // that came with the trend are better than an empty card.
        return (trend?.pricePoints ?? []).map { PricePoint(date: $0.date, price: $0.price) }
    }

    /// "Past year", or — when the stock's prices begin inside the period —
    /// the days the chart really covers: "Since Nov 19 · 3 trading days".
    private func chartTitle(_ series: PerformanceSeries?, usesHistory: Bool, first: Date?) -> String {
        guard usesHistory, let series else { return "Last 90 days" }
        guard series.isShorterThanRange, let first else { return range.title }
        let days = series.tradingDays
        return "Since \(Fmt.shortTradingDay(first)) · \(days) trading day\(days == 1 ? "" : "s")"
    }

    /// Axis labels for what is drawn, not for the range picked: a year chart
    /// of a stock that listed last week labels days, not "Nov Nov Nov".
    private static func axisFormat(spanning points: [PricePoint]) -> Date.FormatStyle {
        guard let first = points.first?.date, let last = points.last?.date else { return Fmt.utc(.dateTime.month(.abbreviated)) }
        let days = last.timeIntervalSince(first) / 86_400
        if days <= 100 { return Fmt.utc(.dateTime.month(.abbreviated).day()) }
        if days <= 800 { return Fmt.utc(.dateTime.month(.abbreviated)) }
        return Fmt.utc(.dateTime.year())
    }

    var body: some View {
        let series = series
        let points = pricePoints(series)
        let selected = selectedDate.flatMap { date in
            points.min { abs($0.date.timeIntervalSince(date)) < abs($1.date.timeIntervalSince(date)) }
        }
        let first = points.first?.price
        let shown = selected ?? points.last
        let change = (shown?.price).flatMap { last in first.map { last / $0 - 1 } }
        let color = (change ?? 0).changeColor
        let usesHistory = (series?.points.count ?? 0) > 1
        let title = chartTitle(series, usesHistory: usesHistory, first: points.first?.date)
        // A few days of prices: draw each day as a point joined by straight
        // lines, and label the days themselves. A smoothed curve through
        // three closes invents a path between them.
        let isShort = points.count < 40

        Card {
            if let intraday {
                IntradayChartSection(symbol: symbol, range: intraday)
            } else {
                VStack(alignment: .leading, spacing: 2) {
                    if let selected {
                        Text(Fmt.tradingDay(selected.date)).eyebrowStyle()
                        Text(Fmt.price(selected.price)).font(.title3.weight(.semibold).monospacedDigit())
                    } else {
                        Text(title).eyebrowStyle()
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text(Fmt.percent(change, signed: true))
                                .font(.title3.weight(.semibold).monospacedDigit()).foregroundStyle(color)
                            if let excess = series?.excessReturn {
                                Text("\(Fmt.percent(excess, signed: true)) vs S&P 500")
                                    .font(.subheadline.monospacedDigit()).foregroundStyle(.inkSecondary)
                            }
                        }
                    }
                }
                .frame(height: 44, alignment: .topLeading)

                if points.count > 1 {
                    let low = points.map(\.price).min() ?? 0
                    let high = points.map(\.price).max() ?? 1
                    let pad = max((high - low) * 0.08, high * 0.002)
                    Chart {
                        ForEach(points) { point in
                            AreaMark(
                                x: .value("Date", point.date),
                                yStart: .value("Floor", low - pad),
                                yEnd: .value("Price", point.price)
                            )
                            .foregroundStyle(LinearGradient(colors: [color.opacity(0.22), color.opacity(0)], startPoint: .top, endPoint: .bottom))
                            .interpolationMethod(isShort ? .linear : .monotone)
                            LineMark(x: .value("Date", point.date), y: .value("Price", point.price))
                                .foregroundStyle(color)
                                .lineStyle(StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
                                .interpolationMethod(isShort ? .linear : .monotone)
                            if points.count <= 12 {
                                PointMark(x: .value("Date", point.date), y: .value("Price", point.price))
                                    .foregroundStyle(color).symbolSize(28)
                            }
                        }
                        if let first {
                            RuleMark(y: .value("Start", first))
                                .foregroundStyle(Color.inkSecondary.opacity(0.5))
                                .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 3]))
                        }
                        if let selected {
                            RuleMark(x: .value("Date", selected.date)).foregroundStyle(Color.inkSecondary.opacity(0.6))
                            PointMark(x: .value("Date", selected.date), y: .value("Price", selected.price))
                                .foregroundStyle(color).symbolSize(70)
                        }
                    }
                    .chartYScale(domain: (low - pad)...(high + pad))
                    // Room either side so the first and last day's labels are
                    // not clipped at the plot's edge.
                    .chartXScale(range: .plotDimension(padding: points.count <= 6 ? 24 : 0))
                    .chartYAxis {
                        AxisMarks(position: .trailing, values: .automatic(desiredCount: 3)) { value in
                            AxisGridLine().foregroundStyle(Color.hairline.opacity(0.5))
                            AxisValueLabel {
                                if let amount = value.as(Double.self) { Text(Fmt.axisPrice(amount)) }
                            }
                        }
                    }
                    .chartXAxis {
                        if points.count <= 6 {
                            // One label per trading day.
                            AxisMarks(values: points.map(\.date)) { _ in
                                AxisValueLabel(format: Fmt.utc(.dateTime.month(.abbreviated).day()))
                            }
                        } else {
                            AxisMarks(values: .automatic(desiredCount: 4)) { _ in
                                AxisValueLabel(format: Self.axisFormat(spanning: points))
                            }
                        }
                    }
                    .chartXSelection(value: $selectedDate)
                    .frame(height: 200)
                    .sensoryFeedback(.selection, trigger: selected?.date)
                    .accessibilityLabel("\(symbol) price, \(title.lowercased())")
                } else if historyFailed {
                    Notice(text: "The price history for this period isn't available right now.", systemImage: "chart.line.downtrend.xyaxis")
                        .frame(height: 200, alignment: .center)
                } else {
                    SkeletonBlock(height: 200)
                }
            }

            HStack(spacing: 4) {
                ForEach(IntradayRange.allCases) { option in
                    rangeButton(option.rawValue, isSelected: intraday == option) {
                        selectedDate = nil
                        intraday = option
                    }
                }
                ForEach(PerformanceRange.allCases) { option in
                    rangeButton(option.rawValue, isSelected: intraday == nil && option == range) {
                        selectedDate = nil
                        intraday = nil
                        range = option
                    }
                }
            }
            .padding(3)
            .background(Color.well, in: Capsule())
            .sensoryFeedback(.selection, trigger: range)
            .sensoryFeedback(.selection, trigger: intraday)
        }
    }

    private func rangeButton(_ label: String, isSelected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.footnote.weight(.semibold))
                .frame(maxWidth: .infinity, minHeight: 32)
                .foregroundStyle(isSelected ? Color.white : .inkSecondary)
                .background(isSelected ? Color.brand : Color.clear, in: Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("range-\(label)")
        .accessibilityAddTraits(isSelected ? .isSelected : [])
    }
}

private extension PerformanceRange {
    var title: String {
        switch self {
        case .oneMonth: "Past month"
        case .threeMonths: "Past 3 months"
        case .sixMonths: "Past 6 months"
        case .yearToDate: "Year to date"
        case .oneYear: "Past year"
        case .fiveYears: "Past 5 years"
        }
    }

}

// MARK: - Valuation

/// The way into the cash-flow stress test, showing what the starting
/// assumptions imply against today's price.
struct ValuationCard: View {
    let overview: CompanyOverview
    let price: Double?

    var body: some View {
        let model = CashFlowModel(overview: overview, price: price)
        NavigationLink {
            ValuationView(overview: overview, price: price)
        } label: {
            Card {
                HStack(alignment: .top, spacing: 12) {
                    Image(systemName: "function")
                        .font(.body.weight(.semibold)).foregroundStyle(.brand)
                        .frame(width: 40, height: 40)
                        .background(Color.brand.opacity(0.10), in: RoundedRectangle(cornerRadius: 11, style: .continuous))
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Stress-test the cash flows").font(.headline)
                        if let value = model?.valuePerShare, let model {
                            Text("At \(Fmt.percent(model.growth)) growth and a \(Fmt.percent(model.discountRate)) required return, the cash flows imply about \(Fmt.price(value)) a share. Change the assumptions and see what a drop in demand does.")
                                .font(.subheadline).foregroundStyle(.inkSecondary)
                        } else {
                            Text(model?.problem ?? "Not enough reported data to value it on cash flows.")
                                .font(.subheadline).foregroundStyle(.inkSecondary)
                        }
                    }
                    Spacer(minLength: 0)
                    Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(.tertiary)
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("open-valuation")
    }
}

// MARK: - Key stats

/// How the market prices the company, on the latest annual figures.
struct KeyStatsCard: View {
    let overview: CompanyOverview

    private var stats: [(String, String)] {
        let check = overview.financialCheck
        let all: [(String, String?)] = [
            ("Market value", overview.marketCap.map { Fmt.money($0) }),
            ("Price to earnings", check.peRatio.map { Fmt.multiple($0) }),
            ("EV / EBITDA", check.evEbitda.map { Fmt.multiple($0) }),
            ("Price to sales", check.psRatio.map { Fmt.multiple($0) }),
            ("Free cash flow yield", check.fcfYield.map { Fmt.percent($0) }),
            ("Return on equity", check.roe.map { Fmt.percent($0) }),
        ]
        return all.compactMap { label, value in value.map { (label, $0) } }
    }

    var body: some View {
        let stats = stats
        if !stats.isEmpty {
            Card("How the market prices it") {
                LazyVGrid(columns: [GridItem(.flexible(), spacing: 8), GridItem(.flexible(), spacing: 8)], spacing: 8) {
                    ForEach(stats, id: \.0) { label, value in
                        StatTile(label: label, value: value)
                    }
                }
                if let asOf = overview.asOfDate {
                    Text("As of \(asOf), on the latest full fiscal year").eyebrowStyle()
                }
            }
        }
    }
}

// MARK: - Financials

struct FinancialsCard: View {
    let check: Components.Schemas.FinancialCheckSection

    private enum Measure: String, CaseIterable, Identifiable {
        case revenue = "Revenue"
        case cashFlow = "Free cash flow"
        var id: String { rawValue }
    }

    @State private var measure: Measure = .revenue

    private var summaries: [(icon: String, title: String, text: String)] {
        let all: [(String, String, String?)] = [
            ("arrow.up.right", "Growth", check.growthSummary),
            ("percent", "Profitability", check.profitabilitySummary),
            ("banknote", "Cash flow", check.cashFlowSummary),
            ("building.columns", "Balance sheet", check.balanceSheetSummary),
        ]
        return all.compactMap { icon, title, text in text.map { (icon, title, $0) } }
    }

    var body: some View {
        let revenue = check.revenueByYear
        let cash = check.freeCashFlowByYear
        let figures = measure == .revenue ? revenue : cash
        let summaries = summaries

        if !(revenue.isEmpty && cash.isEmpty && summaries.isEmpty) {
            Card("Financials") {
                if let dollar = SalesDollar(grossMargin: check.grossMargin, operatingMargin: check.operatingMargin) {
                    SalesDollarBar(dollar: dollar)
                    Divider()
                }
                if !revenue.isEmpty, !cash.isEmpty {
                    Picker("Measure", selection: $measure) {
                        ForEach(Measure.allCases) { Text($0.rawValue).tag($0) }
                    }
                    .pickerStyle(.segmented)
                }
                if figures.count > 1 {
                    Chart(figures) { figure in
                        BarMark(x: .value("Year", figure.year), y: .value(measure.rawValue, figure.value), width: .ratio(0.55))
                            .foregroundStyle(figure.value >= 0 ? Color.brand : Color.loss)
                            .cornerRadius(4)
                            .annotation(position: figure.value >= 0 ? .top : .bottom, spacing: 3) {
                                Text(Fmt.money(figure.value)).font(.caption2.monospacedDigit()).foregroundStyle(.inkSecondary)
                            }
                    }
                    .chartYAxis(.hidden)
                    .frame(height: 150)
                    .accessibilityLabel("\(measure.rawValue) by fiscal year")
                }
                ForEach(summaries, id: \.title) { item in
                    HStack(alignment: .top, spacing: 10) {
                        Image(systemName: item.icon)
                            .font(.footnote.weight(.semibold)).foregroundStyle(.brand)
                            .frame(width: 26, height: 26)
                            .background(Color.brand.opacity(0.10), in: RoundedRectangle(cornerRadius: 7, style: .continuous))
                        VStack(alignment: .leading, spacing: 2) {
                            Text(item.title).font(.caption.weight(.semibold)).foregroundStyle(.inkSecondary)
                            Text(item.text).font(.subheadline)
                        }
                    }
                }
            }
        }
    }
}

/// Where each $100 of sales goes, as one bar.
struct SalesDollarBar: View {
    let dollar: SalesDollar

    var body: some View {
        let profit = max(dollar.operatingProfit, 0)
        VStack(alignment: .leading, spacing: 8) {
            Text("Out of every $100 of sales").eyebrowStyle()
            GeometryReader { proxy in
                HStack(spacing: 2) {
                    Rectangle().fill(Color.inkSecondary.opacity(0.55)).frame(width: proxy.size.width * dollar.costOfSales / 100)
                    Rectangle().fill(Color.caution.opacity(0.8)).frame(width: max(proxy.size.width * dollar.operatingCosts / 100, 0))
                    Rectangle().fill(Color.gain)
                }
                .clipShape(Capsule())
            }
            .frame(height: 12)
            HStack(alignment: .top) {
                SalesDollarPart(amount: dollar.costOfSales, label: "making the product", color: .inkSecondary)
                SalesDollarPart(amount: dollar.operatingCosts, label: "research, selling, running it", color: .caution)
                SalesDollarPart(amount: dollar.operatingProfit, label: profit > 0 ? "operating profit" : "operating loss", color: profit > 0 ? .gain : .loss)
            }
        }
        .accessibilityElement(children: .combine)
    }
}

private struct SalesDollarPart: View {
    let amount: Double
    let label: String
    let color: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 1) {
            Text("$\(Int(amount.rounded()))").font(.headline.monospacedDigit()).foregroundStyle(color)
            Text(label).font(.caption2).foregroundStyle(.inkSecondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - Shared pieces

/// Tags that wrap onto as many lines as they need.
struct FlowTags: View {
    let tags: [String]

    init(_ tags: [String]) {
        self.tags = tags
    }

    var body: some View {
        FlowLayout(spacing: 6) {
            ForEach(tags, id: \.self) { Tag($0) }
        }
    }
}

/// Lays children out left to right, wrapping to a new line when the next
/// one does not fit.
struct FlowLayout: Layout {
    var spacing: CGFloat = 6

    private func rows(_ subviews: Subviews, width: CGFloat) -> [(items: [(index: Int, size: CGSize)], height: CGFloat)] {
        var rows: [(items: [(index: Int, size: CGSize)], height: CGFloat)] = [([], 0)]
        var used: CGFloat = 0
        for (index, subview) in subviews.enumerated() {
            let size = subview.sizeThatFits(.unspecified)
            if !rows[rows.count - 1].items.isEmpty, used + size.width > width {
                rows.append(([], 0))
                used = 0
            }
            rows[rows.count - 1].items.append((index, size))
            rows[rows.count - 1].height = max(rows[rows.count - 1].height, size.height)
            used += size.width + spacing
        }
        return rows
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? .infinity
        let rows = rows(subviews, width: width)
        let height = rows.reduce(0) { $0 + $1.height } + spacing * CGFloat(max(rows.count - 1, 0))
        let widest = rows.map { $0.items.reduce(0) { $0 + $1.size.width } + spacing * CGFloat(max($0.items.count - 1, 0)) }.max() ?? 0
        return CGSize(width: proposal.width ?? widest, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for row in rows(subviews, width: bounds.width) {
            var x = bounds.minX
            for item in row.items {
                subviews[item.index].place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(item.size))
                x += item.size.width + spacing
            }
            y += row.height + spacing
        }
    }
}

struct SourceNotes: View {
    let notes: [String]?

    var body: some View {
        if let notes, !notes.isEmpty {
            Text("Source: " + notes.joined(separator: " · ")).font(.caption2).foregroundStyle(.inkSecondary)
        }
    }
}

struct MoreRow: View {
    let title: String
    let detail: String
    let systemImage: String

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: systemImage)
                .font(.body.weight(.medium)).foregroundStyle(.brand)
                .frame(width: 36, height: 36)
                .background(Color.brand.opacity(0.10), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            VStack(alignment: .leading, spacing: 1) {
                Text(title).font(.subheadline.weight(.semibold))
                Text(detail).font(.caption).foregroundStyle(.inkSecondary)
            }
            Spacer()
            Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(.tertiary)
        }
        .contentShape(Rectangle())
    }
}

/// The page's shape while the overview loads — the slowest call in the app.
private struct CompanySkeleton: View {
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Metrics.sectionSpacing) {
                VStack(alignment: .leading, spacing: 10) {
                    SkeletonBlock(height: 12, width: 120)
                    SkeletonBlock(height: 26, width: 220)
                    SkeletonBlock(height: 44, width: 180)
                }
                .padding(.horizontal, 4)
                Card { SkeletonBlock(height: 250) }
                Card { SkeletonBlock(height: 76, width: 76); SkeletonBlock(); SkeletonBlock(); SkeletonBlock() }
                Card { SkeletonBlock(height: 140) }
            }
            .padding(Metrics.screenPadding)
        }
        .scrollDisabled(true)
        .accessibilityLabel("Loading")
    }
}
