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
        phase = .loading
        trend = nil
        trendFailed = false
        let research = session.research
        async let trendResult: CompanyTrend? = try? research.trend(symbol)

        do throws(ResearchError) {
            let overview = try await research.overview(symbol)
            phase = .loaded(overview)
            session.watchlist.viewed(symbol, name: overview.name)
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
                Button("Try again") { Task { await load() } }.buttonStyle(.borderedProminent)
            }
        }
    }

    private func content(_ overview: CompanyOverview) -> some View {
        let price = quote?.price ?? trend?.latestPrice ?? overview.price
        return ScrollView {
            LazyVStack(alignment: .leading, spacing: Metrics.sectionSpacing) {
                CompanyHeader(overview: overview, quote: quote, fallbackPrice: price)
                PerformanceCard(symbol: symbol, latestPrice: price, trend: trend)
                ReadCard(overview: overview, trend: trend, trendFailed: trendFailed)
                KeyStatsCard(overview: overview)
                FinancialsCard(check: overview.financialCheck)
                BusinessCard(overview: overview)
                MarketCard(position: overview.marketPosition)
                if let trend { MomentumCard(trend: trend) }

                Card("Go deeper") {
                    NavigationLink { SentimentView(symbol: overview.symbol) } label: {
                        MoreRow(title: "News & sentiment", detail: "What is being written and how it reads", systemImage: "newspaper")
                    }
                    Divider()
                    NavigationLink { SupplyChainView(symbol: overview.symbol) } label: {
                        MoreRow(title: "Supply chain", detail: "Where it sits and what could choke it", systemImage: "point.3.connected.trianglepath.dotted")
                    }
                }
                .buttonStyle(.plain)

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
private struct DayRange: View {
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
private struct PerformanceCard: View {
    @Environment(AppSession.self) private var session
    let symbol: String
    let latestPrice: Double?
    let trend: CompanyTrend?

    @State private var range: PerformanceRange = .oneYear
    /// The stock's and the benchmark's daily closes, once fetched.
    @State private var history: (stock: [DailyClose], benchmark: [DailyClose])?
    @State private var historyFailed = false
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

        Card {
            VStack(alignment: .leading, spacing: 2) {
                if let selected {
                    Text(selected.date.formatted(date: .abbreviated, time: .omitted)).eyebrowStyle()
                    Text(Fmt.price(selected.price)).font(.title3.weight(.semibold).monospacedDigit())
                } else {
                    Text(usesHistory ? range.title : "Last 90 days").eyebrowStyle()
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
                        .interpolationMethod(.monotone)
                        LineMark(x: .value("Date", point.date), y: .value("Price", point.price))
                            .foregroundStyle(color)
                            .lineStyle(StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
                            .interpolationMethod(.monotone)
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
                .chartYAxis {
                    AxisMarks(position: .trailing, values: .automatic(desiredCount: 3)) { value in
                        AxisGridLine().foregroundStyle(Color.hairline.opacity(0.5))
                        AxisValueLabel {
                            if let amount = value.as(Double.self) { Text(Fmt.axisPrice(amount)) }
                        }
                    }
                }
                .chartXAxis {
                    AxisMarks(values: .automatic(desiredCount: 4)) { _ in
                        AxisValueLabel(format: range.axisFormat)
                    }
                }
                .chartXSelection(value: $selectedDate)
                .frame(height: 200)
                .sensoryFeedback(.selection, trigger: selected?.date)
                .accessibilityLabel("\(symbol) price, \(range.title.lowercased())")
            } else if historyFailed {
                Notice(text: "The price history for this period isn't available right now.", systemImage: "chart.line.downtrend.xyaxis")
                    .frame(height: 200, alignment: .center)
            } else {
                SkeletonBlock(height: 200)
            }

            HStack(spacing: 6) {
                ForEach(PerformanceRange.allCases) { option in
                    Button {
                        selectedDate = nil
                        range = option
                    } label: {
                        Text(option.rawValue)
                            .font(.footnote.weight(.semibold))
                            .frame(maxWidth: .infinity, minHeight: 32)
                            .foregroundStyle(option == range ? Color.white : .inkSecondary)
                            .background(option == range ? Color.brand : Color.clear, in: Capsule())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("range-\(option.rawValue)")
                    .accessibilityAddTraits(option == range ? .isSelected : [])
                }
            }
            .padding(3)
            .background(Color.well, in: Capsule())
            .sensoryFeedback(.selection, trigger: range)
        }
        .task(id: symbol) {
            guard history == nil else { return }
            do {
                // The benchmark is shared by every chart and fetched once
                // per launch; if only it fails the price still shows.
                async let benchmark = try? session.priceHistory.closes(for: PriceHistory.benchmarkSymbol)
                let stock = try await session.priceHistory.closes(for: symbol)
                history = (stock, await benchmark ?? [])
            } catch {
                historyFailed = true
            }
        }
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

    var axisFormat: Date.FormatStyle {
        switch self {
        case .oneMonth, .threeMonths: .dateTime.month(.abbreviated).day()
        case .sixMonths, .yearToDate, .oneYear: .dateTime.month(.abbreviated)
        case .fiveYears: .dateTime.year()
        }
    }
}

// MARK: - Livermore's read

/// The three scores and what they add up to, on one card.
private struct ReadCard: View {
    let overview: CompanyOverview
    let trend: CompanyTrend?
    let trendFailed: Bool

    var body: some View {
        let metrics = StockMetrics(overview: overview, trend: trend)
        let health = StockScoring.health(metrics)
        let valuation = StockScoring.valuation(metrics)
        let trendScore = StockScoring.trend(metrics)
        let check = overview.financialCheck

        Card("Livermore's read") {
            if trend != nil {
                let overall = StockScoring.overall(health: health, valuation: valuation, trend: trendScore)
                HStack(spacing: 16) {
                    ScoreRing(score: overall)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(StockScoring.label(forOverall: overall)).font(.title3.weight(.semibold))
                        Text("Health, valuation and trend, weighed together. A way to organise the evidence — not a recommendation.")
                            .font(.caption).foregroundStyle(.inkSecondary)
                    }
                }
                Divider()
            }
            ScoreBar(title: "Business health", score: health, detail: check.financialValidationLabel ?? "Is the business fundamentally healthy?")
            ScoreBar(title: "Valuation", score: valuation, detail: check.valuationSummary ?? "Is it cheap, fair or expensive?")
            if let trend {
                ScoreBar(title: "Market trend", score: trendScore, detail: Self.trendLine(trend))
            } else if trendFailed {
                Notice(text: "Market trend is unavailable for this company, so there is no overall score.")
            } else {
                SkeletonBlock(height: 34)
            }
        }
    }

    /// The trend in a sentence, from the two averages traders watch.
    static func trendLine(_ trend: CompanyTrend) -> String {
        switch ((trend.priceVsMa50 ?? 0) >= 0, (trend.priceVsMa200 ?? 0) >= 0) {
        case (true, true): "Above both its 50-day and 200-day averages."
        case (false, false): "Below both its 50-day and 200-day averages."
        case (true, false): "Back above its 50-day average, still below the 200-day."
        case (false, true): "Slipped below its 50-day average, still above the 200-day."
        }
    }
}

// MARK: - Key stats

private struct KeyStatsCard: View {
    let overview: CompanyOverview

    private var stats: [(String, String)] {
        let check = overview.financialCheck
        let all: [(String, String?)] = [
            ("Market cap", overview.marketCap.map { Fmt.money($0) }),
            ("P/E", check.peRatio.map { Fmt.multiple($0) }),
            ("EV / EBITDA", check.evEbitda.map { Fmt.multiple($0) }),
            ("Price / sales", check.psRatio.map { Fmt.multiple($0) }),
            ("Revenue growth", check.revenueYoy.map { Fmt.percent($0, signed: true) }),
            ("3-year revenue CAGR", check.revenue3yCagr.map { Fmt.percent($0, signed: true) }),
            ("Gross margin", check.grossMargin.map { Fmt.percent($0) }),
            ("Operating margin", check.operatingMargin.map { Fmt.percent($0) }),
            ("Return on equity", check.roe.map { Fmt.percent($0) }),
            ("FCF yield", check.fcfYield.map { Fmt.percent($0) }),
            ("Net debt", check.netDebt.map { Fmt.money($0) }),
            ("Debt / equity", check.debtToEquity.map { String(format: "%.2f", $0) }),
        ]
        return all.compactMap { label, value in value.map { (label, $0) } }
    }

    var body: some View {
        let stats = stats
        if !stats.isEmpty {
            Card("Key stats") {
                LazyVGrid(columns: [GridItem(.flexible(), spacing: 8), GridItem(.flexible(), spacing: 8)], spacing: 8) {
                    ForEach(stats, id: \.0) { label, value in
                        StatTile(label: label, value: value)
                    }
                }
                if let asOf = overview.asOfDate {
                    Text("Fundamentals as of \(asOf)").eyebrowStyle()
                }
            }
        }
    }
}

// MARK: - Financials

private struct FinancialsCard: View {
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
                ForEach(check.warnings ?? [], id: \.self) { warning in
                    Notice(text: warning, systemImage: "exclamationmark.triangle.fill", tint: .caution)
                }
            }
        }
    }
}

// MARK: - Business

private struct BusinessCard: View {
    let overview: CompanyOverview

    var body: some View {
        let map = overview.businessMap
        let rows: [(String, String?)] = [
            ("How it makes money", map.revenueModel), ("Margins", map.marginImplication),
            ("Pricing power", map.pricingPowerImplication), ("Cyclicality", map.cyclicalityImplication),
        ]
        let shown = rows.compactMap { title, text in text.map { (title, $0) } }
        let mix = overview.revenueMix

        if map.oneLineSummary != nil || !shown.isEmpty || mix != nil {
            Card("The business") {
                if let summary = map.oneLineSummary {
                    Text(summary).font(.body)
                }
                let tags = [map.primaryValueChainRole, overview.industry].compactMap { $0 }
                if !tags.isEmpty {
                    FlowTags(tags)
                }
                if let mix {
                    Divider()
                    Text("Revenue mix · fiscal \(String(mix.year))").eyebrowStyle()
                    ForEach(mix.slices.prefix(5)) { slice in
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
                if !shown.isEmpty {
                    Divider()
                    ForEach(shown, id: \.0) { title, text in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(title).font(.caption.weight(.semibold)).foregroundStyle(.inkSecondary)
                            Text(text).font(.subheadline)
                        }
                    }
                }
                SourceNotes(notes: map.sourceNotes)
            }
        }
    }
}

// MARK: - Market position

private struct MarketCard: View {
    let position: Components.Schemas.MarketPositionSection

    var body: some View {
        let drivers = position.keyGrowthDrivers ?? []
        let risks = position.keyRisks ?? []
        let rivals = position.keyCompetitors ?? []

        if position.marketCategory != nil || !drivers.isEmpty || !risks.isEmpty || !rivals.isEmpty {
            Card("Market position") {
                if let category = position.marketCategory {
                    Text(category).font(.subheadline.weight(.semibold))
                }
                HStack(spacing: 6) {
                    if let label = position.competitivePositionLabel { Tag(label.capitalized, tint: .brand, systemImage: "flag.fill") }
                    if let growth = position.marketGrowthLabel { Tag("\(growth.capitalized) market", tint: .inkSecondary) }
                }
                if let notes = position.marketShareNotes {
                    Text(notes).font(.subheadline)
                }
                if !drivers.isEmpty {
                    PointList(title: "What could drive it", points: drivers, systemImage: "arrow.up.right.circle.fill", tint: .gain)
                }
                if !risks.isEmpty {
                    PointList(title: "What could hurt it", points: risks, systemImage: "exclamationmark.circle.fill", tint: .loss)
                }
                if !rivals.isEmpty {
                    Divider()
                    Text("Competes with").eyebrowStyle()
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
                SourceNotes(notes: position.sourceNotes)
            }
        }
    }
}

private struct PointList: View {
    let title: String
    let points: [String]
    let systemImage: String
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).eyebrowStyle()
            ForEach(points, id: \.self) { point in
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Image(systemName: systemImage).font(.footnote).foregroundStyle(tint)
                    Text(point.prefix(1).uppercased() + point.dropFirst()).font(.subheadline)
                }
            }
        }
    }
}

// MARK: - Momentum

private struct MomentumCard: View {
    let trend: CompanyTrend

    var body: some View {
        Card("Momentum") {
            HStack(spacing: 8) {
                StatTile(label: "1 month", value: Fmt.percent(trend.perf1m, signed: true), tint: trend.perf1m?.changeColor)
                StatTile(label: "3 months", value: Fmt.percent(trend.perf3m, signed: true), tint: trend.perf3m?.changeColor)
            }
            HStack(spacing: 8) {
                StatTile(label: "6 months", value: Fmt.percent(trend.perf6m, signed: true), tint: trend.perf6m?.changeColor)
                StatTile(label: "12 months", value: Fmt.percent(trend.perf12m, signed: true), tint: trend.perf12m?.changeColor)
            }
            DetailRow("Against its 50-day average", Fmt.percent(trend.priceVsMa50, signed: true), tint: trend.priceVsMa50?.changeColor)
            DetailRow("Against its 200-day average", Fmt.percent(trend.priceVsMa200, signed: true), tint: trend.priceVsMa200?.changeColor)
            DetailRow("Against the S&P 500, 3 months", Fmt.percent(trend.rsVsSpy3m, signed: true), tint: trend.rsVsSpy3m?.changeColor)
            DetailRow("Against the S&P 500, 12 months", Fmt.percent(trend.rsVsSpy12m, signed: true), tint: trend.rsVsSpy12m?.changeColor)
            if let date = trend.latestDate {
                Text("Prices through \(date)").eyebrowStyle()
            }
        }
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
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 6) { ForEach(tags, id: \.self) { Tag($0) } }
            VStack(alignment: .leading, spacing: 6) { ForEach(tags, id: \.self) { Tag($0) } }
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

private struct MoreRow: View {
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
