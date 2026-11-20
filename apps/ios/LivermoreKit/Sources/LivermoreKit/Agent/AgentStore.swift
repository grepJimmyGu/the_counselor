import Foundation
import Observation

/// What the app knows about the user's agent: its settings and its findings.
@MainActor
@Observable
public final class AgentStore {
    public private(set) var profile: AgentProfile?
    public private(set) var insights: [AgentInsight] = []
    /// What the last check could not do, in the backend's words.
    public private(set) var notes: [String] = []
    public private(set) var isChecking = false
    public private(set) var failure: APIFailure?
    public private(set) var lastChecked: Date?

    /// Called when the backend says the session has ended.
    public var onSessionExpired: () -> Void = {}

    private let service: AgentService

    public init(service: AgentService) {
        self.service = service
    }

    /// Findings the user has not dismissed that are marked to watch.
    public var attentionCount: Int { insights.filter { $0.severity == "watch" }.count }

    public func reset() {
        profile = nil
        insights = []
        notes = []
        failure = nil
        lastChecked = nil
    }

    /// Reads the settings and what has been found. Does not start a check.
    public func load() async {
        await run {
            async let profile = self.service.profile()
            async let insights = self.service.insights()
            let (loadedProfile, loadedInsights) = try await (profile, insights)
            self.profile = loadedProfile
            self.insights = loadedInsights
            self.lastChecked = loadedProfile.lastScanAt
        }
    }

    /// Has the agent look now.
    public func check() async {
        guard !isChecking else { return }
        isChecking = true
        defer { isChecking = false }
        await run {
            let scan = try await self.service.scan()
            self.insights = scan.insights ?? []
            self.notes = scan.notes ?? []
            self.lastChecked = scan.checkedAt
        }
    }

    public func dismiss(_ insight: AgentInsight) async {
        // Gone at once; put back if the backend did not take it.
        let before = insights
        insights.removeAll { $0.id == insight.id }
        await run({ try await self.service.dismiss(insight) }, onFailure: { self.insights = before })
    }

    public func update(
        enabled: Bool? = nil, moveAlertPct: Double? = nil, maxPositionPct: Double? = nil, notes: String? = nil
    ) async {
        await run {
            self.profile = try await self.service.update(
                enabled: enabled, moveAlertPct: moveAlertPct, maxPositionPct: maxPositionPct, notes: notes
            )
        }
    }

    /// Tells the backend which symbols to watch. The watchlist lives on this
    /// device, and the agent runs on the backend while the app is closed, so
    /// without this it would have nothing to watch.
    public func syncWatchlist(_ symbols: [String]) async {
        guard let profile, profile.watchlist != symbols else { return }
        await run { self.profile = try await self.service.update(watchlist: symbols) }
    }

    private func run(_ work: () async throws -> Void, onFailure: () -> Void = {}) async {
        do {
            try await work()
            failure = nil
        } catch let error as APIFailure {
            onFailure()
            if error == .notSignedIn { onSessionExpired() } else { failure = error }
        } catch {
            onFailure()
            failure = .network
        }
    }
}
