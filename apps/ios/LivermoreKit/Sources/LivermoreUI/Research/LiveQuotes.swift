import LivermoreKit
import SwiftUI

extension View {
    /// Keeps prices for `symbols` fresh for as long as this view is on screen.
    /// Read them from `session.quotes.quotes`.
    func liveQuotes(_ symbols: [String]) -> some View {
        modifier(LiveQuotesModifier(symbols: symbols))
    }
}

private struct LiveQuotesModifier: ViewModifier {
    @Environment(AppSession.self) private var session
    let symbols: [String]
    /// What this view is currently holding in the store, so every `watch` is
    /// matched by an `unwatch` of the same list even as `symbols` changes.
    @State private var watching: [String] = []

    func body(content: Content) -> some View {
        content
            .onAppear { sync(to: symbols) }
            .onDisappear { sync(to: []) }
            .onChange(of: symbols) { _, new in sync(to: new) }
    }

    private func sync(to next: [String]) {
        guard next != watching else { return }
        // Watch before unwatching, so a symbol in both lists never drops to
        // zero watchers and restarts the polling loop for nothing.
        session.quotes.watch(next)
        session.quotes.unwatch(watching)
        watching = next
    }
}

/// When the prices on screen were last checked — always in view next to them.
struct QuoteFreshnessLabel: View {
    @Environment(AppSession.self) private var session

    var body: some View {
        let store = session.quotes
        Group {
            if let checked = store.lastChecked {
                if store.lastRefreshFailed {
                    Label(
                        "Couldn't refresh — prices from \(checked.formatted(date: .omitted, time: .standard))",
                        systemImage: "wifi.exclamationmark"
                    )
                    .foregroundStyle(.orange)
                } else {
                    Label(
                        "Prices checked \(checked.formatted(date: .omitted, time: .standard))",
                        systemImage: "dot.radiowaves.left.and.right"
                    )
                    .foregroundStyle(.secondary)
                }
            } else if store.lastRefreshFailed {
                Label("Couldn't load live prices", systemImage: "wifi.exclamationmark")
                    .foregroundStyle(.orange)
            }
        }
        .font(.caption.weight(.semibold))
        .accessibilityIdentifier("quote-freshness")
    }
}

/// A price that rolls to its new value when a refresh changes it.
struct LivePriceText: View {
    let price: Double?

    var body: some View {
        Text(Fmt.price(price))
            .monospacedDigit()
            .contentTransition(.numericText(value: price ?? 0))
            .animation(.default, value: price)
    }
}
