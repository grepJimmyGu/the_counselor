import Foundation
import Observation

/// The symbols a user keeps an eye on, and the ones they looked at last.
///
/// Kept on the device, so it works without an account. It is not the
/// website's community watchlist and does not sync with it.
@MainActor
@Observable
public final class Watchlist {
    public struct Entry: Codable, Equatable, Identifiable, Sendable {
        public let symbol: String
        public var name: String

        public var id: String { symbol }
    }

    public private(set) var entries: [Entry]
    public private(set) var recents: [Entry]

    /// What a new install starts with, so the first screen is not empty.
    public static let starters: [Entry] = [
        .init(symbol: "AAPL", name: "Apple"), .init(symbol: "MSFT", name: "Microsoft"),
        .init(symbol: "NVDA", name: "NVIDIA"), .init(symbol: "GOOGL", name: "Alphabet"),
        .init(symbol: "AMZN", name: "Amazon"), .init(symbol: "META", name: "Meta Platforms"),
        .init(symbol: "TSLA", name: "Tesla"),
    ]

    static let maxRecents = 8
    private static let entriesKey = "watchlist.entries.v1"
    private static let recentsKey = "watchlist.recents.v1"
    @ObservationIgnored private let defaults: UserDefaults

    public init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        entries = Self.load(Self.entriesKey, from: defaults) ?? Self.starters
        recents = Self.load(Self.recentsKey, from: defaults) ?? []
    }

    private static func load(_ key: String, from defaults: UserDefaults) -> [Entry]? {
        guard let data = defaults.data(forKey: key) else { return nil }
        return try? JSONDecoder().decode([Entry].self, from: data)
    }

    private func save() {
        defaults.set(try? JSONEncoder().encode(entries), forKey: Self.entriesKey)
        defaults.set(try? JSONEncoder().encode(recents), forKey: Self.recentsKey)
    }

    public var symbols: [String] { entries.map(\.symbol) }

    public func contains(_ symbol: String) -> Bool {
        entries.contains { $0.symbol == symbol.uppercased() }
    }

    /// Adds to the top, or removes if it is already there.
    public func toggle(_ symbol: String, name: String) {
        let symbol = symbol.uppercased()
        if contains(symbol) {
            entries.removeAll { $0.symbol == symbol }
        } else {
            entries.insert(Entry(symbol: symbol, name: name), at: 0)
        }
        save()
    }

    public func remove(atOffsets offsets: IndexSet) {
        for index in offsets.sorted(by: >) where entries.indices.contains(index) { entries.remove(at: index) }
        save()
    }

    public func move(fromOffsets source: IndexSet, toOffset destination: Int) {
        let moving = source.sorted().map { entries[$0] }
        var remaining = entries
        for index in source.sorted(by: >) { remaining.remove(at: index) }
        let insertAt = destination - source.filter { $0 < destination }.count
        remaining.insert(contentsOf: moving, at: min(max(insertAt, 0), remaining.count))
        entries = remaining
        save()
    }

    /// Records that a company page was opened: newest first, no repeats.
    public func viewed(_ symbol: String, name: String) {
        let symbol = symbol.uppercased()
        recents.removeAll { $0.symbol == symbol }
        recents.insert(Entry(symbol: symbol, name: name), at: 0)
        if recents.count > Self.maxRecents { recents.removeLast(recents.count - Self.maxRecents) }
        save()
    }
}
