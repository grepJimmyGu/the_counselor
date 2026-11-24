import LivermoreKit
import SwiftUI

// MARK: - Card

/// A titled surface. The building block of every detail screen.
struct Card<Content: View, Accessory: View>: View {
    let title: String?
    let accessory: Accessory
    @ViewBuilder let content: Content

    init(_ title: String? = nil, @ViewBuilder accessory: () -> Accessory, @ViewBuilder content: () -> Content) {
        self.title = title
        self.accessory = accessory()
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let title {
                HStack(alignment: .firstTextBaseline) {
                    Text(title).font(.headline)
                    Spacer(minLength: 8)
                    accessory
                }
            }
            content
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(Metrics.cardPadding)
        .background(Color.surface, in: RoundedRectangle(cornerRadius: Metrics.cardRadius, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: Metrics.cardRadius, style: .continuous)
                .strokeBorder(Color.hairline.opacity(0.6), lineWidth: 0.5)
        )
    }
}

extension Card where Accessory == EmptyView {
    init(_ title: String? = nil, @ViewBuilder content: () -> Content) {
        self.init(title, accessory: { EmptyView() }, content: content)
    }
}

// MARK: - Small pieces

/// A label over a value.
struct Stat: View {
    let label: String
    let value: String
    let tint: Color?

    init(_ label: String, _ value: String, tint: Color? = nil) {
        self.label = label
        self.value = value
        self.tint = tint
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label).font(.caption).foregroundStyle(.inkSecondary).lineLimit(2)
            Text(value).font(.body.weight(.semibold).monospacedDigit()).foregroundStyle(tint ?? .primary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
    }
}

/// A stat in its own tinted tile, for grids of headline numbers.
struct StatTile: View {
    let label: String
    let value: String
    var tint: Color?
    var note: String?
    /// For values that are a phrase ("+3% to +12%") rather than one number.
    var compact = false

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label).font(.caption).foregroundStyle(.inkSecondary).lineLimit(1).minimumScaleFactor(0.8)
            Text(value).font((compact ? Font.callout : .title3).weight(.semibold).monospacedDigit()).foregroundStyle(tint ?? .primary)
                .lineLimit(1).minimumScaleFactor(0.7)
            if let note { Text(note).font(.caption2).foregroundStyle(.inkSecondary).lineLimit(1) }
        }
        // A value that shrinks to fit must not make its tile shorter than
        // the ones beside it.
        .frame(maxWidth: .infinity, minHeight: 46, alignment: .leading)
        .padding(12)
        .background(Color.well, in: RoundedRectangle(cornerRadius: Metrics.tileRadius, style: .continuous))
        .accessibilityElement(children: .combine)
    }
}

/// "▲ 1.23%" on a tinted capsule. `fraction` is 0.0123 for 1.23%.
struct ChangePill: View {
    let fraction: Double?
    var compact = false

    var body: some View {
        if let fraction {
            let color = fraction.changeColor
            HStack(spacing: 3) {
                Image(systemName: fraction > 0 ? "arrowtriangle.up.fill" : fraction < 0 ? "arrowtriangle.down.fill" : "minus")
                    .font(.system(size: compact ? 7 : 8))
                Text(String(format: "%.2f%%", abs(fraction) * 100))
            }
            .font((compact ? Font.caption : Font.subheadline).weight(.semibold).monospacedDigit())
            .foregroundStyle(color)
            .padding(.horizontal, compact ? 7 : 9).padding(.vertical, compact ? 3 : 4)
            .background(color.opacity(0.12), in: Capsule())
            .accessibilityLabel(String(format: "%@ %.2f percent", fraction >= 0 ? "up" : "down", abs(fraction) * 100))
        }
    }
}

/// A short label on a capsule: a category, a requirement, a status.
struct Tag: View {
    let text: String
    var tint: Color = .inkSecondary
    var systemImage: String?

    init(_ text: String, tint: Color = .inkSecondary, systemImage: String? = nil) {
        self.text = text
        self.tint = tint
        self.systemImage = systemImage
    }

    var body: some View {
        HStack(spacing: 4) {
            if let systemImage { Image(systemName: systemImage).font(.system(size: 9, weight: .semibold)) }
            Text(text)
        }
        .font(.caption2.weight(.semibold))
        .foregroundStyle(tint)
        .padding(.horizontal, 8).padding(.vertical, 4)
        .background(tint.opacity(0.12), in: Capsule())
    }
}

