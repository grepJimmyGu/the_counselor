import Foundation
import Observation

/// Live prices for whatever is on screen, kept fresh while it stays there.
///
/// Screens say which symbols they are showing (`watch`) and stop when they go
/// away (`unwatch`); the store polls the quote endpoint for the union and every
/// screen reads the same `quotes`. Nothing is fetched for a screen nobody is
/// looking at, or while the app is in the background.
///
/// How fresh a price can be is set by the backend, not by this interval: the
/// quote endpoint caches each symbol (30 seconds at the time of writing), so
/// polling faster than that only narrows the gap between the cache refreshing
/// and the screen noticing.
@MainActor
@Observable
public final class QuoteStore {
    public typealias Fetch = @Sendable ([String]) async throws -> [String: LiveQuote]

    /// The most recent quote for each symbol that has ever been fetched. A
    /// failed refresh leaves the last known price in place.
    public private(set) var quotes: [String: LiveQuote] = [:]
    /// When the backend last answered. This is when the price was *checked*;
    /// outside market hours the price itself is the last trade.
    public private(set) var lastChecked: Date?
    /// The most recent refresh failed, so `quotes` may be older than
    /// `interval` suggests.
    public private(set) var lastRefreshFailed = false

    public let interval: Duration

    /// The quote endpoint's cap on symbols per request.
    static let batchSize = 100

    @ObservationIgnored private var watchers: [String: Int] = [:]
    @ObservationIgnored private var loop: Task<Void, Never>?
    @ObservationIgnored private var isActive = true
    private let fetch: Fetch
    private let now: @Sendable () -> Date

    public init(
        interval: Duration = .seconds(10),
        now: @escaping @Sendable () -> Date = { .now },
        fetch: @escaping Fetch
    ) {
        self.interval = interval
        self.now = now
        self.fetch = fetch
    }

    public var watchedSymbols: [String] { watchers.keys.sorted() }

    private static func normalized(_ symbols: [String]) -> [String] {
        var seen = Set<String>()
        return symbols
            .map { $0.trimmingCharacters(in: .whitespaces).uppercased() }
            .filter { !$0.isEmpty && seen.insert($0).inserted }
    }

    /// Start keeping these symbols fresh. Balanced by `unwatch` with the same
    /// list; two screens watching one symbol keep it alive until both let go.
    public func watch(_ symbols: [String]) {
        var isNew = false
        for symbol in Self.normalized(symbols) {
            watchers[symbol, default: 0] += 1
            if watchers[symbol] == 1 { isNew = true }
        }
        // A symbol nobody was watching should not wait out the interval.
        if isNew || loop == nil { restart() }
    }

    public func unwatch(_ symbols: [String]) {
        for symbol in Self.normalized(symbols) {
            guard let count = watchers[symbol] else { continue }
            watchers[symbol] = count > 1 ? count - 1 : nil
        }
        if watchers.isEmpty { stop() }
    }

    /// Pause while the app is in the background; refresh at once on return.
    public func setActive(_ active: Bool) {
        guard active != isActive else { return }
        isActive = active
        if active { restart() } else { stop() }
    }

    /// Fetch every watched symbol now.
    public func refresh() async {
        let symbols = watchedSymbols
        guard !symbols.isEmpty else { return }
        var fetched: [String: LiveQuote] = [:]
        var failed = false
        for start in stride(from: 0, to: symbols.count, by: Self.batchSize) {
            let batch = Array(symbols[start..<min(start + Self.batchSize, symbols.count)])
            do {
                fetched.merge(try await fetch(batch)) { _, new in new }
            } catch {
                failed = true
            }
        }
        // A refresh superseded mid-flight (a new symbol restarted the loop)
        // must not overwrite what its replacement is about to report.
        guard !Task.isCancelled else { return }
        quotes.merge(fetched) { _, new in new }
        lastRefreshFailed = failed
        if !fetched.isEmpty || !failed { lastChecked = now() }
    }

    private func restart() {
        loop?.cancel()
        loop = nil
        guard isActive, !watchers.isEmpty else { return }
        loop = Task { [weak self, interval] in
            while !Task.isCancelled {
                await self?.refresh()
                try? await Task.sleep(for: interval)
            }
        }
    }

    private func stop() {
        loop?.cancel()
        loop = nil
    }
}
