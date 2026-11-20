import Foundation
import Observation

/// What is waiting on the user, loaded once and shared: the Actions tab shows
/// it and the tab's badge counts it.
@MainActor
@Observable
public final class ActionInbox {
    public private(set) var exits: [UnresolvedExit] = []
    public private(set) var notices: [PendingNotice] = []
    public private(set) var failure: APIFailure?
    /// When the list was last read from the backend; nil until it has been.
    public private(set) var loadedAt: Date?

    @ObservationIgnored var onSessionExpired: (@MainActor () -> Void)?
    private let service: ActionService

    init(service: ActionService) {
        self.service = service
    }

    /// Exits are decisions; notices are reading. Only decisions are counted.
    public var waitingCount: Int { exits.count }

    public func refresh() async {
        async let exitRows = Result<[UnresolvedExit], APIFailure>.capture { [service] () async throws(APIFailure) in
            try await service.unresolvedExits()
        }
        async let noticeRows = Result<[PendingNotice], APIFailure>.capture { [service] () async throws(APIFailure) in
            try await service.notices()
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
        if case .success(let rows) = await noticeRows { notices = rows }
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

    public func acknowledge(_ notice: PendingNotice) async throws(APIFailure) {
        try await service.acknowledge(notice)
        notices.removeAll { $0.id == notice.id }
    }

    func reset() {
        exits = []
        notices = []
        failure = nil
        loadedAt = nil
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
