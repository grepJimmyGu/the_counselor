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
        #if DEBUG
        // `-demo` shows the signed-in screens with sample data; see DemoData.
        if session == nil, ProcessInfo.processInfo.arguments.contains("-demo") {
            _session = State(initialValue: AppSession.demo())
            return
        }
        #endif
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
