import LivermoreAPI
import LivermoreKit
import SwiftUI

/// The research home: how the market is doing, the names you follow, and
/// search for anything else.
struct ResearchView: View {
    @Environment(AppSession.self) private var session

    @State private var query = ""
    @State private var results: [SymbolMatch] = []
    @State private var isSearching = false
    @State private var searchError: String?
    /// A month of closes per symbol, for the sparklines. Slower than quotes,
    /// so prices show first and these fill in.
    @State private var snapshots: [String: MarketSnapshot] = [:]

    /// The market at a glance, through the ETFs that track each index.
    private static let indices: [(symbol: String, name: String)] = [
        ("SPY", "S&P 500"), ("QQQ", "Nasdaq 100"), ("DIA", "Dow 30"), ("IWM", "Small caps"),
    ]

    private var trimmedQuery: String { query.trimmingCharacters(in: .whitespaces) }
    private var watchlist: Watchlist { session.watchlist }
    private var watched: [String] { Self.indices.map(\.symbol) + watchlist.symbols }

    var body: some View {
        NavigationStack {
            List {
                if trimmedQuery.isEmpty {
                    home
                } else if let searchError {
                    ContentUnavailableView("Search failed", systemImage: "wifi.exclamationmark", description: Text(searchError))
                        .listRowBackground(Color.clear)
                } else if results.isEmpty && !isSearching {
                    ContentUnavailableView.search(text: trimmedQuery).listRowBackground(Color.clear)
                } else {
                    Section {
                        ForEach(results, id: \.symbol) { match in
                            if ResearchService.isUSListing(match) {
                                NavigationLink(value: match.symbol) { MatchRow(match: match) }
                            } else {
                                // The company page covers US tickers only;
                                // show the listing so the search doesn't
                                // look broken, but don't offer a page that
                                // would fail.
                                MatchRow(match: match).opacity(0.5)
                            }
                        }
                    }
                }
            }
            #if os(iOS)
            .listSectionSpacing(.compact)
            #endif
            .screenBackground()
            .navigationTitle("Research")
            .navigationDestination(for: String.self) { symbol in
                CompanyView(symbol: symbol)
            }
            .toolbar {
                #if os(iOS)
                if trimmedQuery.isEmpty, !watchlist.entries.isEmpty {
                    ToolbarItem(placement: .primaryAction) { EditButton() }
                }
                #endif
            }
            // Always shown: by default iOS hides the field until the list is
            // pulled down, which hides the one thing this tab is for.
            #if os(iOS)
            .searchable(text: $query, placement: .navigationBarDrawer(displayMode: .always), prompt: "Ticker or company")
            .textInputAutocapitalization(.characters)
            // Tickers and company names are Latin text. Without this, a pinyin
            // or kana keyboard sends its half-composed text ("nv id" for
            // "nvid") as the query on every keystroke.
            .keyboardType(.asciiCapable)
            #else
            .searchable(text: $query, prompt: "Ticker or company")
            #endif
            .autocorrectionDisabled()
            .overlay { if isSearching && results.isEmpty { ProgressView() } }
            .task(id: trimmedQuery) { await search() }
            .task(id: watched) { await loadSnapshots() }
            .refreshable {
                await session.quotes.refresh()
                await loadSnapshots()
            }
            .liveQuotes(watched)
        }
    }

