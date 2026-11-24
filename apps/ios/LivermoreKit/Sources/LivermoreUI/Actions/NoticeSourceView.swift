import LivermoreKit
import SwiftUI

/// Everything one strategy or screen has said, and what the user can do
/// about it: read it all, silence it, or open the strategy behind it.
struct NoticeSourceView: View {
    @Environment(AppSession.self) private var session
    let group: NoticeGroup

    @State private var source: NoticeSource?
    @State private var strategy: SavedStrategy?
    @State private var failure: APIFailure?
    @State private var isWorking = false

    private var inbox: ActionInbox { session.inbox }
    private var kind: NoticeSourceKind { source?.kind ?? group.kind }
    private var isMuted: Bool { source?.muted ?? group.muted }
    private var notices: [NoticeItem] { source?.notices ?? group.notices }
    private var unread: Int { notices.filter { !$0.read }.count }

    var body: some View {
        List {
            Section {
                HStack(spacing: 12) {
                    NoticeSourceIcon(kind: kind, level: group.noticeLevel)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(kind == .other ? "Notices" : kind.noun.capitalized).eyebrowStyle()
                        Text(source?.title ?? group.title).font(.headline)
                        if isMuted {
                            HStack(spacing: 4) {
                                Image(systemName: "speaker.slash")
                                Text("Muted")
                            }
                            .font(.caption.weight(.medium)).foregroundStyle(.secondary)
                        }
                    }
                }
                .accessibilityElement(children: .combine)
            }

            Section {
                if unread > 0 {
                    Button("Mark all \(unread) read", systemImage: "checkmark.circle", action: readAll)
                        .disabled(isWorking)
                        .accessibilityIdentifier("notice-read-all")
                }
                if let sourceID = group.sourceId {
                    Button(
                        isMuted ? "Unmute this \(kind.noun)" : "Mute this \(kind.noun)",
                        systemImage: isMuted ? "speaker.wave.2" : "speaker.slash"
                    ) { toggleMute(sourceID) }
                    .disabled(isWorking)
                    .accessibilityIdentifier("notice-mute")
                }
                if let strategy {
                    NavigationLink {
                        StrategyDetailView(strategy: strategy, trackedPositions: [])
                    } label: {
                        Label("Open strategy", systemImage: "chart.line.uptrend.xyaxis")
                    }
                    .accessibilityIdentifier("notice-open-strategy")
                }
            } footer: {
                if group.sourceId != nil {
                    Text(isMuted
                         ? "Muted: its updates arrive already read and it sends no emails. Stops and targets on positions you hold still come through."
                         : "Muting stops this \(kind.noun)'s updates here and its emails. Stops and targets on positions you hold still come through.")
                }
            }

            Section(source == nil && group.sourceId != nil ? "New" : "Updates") {
                if let failure {
                    Text(failure.message).foregroundStyle(.secondary)
                }
                ForEach(notices, id: \.id) { notice in
                    NoticeRow(notice: notice)
                }
            }
        }
        .screenBackground()
        .navigationTitle(source?.title ?? group.title)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .task { await load() }
        .refreshable { await load() }
    }

    private func load() async {
        guard let sourceID = group.sourceId else { return }
        do throws(APIFailure) {
            source = try await inbox.history(of: sourceID)
            failure = nil
        } catch {
            if error == .notSignedIn { session.signOut() }
            failure = error
        }
        if kind == .strategy, strategy == nil {
            strategy = try? await session.strategies.strategies().first { $0.id == sourceID }
        }
    }

    private func readAll() {
        isWorking = true
        Task {
            do throws(APIFailure) {
                if let sourceID = group.sourceId {
                    try await inbox.readAll(from: sourceID)
                } else {
                    try await inbox.readAll(group)
                }
                await load()
            } catch {
                failure = error
            }
            isWorking = false
        }
    }

    private func toggleMute(_ sourceID: String) {
        let muting = !isMuted
        isWorking = true
        Task {
            do throws(APIFailure) {
                if muting { try await inbox.mute(sourceID) } else { try await inbox.unmute(sourceID) }
                await load()
            } catch {
                failure = error
            }
            isWorking = false
        }
    }
}

/// One notice: when, what happened, and the rule's own words.
private struct NoticeRow: View {
    let notice: NoticeItem

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                if !notice.read {
                    Circle().fill(Color.brand).frame(width: 7, height: 7).accessibilityLabel("Unread")
                }
                Text(notice.createdAt.formatted(date: .abbreviated, time: .shortened).uppercased())
                    .font(.caption2.weight(.semibold)).tracking(0.8).foregroundStyle(.secondary)
                if notice.noticeLevel == .act {
                    Text(NoticeLevel.act.label).font(.caption2.weight(.semibold)).foregroundStyle(Color.loss)
                }
            }
            Text(notice.headline).font(.subheadline.weight(notice.read ? .regular : .semibold))
            Text(notice.body).font(.subheadline).foregroundStyle(.secondary)
        }
        .padding(.vertical, 2)
        .accessibilityElement(children: .combine)
    }
}

/// The strategies and screens the user has silenced, each with Unmute.
struct MutedSourcesView: View {
    @Environment(AppSession.self) private var session

    private var inbox: ActionInbox { session.inbox }

    var body: some View {
        List {
            Section {
                if inbox.muted.isEmpty {
                    Text("Nothing is muted.").foregroundStyle(.secondary)
                }
                ForEach(inbox.muted, id: \.sourceId) { source in
                    HStack {
                        Label {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(source.title)
                                Text(source.kind.noun.capitalized).font(.caption).foregroundStyle(.secondary)
                            }
                        } icon: {
                            Image(systemName: NoticeSourceIcon.symbol(for: source.kind))
                        }
                        Spacer()
                        Button("Unmute") {
                            Task { try? await inbox.unmute(source.sourceId) }
                        }
                        .buttonStyle(.borderless)
                        .accessibilityIdentifier("unmute-source")
                    }
                }
            } footer: {
                Text("A muted strategy or screen sends no updates here and no emails. Stops and targets on positions you hold still come through.")
            }
        }
        .screenBackground()
        .navigationTitle("Muted")
    }
}

/// What sent a notice, tinted by how much it matters.
struct NoticeSourceIcon: View {
    let kind: NoticeSourceKind
    let level: NoticeLevel

    static func symbol(for kind: NoticeSourceKind) -> String {
        switch kind {
        case .strategy: "chart.line.uptrend.xyaxis"
        case .screen: "line.3.horizontal.decrease.circle"
        case .other: "bell"
        }
    }

    private var tint: Color {
        switch level {
        case .act: .loss
        case .changed: .brand
        case .fyi: .inkSecondary
        }
    }

    var body: some View {
        Image(systemName: Self.symbol(for: kind))
            .font(.title3).foregroundStyle(tint)
            .frame(width: 42, height: 42)
            .background(tint.opacity(0.12), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .accessibilityHidden(true)
    }
}
