import SwiftUI
import EarshotCore

/// After the call: every unlabeled tap with the transcript around it, and
/// every "heard, please confirm" item. The medic labels by typing (or
/// dictation via the keyboard mic). Labels are marked as the medic's.
struct RecallView: View {
    @Environment(AppModel.self) var model
    @State private var editing: EarshotEvent?
    @State private var suggestions: [String: TapLabelSuggestion] = [:]
    var body: some View {
        NavigationStack {
            List {
                Section("Unlabeled taps") {
                    if model.unlabeledTaps.isEmpty { Text("None").foregroundStyle(.secondary) }
                    ForEach(model.unlabeledTaps) { t in
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Marked at \(model.session?.clock.clock(t.tMs) ?? "") · \(t.tapSource ?? "tap")").font(.headline)
                            ForEach(model.session?.transcriptAround(t.tMs) ?? [], id: \.id) { s in
                                Text("[\(model.session?.clock.clock(s.startMs) ?? "")] \(s.text)").font(.caption).foregroundStyle(.secondary)
                            }
                            if let sg = suggestions[t.id] {
                                HStack {
                                    Text("Suggested: \(sg.text) — “\(sg.quote)” (\(sg.rawSpan))").font(.caption).foregroundStyle(.blue)
                                    Button("Accept") { model.label(tap: t, type: EventType(rawValue: sg.type) ?? .status, fields: ["label": sg.text, "quote": sg.quote]) }
                                }
                            }
                            HStack {
                                Button("Label…") { editing = t }.buttonStyle(.bordered)
                                if model.useFoundationModels && FoundationModelsLabeler.isAvailable && suggestions[t.id] == nil {
                                    Button("Suggest") {
                                        Task {
                                            let ctx = model.session?.transcriptAround(t.tMs, windowMs: 10000) ?? []
                                            if let s = await FoundationModelsLabeler.suggest(tap: t, context: ctx) { suggestions[t.id] = s }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                Section("Heard — please confirm") {
                    if model.confirmItems.isEmpty { Text("None").foregroundStyle(.secondary) }
                    ForEach(model.confirmItems) { e in
                        VStack(alignment: .leading) {
                            Text("“\(e.quote ?? "")”")
                            Text("\(model.session?.clock.clock(e.tMs) ?? "") · \(e.type.rawValue) · \(e.fields.map { "\($0.key)=\($0.value)" }.sorted().joined(separator: ", "))")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
                Section("Not heard") {
                    let c = model.chart
                    MissingRow(label: "Age", missing: c?.age == nil)
                    MissingRow(label: "Weight", missing: c?.weight == nil)
                    MissingRow(label: "Allergies", missing: c?.allergies.isEmpty ?? true)
                    MissingRow(label: "Chief complaint", missing: c?.chiefComplaint == nil && c?.found == nil)
                    MissingRow(label: "Arrival time", missing: c?.arrival == nil)
                }
            }
            .navigationTitle("Recall")
            .sheet(item: $editing) { t in LabelSheet(tap: t) }
        }
    }
}

struct MissingRow: View {
    let label: String; let missing: Bool
    var body: some View {
        if missing { Label("\(label): not heard", systemImage: "circle.dashed").foregroundStyle(.orange) }
    }
}

struct LabelSheet: View {
    @Environment(AppModel.self) var model
    @Environment(\.dismiss) var dismiss
    let tap: EarshotEvent
    @State private var type: EventType = .medication
    @State private var text = ""
    var body: some View {
        NavigationStack {
            Form {
                Picker("Type", selection: $type) {
                    ForEach([EventType.medication, .procedure, .vitals, .status], id: \.self) { Text($0.rawValue).tag($0) }
                }
                TextField("What happened (e.g. aspirin 324 mg PO)", text: $text, axis: .vertical)
                Text("Saved as entered by the medic, at the tap time \(model.session?.clock.clock(tap.tMs) ?? "").").font(.footnote)
            }
            .navigationTitle("Label tap")
            .toolbar {
                Button("Save") {
                    model.label(tap: tap, type: type, fields: ["label": text])
                    dismiss()
                }.disabled(text.trimmingCharacters(in: .whitespaces).isEmpty)
            }
        }
    }
}