    @ViewBuilder
    private var home: some View {
        Section {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 10) {
                    ForEach(Self.indices, id: \.symbol) { index in
                        IndexCard(
                            name: index.name, symbol: index.symbol,
                            quote: session.quotes.quotes[index.symbol], snapshot: snapshots[index.symbol]
                        )
                    }
                }
                .padding(.horizontal, Metrics.screenPadding)
            }
            .listRowInsets(EdgeInsets())
            .listRowBackground(Color.clear)
        } header: {
            Text("Markets")
        } footer: {
            QuoteFreshnessLabel()
        }

        Section {
            if watchlist.entries.isEmpty {
                Text("Search for a company and tap the star on its page to follow it here.")
                    .font(.subheadline).foregroundStyle(.inkSecondary)
            }
            ForEach(watchlist.entries) { entry in
                NavigationLink(value: entry.symbol) {
                    WatchRow(
                        symbol: entry.symbol, name: entry.name,
                        quote: session.quotes.quotes[entry.symbol], snapshot: snapshots[entry.symbol]
                    )
                }
            }
            .onDelete { watchlist.remove(atOffsets: $0) }
            .onMove { watchlist.move(fromOffsets: $0, toOffset: $1) }
        } header: {
            Text("Watchlist")
        }

        let recents = watchlist.recents.filter { !watchlist.contains($0.symbol) }
        if !recents.isEmpty {
            Section("Recently viewed") {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(recents) { entry in
                            NavigationLink(value: entry.symbol) {
                                Text(entry.symbol)
                                    .font(.subheadline.weight(.semibold).monospaced())
                                    .padding(.horizontal, 14).padding(.vertical, 9)
                                    .background(Color.surface, in: Capsule())
                                    .overlay(Capsule().strokeBorder(Color.hairline.opacity(0.8), lineWidth: 0.5))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal, Metrics.screenPadding)
                }
                .listRowInsets(EdgeInsets())
                .listRowBackground(Color.clear)
            }
        }
    }

    private func loadSnapshots() async {
        let wanted = watched.filter { snapshots[$0] == nil }
        guard !wanted.isEmpty else { return }
        if let loaded = try? await session.research.snapshots(wanted) {
            snapshots.merge(loaded) { _, new in new }
        }
    }

    private func search() async {
        let wanted = trimmedQuery
        searchError = nil
        guard !wanted.isEmpty else {
            results = []
            isSearching = false
            return
        }
        isSearching = true
        // Wait for a pause in typing; `.task(id:)` cancels this on each keystroke.
        try? await Task.sleep(for: .milliseconds(300))
        guard !Task.isCancelled else { return }
        do throws(ResearchError) {
            let found = try await session.research.search(wanted)
            guard !Task.isCancelled else { return }
            results = found
        } catch {
            guard !Task.isCancelled else { return }
            results = []
            searchError = error.message
        }
        isSearching = false
    }
}

/// One index, through the ETF that tracks it.
private struct IndexCard: View {
    let name: String
    let symbol: String
    let quote: LiveQuote?
    let snapshot: MarketSnapshot?

    private var price: Double? { quote?.price ?? snapshot?.lastPrice }
    /// Quotes report the day's move in percent points; snapshots as a fraction.
    private var change: Double? { quote.map { $0.changePercent / 100 } ?? snapshot?.changePct }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(name).font(.subheadline.weight(.semibold))
                Spacer(minLength: 4)
                Text(symbol).font(.caption2.weight(.semibold).monospaced()).foregroundStyle(.inkSecondary)
            }
            if let snapshot, snapshot.sparkline.count > 1 {
                Sparkline(values: snapshot.sparkline).frame(height: 34)
            } else {
                Color.clear.frame(height: 34)
            }
            if let price {
                LivePriceText(price: price).font(.subheadline.weight(.semibold))
            } else {
                SkeletonBlock(height: 16, width: 70)
            }
            ChangePill(fraction: change, compact: true)
        }
        .padding(12)
        .frame(width: 148, alignment: .leading)
        .background(Color.surface, in: RoundedRectangle(cornerRadius: Metrics.cardRadius, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: Metrics.cardRadius, style: .continuous)
                .strokeBorder(Color.hairline.opacity(0.6), lineWidth: 0.5)
        )
        .accessibilityElement(children: .combine)
    }
}

/// A followed company: who, the month's shape, the price and the day's move.
private struct WatchRow: View {
    let symbol: String
    let name: String
    let quote: LiveQuote?
    let snapshot: MarketSnapshot?

    private var price: Double? { quote?.price ?? snapshot?.lastPrice }
    private var change: Double? { quote.map { $0.changePercent / 100 } ?? snapshot?.changePct }

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(symbol).font(.headline.monospaced())
                Text(name).font(.caption).foregroundStyle(.inkSecondary).lineLimit(1)
            }
            Spacer(minLength: 8)
            if let snapshot, snapshot.sparkline.count > 1 {
                Sparkline(values: snapshot.sparkline).frame(width: 64, height: 28)
            }
            VStack(alignment: .trailing, spacing: 3) {
                if let price {
                    LivePriceText(price: price).font(.subheadline.weight(.semibold))
                } else {
                    SkeletonBlock(height: 14, width: 60)
                }
                ChangePill(fraction: change, compact: true)
            }
            .frame(minWidth: 84, alignment: .trailing)
        }
        .padding(.vertical, 2)
        .accessibilityElement(children: .combine)
    }
}

private struct MatchRow: View {
    let match: SymbolMatch

    var body: some View {
        HStack(spacing: 12) {
            Text(String(match.symbol.prefix(1)))
                .font(.headline).foregroundStyle(.brand)
                .frame(width: 36, height: 36)
                .background(Color.brand.opacity(0.10), in: Circle())
            VStack(alignment: .leading, spacing: 2) {
                Text(match.symbol).font(.headline.monospaced())
                Text(match.name).font(.caption).foregroundStyle(.inkSecondary).lineLimit(1)
                if let region = match.region, region != "United States" {
                    Text(region).font(.caption2).foregroundStyle(.tertiary)
                }
            }
        }
        .padding(.vertical, 2)
    }
}
