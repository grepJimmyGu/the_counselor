import LivermoreKit
import SwiftUI

#if os(iOS)
import UIKit
#else
import AppKit
#endif

// The website's palette (apps/web/src/app/globals.css), converted from OKLCH,
// with its own dark values — not an inverted copy of the light ones.
extension Color {
    init(light: UInt32, dark: UInt32) {
        func components(_ hex: UInt32) -> (CGFloat, CGFloat, CGFloat) {
            (CGFloat((hex >> 16) & 0xFF) / 255, CGFloat((hex >> 8) & 0xFF) / 255, CGFloat(hex & 0xFF) / 255)
        }
        let l = components(light), d = components(dark)
        #if os(iOS)
        self.init(uiColor: UIColor { traits in
            let c = traits.userInterfaceStyle == .dark ? d : l
            return UIColor(red: c.0, green: c.1, blue: c.2, alpha: 1)
        })
        #else
        self.init(nsColor: NSColor(name: nil) { appearance in
            let c = appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? d : l
            return NSColor(red: c.0, green: c.1, blue: c.2, alpha: 1)
        })
        #endif
    }

    /// Livermore blue: actions, selection, the strategy line on a chart.
    static let brand = Color(light: 0x0063D7, dark: 0x3B8EF5)
    /// Up, and good. Never used for anything that is not a gain or a pass.
    static let gain = Color(light: 0x007D33, dark: 0x22C373)
    /// Down, and bad.
    static let loss = Color(light: 0xC90019, dark: 0xF94144)
    /// Needs attention; neither good nor bad yet.
    static let caution = Color(light: 0xC37F00, dark: 0xF5AE39)

    /// The page behind everything.
    static let canvas = Color(light: 0xF6F9FB, dark: 0x090E11)
    /// A card on the page.
    static let surface = Color(light: 0xFFFFFF, dark: 0x0F171C)
    /// A tile or track inside a card.
    static let well = Color(light: 0xEFF2F4, dark: 0x182125)
    static let hairline = Color(light: 0xD6DBE0, dark: 0x293237)
    static let inkSecondary = Color(light: 0x636A71, dark: 0x9EA6AE)

    // Older names, kept so screens that have not been restyled still compile.
    static var groupedBackground: Color { .canvas }
    static var cardBackground: Color { .surface }
}

extension ShapeStyle where Self == Color {
    static var brand: Color { Color.brand }
    static var gain: Color { Color.gain }
    static var loss: Color { Color.loss }
    static var caution: Color { Color.caution }
    static var inkSecondary: Color { Color.inkSecondary }
}

extension Double {
    /// Gain colour when up, loss colour when down, secondary when flat.
    var changeColor: Color { self > 0 ? .gain : self < 0 ? .loss : .inkSecondary }
}

extension ScoreStatus {
    var color: Color {
        switch self {
        case .strong: .gain
        case .neutral: .caution
        case .weak: .loss
        }
    }

    var label: String { rawValue.capitalized }
}

enum Metrics {
    static let cardRadius: CGFloat = 18
    static let tileRadius: CGFloat = 12
    static let cardPadding: CGFloat = 16
    static let screenPadding: CGFloat = 16
    static let sectionSpacing: CGFloat = 14
}

extension Font {
    /// Small capitals above a headline: a date, a category.
    static let eyebrow = Font.caption2.weight(.semibold)
    /// The one number a screen is about.
    static let hero = Font.system(size: 40, weight: .bold).monospacedDigit()
}

extension View {
    /// Uppercase, tracked, secondary — the byline treatment for dates and
    /// categories, which stay legible rather than buried.
    func eyebrowStyle() -> some View {
        font(.eyebrow).tracking(0.8).textCase(.uppercase).foregroundStyle(.inkSecondary)
    }

    /// The app's page background behind a scrolling screen or a list.
    func screenBackground() -> some View {
        scrollContentBackground(.hidden).background(Color.canvas.ignoresSafeArea())
    }
}
