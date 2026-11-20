import LivermoreKit
import SwiftUI

/// The user's own limits and words for their agent.
struct AgentSettingsView: View {
    @Environment(AppSession.self) private var session
    @Environment(\.dismiss) private var dismiss

    @State private var moveAlert = 4.0
    @State private var maxPosition = 25.0
    @State private var notes = ""
    @State private var emailAlerts = true
    @State private var loaded = false
    @State private var isSaving = false

    private static let notesLimit = 1000

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Stepper(value: $moveAlert, in: 1...20, step: 0.5) {
                        DetailRow("A move in one day of", "\(moveAlert.formatted(.number.precision(.fractionLength(0...1))))%")
                    }
                    .accessibilityIdentifier("agent-move-alert")
                } header: {
                    Text("Tell me about")
                } footer: {
                    Text("For anything on your watchlist or in your holdings, up or down.")
                }
                Section {
                    Stepper(value: $maxPosition, in: 5...100, step: 5) {
                        DetailRow("One holding above", "\(maxPosition.formatted(.number.precision(.fractionLength(0))))%")
                    }
                    .accessibilityIdentifier("agent-max-position")
                } footer: {
                    Text("Of everything you hold at your linked broker. When a holding passes it, the agent works out the sale that would bring it back and drafts that order for you to review.")
                }
                Section {
                    Toggle("Email me what it finds", isOn: $emailAlerts)
                        .accessibilityIdentifier("agent-email-alerts")
                } footer: {
                    Text("When a scheduled check finds something to watch, one email lists it. Checks you start yourself never email you. Applies while Watch around the clock is on.")
                }
                Section {
                    TextEditor(text: $notes)
                        .frame(minHeight: 110)
                        .accessibilityIdentifier("agent-notes")
                } header: {
                    Text("How you invest")
                } footer: {
                    Text("In your own words: what you are trying to do, what you never do. Your agent reads this before it answers you. \(notes.count)/\(Self.notesLimit)")
                }
                if let failure = session.agent.failure {
                    Section { Notice(text: failure.message, systemImage: "exclamationmark.triangle.fill", tint: .caution) }
                }
            }
            .screenBackground()
            .navigationTitle("Agent settings")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save", action: save)
                        .disabled(isSaving || notes.count > Self.notesLimit)
                        .accessibilityIdentifier("agent-settings-save")
                }
            }
            .onAppear {
                guard !loaded, let profile = session.agent.profile else { return }
                loaded = true
                moveAlert = profile.moveAlertPct
                maxPosition = profile.maxPositionPct
                notes = profile.notes
                emailAlerts = profile.emailAlerts ?? true
            }
        }
    }

    private func save() {
        isSaving = true
        Task {
            await session.agent.update(
                emailAlerts: emailAlerts, moveAlertPct: moveAlert, maxPositionPct: maxPosition, notes: notes
            )
            isSaving = false
            if session.agent.failure == nil { dismiss() }
        }
    }
}
