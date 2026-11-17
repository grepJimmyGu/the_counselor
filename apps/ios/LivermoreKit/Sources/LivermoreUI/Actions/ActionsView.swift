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

            if !inbox.notices.isEmpty {
                Section("Notices") {
                    ForEach(inbox.notices, id: \.id) { notice in
                        NoticeRow(notice: notice)
                            .swipeActions {
                                Button("Read") { acknowledge(notice) }.tint(.brand)
                            }
                    }
                }
            }
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

    private func acknowledge(_ notice: PendingNotice) {
        Task { try? await inbox.acknowledge(notice) }
    }
}

private struct ExitRow: View {
    let exit: UnresolvedExit

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            // The day the rule was met, first.
            Text((exit.barDate ?? exit.signaledAt.map { String($0.prefix(10)) } ?? "").uppercased())
                .font(.caption2.weight(.semibold)).tracking(0.8).foregroundStyle(.secondary)
            HStack(alignment: .firstTextBaseline) {
                Text(exit.symbol).font(.headline.monospaced())
                Text(exit.headline).font(.subheadline)
            }
            Text(exit.strategyTitle).font(.caption).foregroundStyle(.secondary).lineLimit(1)
        }
        .padding(.vertical, 2)
        .accessibilityElement(children: .combine)
    }
}

private struct NoticeRow: View {
    @Environment(AppSession.self) private var session
    let notice: PendingNotice

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(notice.createdAt.formatted(date: .abbreviated, time: .shortened).uppercased())
                .font(.caption2.weight(.semibold)).tracking(0.8).foregroundStyle(.secondary)
            Text(notice.title).font(.subheadline.weight(.semibold))
            Text(notice.body).font(.subheadline).foregroundStyle(.secondary)
            Button("Mark as read") {
                Task { try? await session.inbox.acknowledge(notice) }
            }
            .font(.caption.weight(.medium))
            .buttonStyle(.borderless)
        }
        .padding(.vertical, 2)
    }
}
