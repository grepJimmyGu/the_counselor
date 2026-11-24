import Foundation
import Observation

/// What is waiting on the user, loaded once and shared: the Actions tab shows
/// it and the tab's badge counts it.
@MainActor
@Observable
public final class ActionInbox {
    public private(set) var exits: [UnresolvedExit] = []
    /// Unread notices, one group per strategy or screen, most important first.
    public private(set) var updates: [NoticeGroup] = []
    /// Strategies and screens the user has silenced.
    public private(set) var muted: [MutedNoticeSource] = []
    public private(set) var failure: APIFailure?
    /// When the list was last read from the backend; nil until it has been.
    public private(set) var loadedAt: Date?

    @ObservationIgnored var onSessionExpired: (@MainActor () -> Void)?
    private let service: ActionService

    init(service: ActionService) {
        self.service = service
    }

    /// Exits are decisions; notices are reading. Only decisions are counted.
    /// Unread updates are shown on the tab itself, not in the badge.
    public var waitingCount: Int { exits.count }

    public func refresh() async {
        async let exitRows = Result<[UnresolvedExit], APIFailure>.capture { [service] () async throws(APIFailure) in
            try await service.unresolvedExits()
        }
        async let noticeRows = Result<NoticeInbox, APIFailure>.capture { [service] () async throws(APIFailure) in
            try await service.noticeInbox()
        }
        switch await exitRows {
        case .success(let rows):
            exits = rows
            failure = nil
            loadedAt = .now
        case .failure(let error):
            if error == .notSignedIn { onSessionExpired?() }
            failure = error
        }
        // Notices are secondary: if they fail the exits are still shown.
        if case .success(let inbox) = await noticeRows {
            updates = inbox.groups
            muted = inbox.muted
        }
    }

    /// The user sold. The exit leaves the list once the backend has it.
    public func confirm(_ exit: UnresolvedExit, sharesSold: Double, fillPrice: Double?) async throws(APIFailure) {
        try await service.confirmExit(exit, sharesSold: sharesSold, fillPrice: fillPrice)
        exits.removeAll { $0.id == exit.id }
    }

    /// The user looked and is keeping the position.
    public func hold(_ exit: UnresolvedExit) async throws(APIFailure) {
        try await service.hold(exit)
        exits.removeAll { $0.id == exit.id }
    }

    /// Everything one strategy or screen has sent, read or not.
    public func history(of sourceID: String) async throws(APIFailure) -> NoticeSource {
        try await service.noticeSource(sourceID)
    }

    /// Marks a group's notices read: by source when it has one, by id when
    /// the notices have no strategy behind them.
    public func readAll(_ group: NoticeGroup) async throws(APIFailure) {
        if let source = group.sourceId {
            try await service.markNoticesRead(sourceID: source)
        } else {
            try await service.markNoticesRead(ids: group.notices.map(\.id))
        }
        updates.removeAll { $0.id == group.id }
    }

    public func readAll(from sourceID: String) async throws(APIFailure) {
        try await service.markNoticesRead(sourceID: sourceID)
        updates.removeAll { $0.sourceId == sourceID }
    }

    /// Silences a strategy or screen, here and in email. Its unread notices
    /// are cleared; exits on held positions are not affected.
    public func mute(_ sourceID: String) async throws(APIFailure) {
        try await service.muteNotices(from: sourceID)
        await refresh()
    }

    public func unmute(_ sourceID: String) async throws(APIFailure) {
        try await service.unmuteNotices(from: sourceID)
        muted.removeAll { $0.sourceId == sourceID }
        updates = updates.map { $0.sourceId == sourceID ? $0.with(muted: false) : $0 }
    }

    func reset() {
        exits = []
        updates = []
        muted = []
        failure = nil
        loadedAt = nil
    }
}

extension NoticeGroup {
    func with(muted: Bool) -> Self {
        var copy = self
        copy.muted = muted
        return copy
    }
}

extension Result where Failure == APIFailure {
    /// Runs a typed-throwing call and keeps its outcome, so two calls can run
    /// together without one failure cancelling the other.
    public static func capture(_ body: () async throws(APIFailure) -> Success) async -> Result {
        do {
            return .success(try await body())
        } catch {
            return .failure(error)
        }
    }
}
