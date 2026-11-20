import Foundation

/// The last answer for each key, kept for a few minutes.
///
/// Reopening a company the user looked at a moment ago should not show a
/// skeleton and should not ask the backend again: the backend itself keeps a
/// company page for ten minutes, so within that time a second request can
/// only return what the first one did.
@MainActor
public final class RecentValues<Value> {
    private struct Entry {
        let value: Value
        let storedAt: Date
    }

    public let lifetime: TimeInterval
    public let capacity: Int
    private let now: () -> Date
    private var entries: [String: Entry] = [:]
    /// Keys from least to most recently stored.
    private var order: [String] = []

    public init(lifetime: TimeInterval = 300, capacity: Int = 24, now: @escaping () -> Date = { .now }) {
        self.lifetime = lifetime
        self.capacity = capacity
        self.now = now
    }

    private func normalized(_ key: String) -> String { key.uppercased() }

    /// The stored value if it is younger than `lifetime`.
    public func value(for key: String) -> Value? {
        let key = normalized(key)
        guard let entry = entries[key] else { return nil }
        guard now().timeIntervalSince(entry.storedAt) < lifetime else {
            entries[key] = nil
            order.removeAll { $0 == key }
            return nil
        }
        return entry.value
    }

    public func store(_ value: Value, for key: String) {
        let key = normalized(key)
        entries[key] = Entry(value: value, storedAt: now())
        order.removeAll { $0 == key }
        order.append(key)
        while order.count > capacity {
            entries[order.removeFirst()] = nil
        }
    }

    public func removeAll() {
        entries.removeAll()
        order.removeAll()
    }
}
