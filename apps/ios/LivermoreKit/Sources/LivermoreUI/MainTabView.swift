import LivermoreKit
import Observation
import SwiftUI

enum AppTab: Hashable {
    case research, strategies, agent, actions, account
}

/// Which tab is showing. Shared so that one screen can send the user to
/// another tab, as the agent does for exits waiting in Actions.
@MainActor
@Observable
final class TabRouter {
    var tab: AppTab = .research
}

/// The five areas of the app.
struct MainTabView: View {
    @Environment(AppSession.self) private var session
    @State private var router = TabRouter()

    var body: some View {
        TabView(selection: $router.tab) {
            ResearchView()
                .tabItem { Label("Research", systemImage: "magnifyingglass") }
                .tag(AppTab.research)

            StrategiesView()
                .tabItem { Label("Strategies", systemImage: "chart.line.uptrend.xyaxis") }
                .tag(AppTab.strategies)

            AgentView()
                .tabItem { Label("Agent", systemImage: "sparkles") }
                .badge(session.agent.attentionCount)
                .tag(AppTab.agent)

            ActionsView()
                .tabItem { Label("Actions", systemImage: "bell.badge") }
                .badge(session.inbox.waitingCount)
                .tag(AppTab.actions)

            Group {
                if session.isSignedIn {
                    AccountView()
                } else {
                    SignInView()
                }
            }
            .tabItem { Label("Account", systemImage: "person.crop.circle") }
            .tag(AppTab.account)
        }
        .environment(router)
        // The badges have to be right before their tabs are ever opened.
        .task(id: session.isSignedIn) {
            if session.isSignedIn {
                await session.inbox.refresh()
                await session.agent.load()
            }
        }
    }
}
