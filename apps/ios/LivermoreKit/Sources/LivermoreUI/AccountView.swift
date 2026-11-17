import LivermoreKit
import SwiftUI

struct AccountView: View {
    @Environment(AppSession.self) private var session

    var body: some View {
        NavigationStack {
            List {
                if session.isDemo { SampleDataNotice() }
                if case .signedIn(let user) = session.state {
                    Section {
                        HStack(spacing: 14) {
                            let name = user.displayName.flatMap { $0.isEmpty ? nil : $0 } ?? user.email
                            Text(String(name.prefix(1)).uppercased())
                                .font(.title2.weight(.bold)).foregroundStyle(.white)
                                .frame(width: 56, height: 56)
                                .background(Color.brand, in: Circle())
                            VStack(alignment: .leading, spacing: 4) {
                                Text(name).font(.headline).lineLimit(1)
                                if name != user.email {
                                    Text(user.email).font(.subheadline).foregroundStyle(.inkSecondary).lineLimit(1)
                                }
                                if let tier = session.tier { Tag("\(tier.capitalized) plan", tint: .brand) }
                            }
                        }
                        .padding(.vertical, 4)
                        .accessibilityElement(children: .combine)
                    }
                }
                Section {
                    NavigationLink {
                        BrokerageView()
                    } label: {
                        Label("Brokerage", systemImage: "building.columns")
                    }
                } footer: {
                    Text("Link Robinhood, Charles Schwab or another broker to see your holdings and send orders you have confirmed.")
                }
                Section {
                    Button("Sign out", role: .destructive) {
                        session.signOut()
                    }
                    .accessibilityIdentifier("sign-out-button")
                }
            }
            .screenBackground()
            .navigationTitle("Account")
        }
    }
}