/// A note inside a card: a caveat, a warning, a confirmation.
struct Notice: View {
    let text: String
    var systemImage = "info.circle.fill"
    var tint: Color = .inkSecondary

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Image(systemName: systemImage).foregroundStyle(tint)
            Text(text).foregroundStyle(tint == .inkSecondary ? Color.primary : tint)
        }
        .font(.footnote)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(tint.opacity(0.10), in: RoundedRectangle(cornerRadius: Metrics.tileRadius, style: .continuous))
    }
}

/// A label and a value on one line, the value trailing.
struct DetailRow: View {
    let label: String
    let value: String
    var tint: Color?

    init(_ label: String, _ value: String, tint: Color? = nil) {
        self.label = label
        self.value = value
        self.tint = tint
    }

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label).foregroundStyle(.inkSecondary)
            Spacer(minLength: 12)
            Text(value).fontWeight(.medium).monospacedDigit().foregroundStyle(tint ?? .primary)
                .multilineTextAlignment(.trailing)
        }
        .font(.subheadline)
        .accessibilityElement(children: .combine)
    }
}

// MARK: - Scores

/// A 0–100 score as a ring, coloured by what the score means.
struct ScoreRing: View {
    let score: Int
    var size: CGFloat = 76
    var lineWidth: CGFloat = 8

    var body: some View {
        let color = StockScoring.status(score).color
        ZStack {
            Circle().stroke(Color.well, lineWidth: lineWidth)
            Circle()
                .trim(from: 0, to: CGFloat(min(max(score, 0), 100)) / 100)
                .stroke(color, style: StrokeStyle(lineWidth: lineWidth, lineCap: .round))
                .rotationEffect(.degrees(-90))
            Text("\(score)").font(.system(size: size * 0.36, weight: .bold).monospacedDigit())
        }
        .frame(width: size, height: size)
        .accessibilityLabel("\(score) out of 100")
    }
}

/// One named score: a bar, the number, and what it means in a word.
struct ScoreBar: View {
    let title: String
    let score: Int
    var detail: String?

    var body: some View {
        let status = StockScoring.status(score)
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(title).font(.subheadline.weight(.semibold))
                Spacer()
                Text(status.label).font(.caption.weight(.semibold)).foregroundStyle(status.color)
                Text("\(score)").font(.subheadline.weight(.bold).monospacedDigit())
            }
            GeometryReader { proxy in
                ZStack(alignment: .leading) {
                    Capsule().fill(Color.well)
                    Capsule().fill(status.color).frame(width: proxy.size.width * CGFloat(min(max(score, 0), 100)) / 100)
                }
            }
            .frame(height: 6)
            if let detail { Text(detail).font(.caption).foregroundStyle(.inkSecondary) }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(title): \(score) out of 100, \(status.label)")
    }
}

// MARK: - Sparkline

/// A month of closes as a line, coloured by whether it ended up or down.
struct Sparkline: View {
    let values: [Double]
    var lineWidth: CGFloat = 1.5

    private var color: Color {
        guard let first = values.first, let last = values.last else { return .inkSecondary }
        return (last - first).changeColor
    }

    var body: some View {
        GeometryReader { proxy in
            if values.count > 1, let low = values.min(), let high = values.max() {
                let span = max(high - low, .leastNonzeroMagnitude)
                let step = proxy.size.width / CGFloat(values.count - 1)
                let points = values.enumerated().map { index, value in
                    CGPoint(x: CGFloat(index) * step, y: proxy.size.height * (1 - CGFloat((value - low) / span)))
                }
                ZStack {
                    Path { path in
                        path.move(to: CGPoint(x: 0, y: proxy.size.height))
                        points.forEach { path.addLine(to: $0) }
                        path.addLine(to: CGPoint(x: proxy.size.width, y: proxy.size.height))
                        path.closeSubpath()
                    }
                    .fill(LinearGradient(colors: [color.opacity(0.22), color.opacity(0)], startPoint: .top, endPoint: .bottom))
                    Path { path in
                        path.move(to: points[0])
                        points.dropFirst().forEach { path.addLine(to: $0) }
                    }
                    .stroke(color, style: StrokeStyle(lineWidth: lineWidth, lineCap: .round, lineJoin: .round))
                }
            }
        }
        .accessibilityHidden(true)
    }
}

// MARK: - Position level bar

