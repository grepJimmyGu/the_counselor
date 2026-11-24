import LivermoreKit
import SwiftUI

/// What the user's strategies are asking them to do.
struct ActionsView: View {
    @Environment(AppSession.self) private var session

    private var inbox: ActionInbox { session.inbox }
    private var link: BrokerageLink { session.brokerageLink }

    var body: some View {
        NavigationStack {
            Group {
                if !session.isSignedIn {
                    ContentUnavailableView {
                        Label("Sign in to see your actions", systemImage: "bell.badge")
                    } description: {
                        Text("When a strategy you track reaches a stop or a target, it appears here until you decide what to do. Sign in from the Account tab.")
                    }
                } else {
                    list
                }
            }
            .screenBackground()
            .navigationTitle("Actions")
            .navigationDestination(for: UnresolvedExit.self) { ExitDecisionView(exit: $0) }
            .navigationDestination(for: NoticeGroup.self) { NoticeSourceView(group: $0) }
        }
        .task(id: session.isSignedIn) {
            guard session.isSignedIn else { return }
            async let inboxLoad: Void = inbox.refresh()
            async let linkLoad: Void = link.refresh()
            _ = await (inboxLoad, linkLoad)
        }
    }

    private var list: some View {
        List {
            if session.isDemo { SampleDataNotice() }

            Section {
                if inbox.exits.isEmpty {
                    if inbox.loadedAt == nil, inbox.failure == nil {
                        HStack { ProgressView(); Text("Checking your positions…").foregroundStyle(.secondary) }
                    } else if let failure = inbox.failure {
                        Text(failure.message).foregroundStyle(.secondary)
                    } else {
                        Label("Nothing is waiting on you.", systemImage: "checkmark.circle")
                            .foregroundStyle(.secondary)
                    }
                } else {
                    ForEach(inbox.exits, id: \.id) { exit in
                        NavigationLink(value: exit) { ExitRow(exit: exit) }
                    }
                }
            } header: {
                Text(inbox.exits.count > 1 ? "\(inbox.exits.count) exits waiting on you" : "Waiting on you")
            } footer: {
                VStack(alignment: .leading, spacing: 4) {
                    if !inbox.exits.isEmpty {
                        Text("Nothing has been sold — no order goes out unless you send it. Each one stays here until you say what you did.")
                    }
                    if let loaded = inbox.loadedAt {
                        Text("CHECKED \(loaded.formatted(date: .abbreviated, time: .shortened).uppercased())")
                            .font(.caption2.weight(.semibold)).tracking(0.6)
                    }
                }
            }

            Section("Your broker") {
                NavigationLink {
                    BrokerageView()
                } label: {
                    LabeledContent {
                        Text(brokerSummary)
                    } label: {
                        Label("Brokerage", systemImage: "building.columns")
                    }
                }
                .accessibilityIdentifier("open-brokerage")
            }

            updatesSection
        }
        .refreshable {
            await inbox.refresh()
            await link.refresh()
        }
    }

    private var brokerSummary: String {
        guard let status = link.status else { return link.failure == nil ? "…" : "Unavailable" }
        if !status.configured { return "Unavailable" }
        if !status.isLinked { return "Not linked" }
        let count = status.connectedAccounts
        return "\(count) account\(count == 1 ? "" : "s")" + (status.canTrade ? "" : " · view only")
    }

    /// What strategies and screens have said since the user last looked,
    /// one row per source, most important first.
    @ViewBuilder
    private var updatesSection: some View {
        if inbox.loadedAt != nil {
            Section {
                if inbox.updates.isEmpty {
                    Label("No new updates from your strategies and screens.", systemImage: "tray")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(inbox.updates, id: \.id) { group in
                        NavigationLink(value: group) { NoticeGroupRow(group: group) }
                            .swipeActions(edge: .trailing) {
                                Button("Read") { readAll(group) }.tint(.brand)
                                if let source = group.sourceId, !group.muted {
                                    Button("Mute") { mute(source) }.tint(.gray)
                                }
                            }
                            .accessibilityIdentifier("notice-group")
                    }
                }
                if !inbox.muted.isEmpty {
                    NavigationLink {
                        MutedSourcesView()
                    } label: {
                        LabeledContent {
                            Text("\(inbox.muted.count)")
                        } label: {
                            Label("Muted", systemImage: "speaker.slash")
                        }
                    }
                    .accessibilityIdentifier("muted-sources")
                }
            } header: {
                Text("Updates")
            } footer: {
                Text("Swipe a row to mark it read or mute it. Stops and targets on positions you hold always come through.")
            }
        }
    }

    private func readAll(_ group: NoticeGroup) {
        Task { try? await inbox.readAll(group) }
    }

    private func mute(_ source: String) {
        Task { try? await inbox.mute(source) }
    }
}

/// One strategy or screen with unread updates.
private struct NoticeGroupRow: View {
    let group: NoticeGroup

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            NoticeSourceIcon(kind: group.kind, level: group.noticeLevel)
            VStack(alignment: .leading, spacing: 3) {
                HStack(alignment: .firstTextBaseline) {
                    Text(group.title).font(.subheadline.weight(.semibold)).lineLimit(1)
                    Spacer(minLength: 8)
                    Text(group.latestAt, format: .relative(presentation: .named))
                        .font(.caption).foregroundStyle(.secondary)
                }
                Text(group.latestHeadline).font(.subheadline).lineLimit(2)
                HStack(spacing: 6) {
                    Text(group.summary)
                    if group.muted { Image(systemName: "speaker.slash").accessibilityLabel("Muted") }
                }
                .font(.caption.weight(.medium))
                .foregroundStyle(group.noticeLevel == .changed ? Color.brand : Color.inkSecondary)
            }
        }
        .padding(.vertical, 2)
        .accessibilityElement(children: .combine)
    }
}

private struct ExitRow: View {
    let exit: UnresolvedExit

    private var isStop: Bool { (exit.pctChange ?? 0) < 0 || exit.triggerType.contains("stop") }

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: isStop ? "exclamationmark.octagon.fill" : "flag.checkered")
                .font(.title3).foregroundStyle(isStop ? Color.loss : .gain)
                .frame(width: 42, height: 42)
                .background((isStop ? Color.loss : .gain).opacity(0.12), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            VStack(alignment: .leading, spacing: 3) {
                // The day the rule was met, first.
                Text(exit.barDate ?? exit.signaledAt.map { String($0.prefix(10)) } ?? "").eyebrowStyle()
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(exit.symbol).font(.headline.monospaced())
                    Text(exit.headline).font(.subheadline)
                }
                Text(exit.strategyTitle).font(.caption).foregroundStyle(.inkSecondary).lineLimit(1)
            }
        }
        .padding(.vertical, 2)
        .accessibilityElement(children: .combine)
    }
}
