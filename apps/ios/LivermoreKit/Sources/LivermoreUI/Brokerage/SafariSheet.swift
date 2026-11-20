import SwiftUI

#if os(iOS)
import SafariServices

/// An in-app browser for the brokerage sign-in. The page belongs to the
/// broker and the aggregator: the app cannot read what is typed into it.
struct SafariSheet: UIViewControllerRepresentable {
    let url: URL

    func makeUIViewController(context: Context) -> SFSafariViewController {
        let controller = SFSafariViewController(url: url)
        controller.dismissButtonStyle = .done
        return controller
    }

    func updateUIViewController(_ controller: SFSafariViewController, context: Context) {}
}
#endif

/// A link target that can drive `.sheet(item:)`.
struct BrowserDestination: Identifiable {
    let url: URL
    var id: URL { url }
}
