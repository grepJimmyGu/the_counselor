import LivermoreKit
import SwiftUI

/// Step one of the options builder: what the user wants from the stock.
///
/// The chain is fetched here, while the user reads the four cards, so the
/// plan on the next screen appears at once, and a stock with no options says
/// so before a card is chosen rather than after.
struct OptionGoalView: View {
    @Environment(AppSession.self) private var session
    let symbol: String

    @State private var chain: OptionChain?
    @State private var failure: APIFailure?

    var body: some View {
        Group {
            if !session.isSignedIn {
                ContentUnavailableView {
                    Label("Sign in to build an option plan", systemImage: "person.crop.circle")
                } description: {
                    Text("Option prices and saved plans need an account. Sign in from the Account tab.")
                }
            } else if let failure {
                ContentUnavailableView {
                    Label("No option plan for \(symbol) right now", systemImage: "exclamationmark.triangle")
                } description: {
                    Text(OptionsService.message(for: failure))
                } actions: {
                    Button("Try again") { Task { await load() } }.buttonStyle(.borderedProminent)
                }
            } else {
                cards
            }
        }
        .screenBackground()
        .navigationTitle("Options")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .task(id: session.isSignedIn) {
            if session.isSignedIn, chain == nil { await load() }
        }
    }

    private var cards: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: Metrics.sectionSpacing) {
                if session.isDemo { SampleDataNotice().padding(.horizontal, 4) }
                Text("What do you want from \(symbol)?")
                    .font(.title2.weight(.bold))
                    .padding(.top, 4)
                ForEach(OptionStrategy.allCases) { strategy in
                    NavigationLink {
                        OptionPlanView(symbol: symbol, strategy: strategy, firstChain: chain)
                    } label: {
                        GoalCard(strategy: strategy, symbol: symbol)
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("option-goal-\(strategy.rawValue)")
                }
            }
            .padding(Metrics.screenPadding)
        }
    }

    private func load() async {
        failure = nil
        do throws(APIFailure) {
            chain = try await session.options.chain(symbol)
        } catch {
            if error == .notSignedIn {
                session.signOut()
            } else {
                failure = error
            }
        }
    }
}

private struct GoalCard: View {
    let strategy: OptionStrategy
    let symbol: String

    private var icon: String {
        switch strategy {
        case .longCall: "arrow.up.right"
        case .longPut: "arrow.down.right"
        case .coveredCall: "dollarsign.arrow.circlepath"
        case .protectivePut: "shield.lefthalf.filled"
        }
    }

    var body: some View {
        Card {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: icon)
                    .font(.title3.weight(.semibold)).foregroundStyle(.brand)
                    .frame(width: 44, height: 44)
                    .background(Color.brand.opacity(0.10), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                VStack(alignment: .leading, spacing: 6) {
                    Text(strategy.goal).font(.headline)
                    Text(strategy.explanation(symbol: symbol))
                        .font(.subheadline).foregroundStyle(.inkSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                    HStack(spacing: 6) {
                        Tag(strategy.name, tint: .brand)
                        Tag(strategy.needs)
                    }
                }
                Spacer(minLength: 0)
                Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(.tertiary)
            }
        }
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}
