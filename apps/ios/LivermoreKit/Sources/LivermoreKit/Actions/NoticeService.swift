import Foundation
import LivermoreAPI
import OpenAPIRuntime

public typealias NoticeItem = Components.Schemas.NoticeView
public typealias NoticeGroup = Components.Schemas.NoticeGroupView
public typealias MutedNoticeSource = Components.Schemas.MutedSourceView
public typealias NoticeInbox = Components.Schemas.NoticeInboxView
public typealias NoticeSource = Components.Schemas.NoticeSourceView

/// The notice inbox: what each strategy and screen has told the user, grouped
/// by the one that sent it, read in bulk, and silenced per source.
///
/// Muting a source stops its notices here and its emails. It never touches an
/// exit on a held position: those are decisions, listed on their own.
extension ActionService {
    public func noticeInbox() async throws(APIFailure) -> NoticeInbox {
        let output = try await APIFailure.perform { try await client.noticeInboxViewApiMeNoticesGet() }
        switch output {
        case .ok(let ok):
            guard case .json(let inbox) = ok.body else { throw .server(status: 200) }
            return inbox
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    /// Everything one strategy or screen has sent, read or not, newest first.
    public func noticeSource(_ sourceID: String) async throws(APIFailure) -> NoticeSource {
        let output = try await APIFailure.perform {
            try await client.noticeSourceViewApiMeNoticesSourcesSourceIdGet(path: .init(sourceId: sourceID))
        }
        switch output {
        case .ok(let ok):
            guard case .json(let source) = ok.body else { throw .server(status: 200) }
            return source
        case .unprocessableContent:
            throw .server(status: 422)
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    /// Marks notices read: every unread one from a source, or the ones named.
    @discardableResult
    public func markNoticesRead(sourceID: String) async throws(APIFailure) -> Int {
        try await markRead(.init(sourceId: sourceID))
    }

    @discardableResult
    public func markNoticesRead(ids: [Int]) async throws(APIFailure) -> Int {
        try await markRead(.init(ids: ids))
    }

    private func markRead(_ request: Components.Schemas.MarkReadRequest) async throws(APIFailure) -> Int {
        let output = try await APIFailure.perform {
            try await client.markNoticesReadApiMeNoticesReadPost(body: .json(request))
        }
        switch output {
        case .ok(let ok):
            guard case .json(let response) = ok.body else { throw .server(status: 200) }
            return response.marked
        case .unprocessableContent:
            throw .server(status: 422)
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    /// Silences a strategy or screen: no notices here and no emails from it.
    public func muteNotices(from sourceID: String) async throws(APIFailure) {
        let output = try await APIFailure.perform {
            try await client.muteNoticeSourceApiMeNoticesMutesSourceIdPut(path: .init(sourceId: sourceID))
        }
        switch output {
        case .noContent:
            return
        case .unprocessableContent:
            throw .server(status: 422)
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }

    public func unmuteNotices(from sourceID: String) async throws(APIFailure) {
        let output = try await APIFailure.perform {
            try await client.unmuteNoticeSourceApiMeNoticesMutesSourceIdDelete(path: .init(sourceId: sourceID))
        }
        switch output {
        case .noContent:
            return
        case .unprocessableContent:
            throw .server(status: 422)
        case .undocumented(let status, let payload):
            throw await APIFailure.from(status: status, payload: payload)
        }
    }
}

// MARK: - How a notice reads

/// How much a notice matters, from the backend's `level`.
public enum NoticeLevel: String, Sendable, Comparable {
    /// A stop or target on a held position was hit.
    case act
    /// A strategy now says buy or sell.
    case changed
    /// A screen gained or lost a name.
    case fyi

    public init(_ raw: String) { self = NoticeLevel(rawValue: raw) ?? .fyi }

    /// The words on the row: short, and about what happened.
    public var label: String {
        switch self {
        case .act: "Exit reached"
        case .changed: "Signal changed"
        case .fyi: "For your information"
        }
    }

    private var rank: Int {
        switch self {
        case .act: 3
        case .changed: 2
        case .fyi: 1
        }
    }

    public static func < (lhs: NoticeLevel, rhs: NoticeLevel) -> Bool { lhs.rank < rhs.rank }
}

/// What sent a group of notices.
public enum NoticeSourceKind: String, Sendable {
    case strategy, screen, other

    public init(_ raw: String) { self = NoticeSourceKind(rawValue: raw) ?? .other }

    /// "strategy" or "screen", for "Mute this strategy".
    public var noun: String {
        switch self {
        case .strategy: "strategy"
        case .screen: "screen"
        case .other: "source"
        }
    }
}

extension Components.Schemas.NoticeView {
    public var noticeLevel: NoticeLevel { NoticeLevel(level) }

    /// The notice without the source's name in front: a title of
    /// "⚡ Momentum leaders — PLTR entered 'Momentum leaders'" reads
    /// "PLTR entered 'Momentum leaders'" under that source's name.
    public var headline: String {
        let trimmed = title.hasPrefix("⚡") ? String(title.dropFirst()).trimmingCharacters(in: .whitespaces) : title
        guard let range = trimmed.range(of: " — ") else { return trimmed }
        let rest = trimmed[range.upperBound...].trimmingCharacters(in: .whitespaces)
        return rest.isEmpty ? trimmed : rest
    }
}

extension Components.Schemas.NoticeGroupView {
    /// Stable across loads: the source, or one bucket for notices without one.
    public var id: String { sourceId ?? "other" }
    public var noticeLevel: NoticeLevel { NoticeLevel(level) }
    public var kind: NoticeSourceKind { NoticeSourceKind(sourceKind) }

    /// The newest notice's headline, for the row.
    public var latestHeadline: String { notices.first?.headline ?? "" }

    /// "3 new · Signal changed".
    public var summary: String {
        "\(unreadCount) new · \(noticeLevel.label)"
    }
}

extension Components.Schemas.MutedSourceView {
    public var kind: NoticeSourceKind { NoticeSourceKind(sourceKind) }
}

extension Components.Schemas.NoticeSourceView {
    public var kind: NoticeSourceKind { NoticeSourceKind(sourceKind) }
    public var unreadCount: Int { notices.filter { !$0.read }.count }
}
