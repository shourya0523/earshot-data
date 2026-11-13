import SwiftUI
import EarshotCore

@main
struct EarshotApp: App {
    @State private var model = AppModel()
    var body: some Scene {
        WindowGroup {
            RootView().environment(model)
        }
    }
}

struct RootView: View {
    @Environment(AppModel.self) var model
    var body: some View {
        TabView {
            Tab("Connect", systemImage: "dot.radiowaves.left.and.right") { ConnectView() }
            Tab("Timeline", systemImage: "list.bullet.rectangle") { TimelineView() }
                .badge(model.unlabeledTaps.count)
            Tab("Recall", systemImage: "questionmark.bubble") { RecallView() }
                .badge(model.unlabeledTaps.count + model.confirmItems.count)
            Tab("Draft", systemImage: "doc.text") { DraftView() }
            Tab("Handoff", systemImage: "person.2.wave.2") { HandoffView() }
            Tab("Ledger", systemImage: "lock.shield") { LedgerView() }
            Tab("Settings", systemImage: "gearshape") { SettingsView() }
        }
    }
}

/// Receipt sheet: the quote, time and source behind any value.
struct ReceiptView: View {
    let event: EarshotEvent
    let clock: CallClock?
    var body: some View {
        NavigationStack {
            List {
                Section("What") {
                    LabeledContent("Type", value: event.type.rawValue)
                    ForEach(event.fields.sorted(by: { $0.key < $1.key }), id: \.key) { k, v in LabeledContent(k, value: v) }
                }
                Section("Receipt") {
                    LabeledContent("Time", value: clock?.clock(event.tMs) ?? event.time)
                    LabeledContent("Source", value: ChartModel.srcLabel(event))
                    if let q = event.quote { Text("“\(q)”").italic() } else if event.source == .tap { Text("Tap only, nothing heard") }
                    if let s = event.rawSpan { LabeledContent("Raw span", value: s) }
                    if let ts = event.tapSource { LabeledContent("Tap from", value: ts) }
                    if let by = event.enteredBy { LabeledContent("Entered by", value: by) }
                    LabeledContent("Confidence", value: String(format: "%.2f", event.confidence))
                    LabeledContent("Models", value: "\(event.models.asr) · \(event.models.extract)")
                }
                if let r = event.receipts, !r.isEmpty {
                    Section("Per field") {
                        ForEach(r.sorted(by: { $0.key < $1.key }), id: \.key) { k, v in
                            VStack(alignment: .leading) {
                                Text(k).font(.caption).foregroundStyle(.secondary)
                                Text("“\(v.quote)” (\(v.rawSpan))")
                            }
                        }
                    }
                }
            }
            .navigationTitle("Receipt \(event.id)")
        }
    }
}
