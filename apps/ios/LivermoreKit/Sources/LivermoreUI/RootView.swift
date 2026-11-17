import LivermoreKit
import SwiftUI

/// The whole app: sign-in when signed out, the tab shell when signed in.
public struct RootView: View {
    @State private var session: AppSession

    public init(session: AppSession? = nil) {
        _session = State(initialValue: session ?? AppSession())
    }

    public var body: some View {
        Group {
            if session.isSignedIn {
                MainTabView()
            } else {
                SignInView()
            }
        }
        .environment(session)
        .task(id: session.isSignedIn) {
            await session.refreshEntitlements()
        }
    }
}
