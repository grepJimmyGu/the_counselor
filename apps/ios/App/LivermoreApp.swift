import LivermoreUI
import SwiftUI

// The app target is deliberately this small: everything else lives in the
// LivermoreKit package, where it builds and tests without Xcode.
@main
struct LivermoreApp: App {
    var body: some Scene {
        WindowGroup {
            RootView()
        }
    }
}
