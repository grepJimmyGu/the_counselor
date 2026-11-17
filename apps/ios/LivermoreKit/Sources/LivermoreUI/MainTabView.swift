import LivermoreKit
import SwiftUI

/// The four areas of the app. Actions is filled in by the next slice.
struct MainTabView: View {
    @Environment(AppSession.self) private var session

    var body: some View {
        TabView {
            ResearchView()
                .tabItem { Label("Research", systemImage: "magnifyingglass") }

            StrategiesView()
                .tabItem { Label("Strategies", systemImage: "chart.line.uptrend.xyaxis") }

            ComingSoonView(
                title: "Actions",
                systemImage: "bell.badge",
                detail: "What your strategies are asking you to do, and your linked brokerage."
            )
            .tabItem { Label("Actions", systemImage: "bell.badge") }

            Group {
                if session.isSignedIn {
                    AccountView()
                } else {
                    SignInView()
                }
            }
            .tabItem { Label("Account", systemImage: "person.crop.circle") }
        }
    }
}

private struct ComingSoonView: View {
    let title: String
    let systemImage: String
    let detail: String

    var body: some View {
        NavigationStack {
            ContentUnavailableView {
                Label(title, systemImage: systemImage)
            } description: {
                Text(detail)
            } actions: {
                Text("Not built yet")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            .navigationTitle(title)
        }
    }
}
