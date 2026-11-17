import LivermoreAPI
import LivermoreKit
import SwiftUI

/// Search for a company, or start from a short list of widely held names.
struct ResearchView: View {
    @Environment(AppSession.self) private var session

    @State private var query = ""
    @State private var results: [SymbolMatch] = []
    @State private var isSearching = false
    @State private var searchError: String?
    @State private var quotes: [String: LiveQuote] = [:]

    /// Shown before the user types. The same large caps the website's ticker
    /// bar leads with.
    private static let starters: [(symbol: String, name: String)] = [
        ("AAPL", "Apple"), ("MSFT", "Microsoft"), ("NVDA", "NVIDIA"), ("GOOGL", "Alphabet"),
        ("AMZN", "Amazon"), ("META", "Meta Platforms"), ("TSLA", "Tesla"),
    ]

    private var trimmedQuery: String { query.trimmingCharacters(in: .whitespaces) }

    var body: some View {
        NavigationStack {
            List {
                if trimmedQuery.isEmpty {
                    Section("Widely held") {
                        ForEach(Self.starters, id: \.symbol) { starter in
                            NavigationLink(value: starter.symbol) {
                                StarterRow(symbol: starter.symbol, name: starter.name, quote: quotes[starter.symbol])
                            }
                        }
                    }
                } else if let searchError {
                    ContentUnavailableView("Search failed", systemImage: "wifi.exclamationmark", description: Text(searchError))
                } else if results.isEmpty && !isSearching {
                    ContentUnavailableView.search(text: trimmedQuery)
                } else {
                    ForEach(results, id: \.symbol) { match in
                        if ResearchService.isUSListing(match) {
                            NavigationLink(value: match.symbol) { MatchRow(match: match) }
                        } else {
                            // The company page covers US tickers only; show
                            // the listing so the search doesn't look broken,
                            // but don't offer a page that would fail.
                            MatchRow(match: match).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .navigationTitle("Research")
            .navigationDestination(for: String.self) { symbol in
                CompanyView(symbol: symbol)
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
            .task { await loadQuotes() }
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

    private func loadQuotes() async {
        if let loaded = try? await session.research.quotes(Self.starters.map(\.symbol)) {
            quotes = loaded
        }
    }
}

private struct StarterRow: View {
    let symbol: String
    let name: String
    let quote: LiveQuote?

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(symbol).font(.headline.monospaced())
                Text(name).font(.subheadline).foregroundStyle(.secondary)
            }
            Spacer()
            if let quote {
                VStack(alignment: .trailing, spacing: 2) {
                    Text(Fmt.price(quote.price)).font(.subheadline.monospacedDigit())
                    Text(Fmt.percentPoints(quote.changePercent))
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(quote.changePercent.changeColor)
                }
            }
        }
    }
}

private struct MatchRow: View {
    let match: SymbolMatch

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(match.symbol).font(.headline.monospaced())
            Text(match.name).font(.subheadline).foregroundStyle(.secondary).lineLimit(1)
            if let region = match.region, region != "United States" {
                Text(region).font(.caption).foregroundStyle(.tertiary)
            }
        }
    }
}
