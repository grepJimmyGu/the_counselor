import LivermoreAPI
import LivermoreKit
import SwiftUI

/// Where the company sits in its supply chain and whether it is a chokepoint.
struct SupplyChainView: View {
    @Environment(AppSession.self) private var session
    let symbol: String

    @State private var summary: SupplyChainSummary?
    @State private var error: ResearchError?

    var body: some View {
        Group {
            if let summary {
                loaded(summary)
            } else if let error {
                ContentUnavailableView {
                    Label("Supply chain unavailable", systemImage: "point.3.connected.trianglepath.dotted")
                } description: {
                    Text(error.message)
                } actions: {
                    Button("Try again") { Task { await load() } }
                }
            } else {
                ProgressView("Loading the supply chain for \(symbol)…")
            }
        }
        .navigationTitle("Supply chain")
        .task { await load() }
    }

    private func load() async {
        error = nil
        do throws(ResearchError) {
            summary = try await session.research.supplyChain(symbol)
        } catch {
            self.error = error
        }
    }

    private func loaded(_ summary: SupplyChainSummary) -> some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                if let computed = summary.computedAt {
                    Text("AS OF \(computed.prefix(10))")
                        .font(.caption2.weight(.semibold)).tracking(0.8).foregroundStyle(.secondary)
                }
                Card("Verdict") {
                    Text(summary.verdict.replacingOccurrences(of: "_", with: " ").capitalized)
                        .font(.title3.weight(.semibold))
                    if let message = summary.message { Text(message).font(.subheadline) }
                    if let statement = summary.breakStatement { Text(statement).font(.subheadline) }
                    let facts: [(String, String?)] = [
                        ("Vertical", summary.vertical), ("Layer", summary.layer),
                        ("Stage", summary.stage), ("Confidence", summary.confidence),
                    ]
                    ForEach(facts.compactMap { title, value in value.map { (title, $0) } }, id: \.0) { title, value in
                        LabeledContent(title, value: value.replacingOccurrences(of: "_", with: " ").capitalized)
                            .font(.subheadline)
                    }
                }
                if let tests = summary.tests, !tests.isEmpty {
                    Card("Chokepoint tests") {
                        ForEach(Array(tests.enumerated()), id: \.offset) { index, test in
                            if index > 0 { Divider() }
                            VStack(alignment: .leading, spacing: 4) {
                                HStack {
                                    Text(test.test.replacingOccurrences(of: "_", with: " ").capitalized)
                                        .font(.subheadline.weight(.semibold))
                                    Spacer()
                                    Text(test.verdict.replacingOccurrences(of: "_", with: " ").uppercased())
                                        .font(.caption2.weight(.bold)).foregroundStyle(.secondary)
                                }
                                Text(test.rationale).font(.footnote)
                                Text("Evidence: \(test.evidenceTier.replacingOccurrences(of: "_", with: " "))")
                                    .font(.caption2).foregroundStyle(.tertiary)
                            }
                        }
                    }
                }
            }
            .padding()
        }
        .background(Color.groupedBackground)
    }
}
