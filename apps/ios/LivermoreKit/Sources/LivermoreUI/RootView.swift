import LivermoreKit
import SwiftUI

/// The whole app.
///
/// Research is open without an account, as it is on the website — the backend
/// serves the anonymous tier. Signing in happens in the Account tab and is
/// what the Strategies and Actions tabs need.
public struct RootView: View {
    @State private var session: AppSession
    @Environment(\.scenePhase) private var scenePhase

    public init(session: AppSession? = nil) {
        #if DEBUG
        // `-demo` shows the signed-in screens with sample data; see DemoData.
        if session == nil, ProcessInfo.processInfo.arguments.contains("-demo") {
            _session = State(initialValue: AppSession.demo())
            return
        }
        // `-serverURL http://127.0.0.1:8000` points the app at a backend on this
        // Mac, and `-googleClientID <id>` tries Google sign-in with a client ID
        // that is not yet in APIEnvironment. Launch arguments land in UserDefaults.
        if session == nil {
            let defaults = UserDefaults.standard
            _session = State(initialValue: AppSession(
                serverURL: defaults.string(forKey: "serverURL").flatMap(URL.init) ?? APIEnvironment.production,
                googleClientID: defaults.string(forKey: "googleClientID") ?? APIEnvironment.googleClientID
            ))
            return
        }
        #endif
        _session = State(initialValue: session ?? AppSession())
    }

    public var body: some View {
        MainTabView()
        .environment(session)
        .tint(.brand)
        .task(id: session.isSignedIn) {
            await session.refreshEntitlements()
        }
        .alert(
            "Sign in with \(session.biometry?.name ?? "Face ID") next time?",
            isPresented: Binding(
                get: { session.biometricOffer != nil },
                set: { if !$0 { session.declineBiometricOffer() } }
            ),
            presenting: session.biometricOffer
        ) { offer in
            // The credential is passed in rather than read back from the
            // session, so the order SwiftUI clears the alert in cannot lose it.
            Button("Use \(session.biometry?.name ?? "Face ID")") { session.acceptBiometricOffer(offer) }
            Button("Not now", role: .cancel) { session.declineBiometricOffer() }
        } message: { _ in
            Text("Your password is kept in this device's Keychain and released only after \(session.biometry?.name ?? "Face ID").")
        }
        // Prices are only polled while the app is in front.
        .onChange(of: scenePhase, initial: true) { _, phase in
            session.quotes.setActive(phase != .background)
        }
    }
}
