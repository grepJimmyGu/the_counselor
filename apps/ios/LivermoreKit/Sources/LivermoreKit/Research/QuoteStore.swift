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
///
/// When no US session is open (nights, weekends) the price is the last trade
/// and is not going to change, so the store polls at `idleInterval` instead.
/// That is most of the week, and it is the single largest stream of requests
/// the app makes.
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

    /// Between refreshes while a US session, pre-market through after-hours, is open.
    public let interval: Duration
    /// Between refreshes the rest of the time.
    public let idleInterval: Duration

    /// The quote endpoint's cap on symbols per request.
    static let batchSize = 100

    @ObservationIgnored private var watchers: [String: Int] = [:]
    @ObservationIgnored private var loop: Task<Void, Never>?
    @ObservationIgnored private var isActive = true
    private let fetch: Fetch
    private let now: @Sendable () -> Date
    private let isTrading: @Sendable (Date) -> Bool

    public init(
        interval: Duration = .seconds(10),
        idleInterval: Duration = .seconds(60),
        now: @escaping @Sendable () -> Date = { .now },
        isTrading: @escaping @Sendable (Date) -> Bool = MarketHours.isOpen(at:),
        fetch: @escaping Fetch
    ) {
        self.interval = interval
        self.idleInterval = idleInterval
        self.now = now
        self.isTrading = isTrading
        self.fetch = fetch
    }

    /// How long to wait before the next refresh, as things stand now.
    public var currentInterval: Duration { isTrading(now()) ? interval : idleInterval }

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
        loop = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                await self.refresh()
                // Read each time round: a session opens and closes while the
                // app is running.
                try? await Task.sleep(for: self.currentInterval)
            }
        }
    }

    private func stop() {
        loop?.cancel()
        loop = nil
    }
}

/// When US stock prices can change.
public enum MarketHours {
    /// Monday to Friday, 4:00 to 20:00 New York time: pre-market through
    /// after-hours. Market holidays are not known here and count as open,
    /// which only means polling at the faster rate on a day nothing moves.
    public static func isOpen(at date: Date) -> Bool {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/New_York") ?? .gmt
        let parts = calendar.dateComponents([.weekday, .hour], from: date)
        guard let weekday = parts.weekday, let hour = parts.hour else { return true }
        return (2...6).contains(weekday) && (4..<20).contains(hour)
    }
}
