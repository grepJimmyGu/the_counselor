import SwiftUI

/// "Continue with Google", to Google's sign-in branding rules: the standard
/// colour "G" on a plain surface, with one of the approved labels.
struct GoogleButton: View {
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                GoogleLogo().frame(width: 20, height: 20)
                Text("Continue with Google")
            }
            .font(.body.weight(.semibold))
            .foregroundStyle(Color.primary)
            .frame(maxWidth: .infinity, minHeight: 50)
            .background(Color.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).strokeBorder(Color.hairline))
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("google-sign-in-button")
    }
}

/// Google's "G". The four shapes and colours are the ones in Google's own
/// sign-in button artwork, on its 48-unit grid.
struct GoogleLogo: View {
    private static let shapes: [(path: Path, color: Color)] = [
        ("M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z", 0xEA4335),
        ("M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z", 0x4285F4),
        ("M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z", 0xFBBC05),
        ("M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z", 0x34A853),
    ].map { (SVGPath.path($0.0), Color(hex: $0.1)) }

    var body: some View {
        Canvas { context, size in
            let scale = min(size.width, size.height) / 48
            for shape in Self.shapes {
                context.fill(shape.path.applying(CGAffineTransform(scaleX: scale, y: scale)), with: .color(shape.color))
            }
        }
        .accessibilityHidden(true)
    }
}

private extension Color {
    init(hex: UInt32) {
        self.init(
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255
        )
    }
}

/// Reads the subset of SVG path syntax that logo artwork uses: move, line,
/// horizontal, vertical, cubic and smooth-cubic segments, and close.
enum SVGPath {
    static func path(_ data: String) -> Path {
        let pattern = try! Regex(#"[MmLlHhVvCcSsZz]|[-+]?(?:\d*\.\d+|\d+)"#)
        let tokens = data.matches(of: pattern).map { String(data[$0.range]) }
        var path = Path()
        var current = CGPoint.zero
        var lastControl: CGPoint?
        var command: Character = "M"
        var index = 0

        func number() -> CGFloat {
            defer { index += 1 }
            return index < tokens.count ? CGFloat(Double(tokens[index]) ?? 0) : 0
        }

        while index < tokens.count {
            if let letter = tokens[index].first, letter.isLetter {
                command = letter
                index += 1
                if letter == "Z" || letter == "z" {
                    path.closeSubpath()
                    continue
                }
            }
            let relative = command.isLowercase
            let origin = current
            func point() -> CGPoint {
                let x = number(), y = number()
                return relative ? CGPoint(x: origin.x + x, y: origin.y + y) : CGPoint(x: x, y: y)
            }

            switch command {
            case "M", "m":
                current = point()
                path.move(to: current)
                // Further pairs after a move are lines.
                command = relative ? "l" : "L"
                lastControl = nil
            case "L", "l":
                current = point()
                path.addLine(to: current)
                lastControl = nil
            case "H", "h":
                let x = number()
                current.x = relative ? origin.x + x : x
                path.addLine(to: current)
                lastControl = nil
            case "V", "v":
                let y = number()
                current.y = relative ? origin.y + y : y
                path.addLine(to: current)
                lastControl = nil
            case "C", "c":
                let first = point(), second = point(), end = point()
                path.addCurve(to: end, control1: first, control2: second)
                lastControl = second
                current = end
            case "S", "s":
                // The first control point mirrors the previous segment's last.
                let first = lastControl.map { CGPoint(x: 2 * origin.x - $0.x, y: 2 * origin.y - $0.y) } ?? origin
                let second = point(), end = point()
                path.addCurve(to: end, control1: first, control2: second)
                lastControl = second
                current = end
            default:
                index += 1
            }
        }
        return path
    }
}
