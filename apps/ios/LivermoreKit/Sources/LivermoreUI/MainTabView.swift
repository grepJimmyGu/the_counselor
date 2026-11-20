import LivermoreKit
import SwiftUI

/// The four areas of the app.
struct MainTabView: View {
    @Environment(AppSession.self) private var session

    var body: some View {
        TabView {
            ResearchView()
                .tabItem { Label("Research", systemImage: "magnifyingglass") }

            StrategiesView()
                .tabItem { Label("Strategies", systemImage: "chart.line.uptrend.xyaxis") }

            ActionsView()
                .tabItem { Label("Actions", systemImage: "bell.badge") }
                .badge(session.inbox.waitingCount)

            Group {
                if session.isSignedIn {
                    AccountView()
                } else {
                    SignInView()
                }
            }
            .tabItem { Label("Account", systemImage: "person.crop.circle") }
        }
        // The badge has to be right before the Actions tab is ever opened.
        .task(id: session.isSignedIn) {
            if session.isSignedIn { await session.inbox.refresh() }
        }
    }
}