/// Where a position's price sits between its stop and its next target.
struct LevelBar: View {
    let stop: Double?
    let entry: Double
    let target: Double?
    let price: Double?

    // The bar spans stop → target; with one side missing it spans a
    // symmetric distance from entry so the marker still means something.
    private var low: Double { stop ?? (target.map { entry - ($0 - entry) } ?? entry * 0.9) }
    private var high: Double { target ?? (stop.map { entry + (entry - $0) } ?? entry * 1.1) }

    private func position(_ value: Double) -> CGFloat {
        CGFloat(min(max((value - low) / max(high - low, .leastNonzeroMagnitude), 0), 1))
    }

    var body: some View {
        VStack(spacing: 6) {
            GeometryReader { proxy in
                let width = proxy.size.width
                ZStack(alignment: .leading) {
                    Capsule().fill(
                        LinearGradient(
                            stops: [
                                .init(color: Color.loss.opacity(0.35), location: 0),
                                .init(color: Color.well, location: position(entry)),
                                .init(color: Color.gain.opacity(0.35), location: 1),
                            ],
                            startPoint: .leading, endPoint: .trailing
                        )
                    )
                    .frame(height: 6)
                    // Entry tick.
                    Rectangle().fill(Color.inkSecondary).frame(width: 1.5, height: 12)
                        .offset(x: width * position(entry) - 0.75)
                    if let price {
                        Circle().fill((price - entry).changeColor)
                            .overlay(Circle().stroke(Color.surface, lineWidth: 2))
                            .frame(width: 14, height: 14)
                            .offset(x: width * position(price) - 7)
                    }
                }
                .frame(height: 14)
            }
            .frame(height: 14)
            HStack {
                Text(stop.map { "Stop \(Fmt.price($0))" } ?? "No stop").foregroundStyle(stop == nil ? Color.inkSecondary : .loss)
                Spacer()
                Text(target.map { "Target \(Fmt.price($0))" } ?? "No target left").foregroundStyle(target == nil ? Color.inkSecondary : .gain)
            }
            .font(.caption2.weight(.semibold).monospacedDigit())
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(
            [stop.map { "Stop at \(Fmt.price($0))" }, price.map { "now \(Fmt.price($0))" }, target.map { "next target \(Fmt.price($0))" }]
                .compactMap { $0 }.joined(separator: ", ")
        )
    }
}

// MARK: - Buttons

/// The one thing a screen wants done.
struct PrimaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    var tint: Color = .brand

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.body.weight(.semibold))
            .frame(maxWidth: .infinity, minHeight: 50)
            .foregroundStyle(.white)
            .background(isEnabled ? tint : Color.inkSecondary.opacity(0.4), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .opacity(configuration.isPressed ? 0.85 : 1)
            .scaleEffect(configuration.isPressed ? 0.985 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

/// An alternative beside the primary action.
struct SecondaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.body.weight(.semibold))
            .frame(maxWidth: .infinity, minHeight: 50)
            .foregroundStyle(isEnabled ? Color.brand : .inkSecondary)
            .background(Color.brand.opacity(isEnabled ? 0.10 : 0.04), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .opacity(configuration.isPressed ? 0.7 : 1)
    }
}

extension View {
    /// Pins actions above the tab bar, on a blurred strip, so the next step
    /// is reachable without scrolling to the end of a long screen.
    func bottomBar<Bar: View>(@ViewBuilder _ bar: () -> Bar) -> some View {
        safeAreaInset(edge: .bottom, spacing: 0) {
            VStack(spacing: 8) { bar() }
                .padding(.horizontal, Metrics.screenPadding)
                .padding(.vertical, 10)
                .frame(maxWidth: .infinity)
                .background(.bar)
                .overlay(alignment: .top) { Rectangle().fill(Color.hairline.opacity(0.6)).frame(height: 0.5) }
        }
    }
}

// MARK: - Loading

/// A grey block standing in for content that is on its way.
struct SkeletonBlock: View {
    var height: CGFloat = 16
    var width: CGFloat?
    @State private var dim = false

    var body: some View {
        RoundedRectangle(cornerRadius: 6, style: .continuous)
            .fill(Color.well)
            .frame(width: width, height: height)
            .frame(maxWidth: width == nil ? .infinity : nil, alignment: .leading)
            .opacity(dim ? 0.45 : 1)
            .onAppear { withAnimation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true)) { dim = true } }
            .accessibilityHidden(true)
    }
}
