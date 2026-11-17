import LivermoreKit
import SwiftUI

struct AccountView: View {
    @Environment(AppSession.self) private var session

    var body: some View {
        NavigationStack {
            List {
                if case .signedIn(let user) = session.state {
                    Section("Signed in as") {
                        if let name = user.displayName, !name.isEmpty {
                            LabeledContent("Name", value: name)
                        }
                        LabeledContent("Email", value: user.email)
                        LabeledContent("Plan", value: session.tier?.capitalized ?? "—")
                    }
                }
                Section {
                    Button("Sign out", role: .destructive) {
                        session.signOut()
                    }
                    .accessibilityIdentifier("sign-out-button")
                }
            }
            .navigationTitle("Account")
        }
    }
}
