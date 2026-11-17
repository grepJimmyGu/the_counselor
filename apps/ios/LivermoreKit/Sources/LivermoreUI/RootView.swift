import LivermoreKit
import SwiftUI

/// The whole app.
///
/// Research is open without an account, as it is on the website — the backend
/// serves the anonymous tier. Signing in happens in the Account tab and is
/// what the Strategies and Actions tabs need.
public struct RootView: View {
    @State private var session: AppSession

    public init(session: AppSession? = nil) {
        _session = State(initialValue: session ?? AppSession())
    }

    public var body: some View {
        MainTabView()
        .environment(session)
        .task(id: session.isSignedIn) {
            await session.refreshEntitlements()
        }
    }
}
