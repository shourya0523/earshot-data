import SwiftUI
import EarshotCore

struct TimelineView: View {
    @Environment(AppModel.self) var model
    @State private var selected: EarshotEvent?
    var body: some View {
        NavigationStack {
            List {
                if let c = model.chart, c.dispatchChanged {
                    Section {
                        Label("Dispatched for “\(c.dispatch!.text)”, found “\((c.found ?? c.chiefComplaint)!.text)”", systemImage: "exclamationmark.triangle.fill")
                            .foregroundStyle(.orange)
                    }
                }
                Section { VitalsDueBanner() }
                Section("Timeline") {
                    if model.events.isEmpty { Text("Nothing yet. Taps and speech appear here as the call goes.").foregroundStyle(.secondary) }
                    ForEach(model.events, id: \.id) { e in
                        Button { selected = e } label: { EventRow(event: e, clock: model.session?.clock) }
                            .buttonStyle(.plain)
                    }
                }
            }
            .navigationTitle("Live timeline")
            .toolbar { Button("Mark", systemImage: "hand.tap") { model.manualMark() } }
            .sheet(item: $selected) { ReceiptView(event: $0, clock: model.session?.clock) }
        }
    }
}

extension EarshotEvent: @retroactive Identifiable {}

struct EventRow: View {
    let event: EarshotEvent
    let clock: CallClock?
    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Text(clock?.clock(event.tMs) ?? "").font(.body.monospacedDigit()).foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.body.weight(.medium))
                if let q = event.quote { Text("“\(q)”").font(.caption).foregroundStyle(.secondary).lineLimit(2) }
            }
            Spacer()
            Text(ChartModel.srcLabel(event)).font(.caption2).padding(4).background(.quaternary, in: RoundedRectangle(cornerRadius: 4))
            if event.needsConfirm { Image(systemName: "questionmark.circle").foregroundStyle(.orange) }
        }
    }
    var title: String {
        let f = event.fields
        switch event.type {
        case .vitals: return ChartModel.vitalsLine(event)
        case .medication: return [f["drug"], f["dose"], f["unit"], f["route"]].compactMap { $0 }.joined(separator: " ")
        case .procedure: return f["procedure"] ?? "procedure"
        case .tap: return event.isUnlabeledTap ? "Marked — no label" : "Tap"
        case .status: return [f["kind"], f["condition"] ?? f["symptom"] ?? f["drug"] ?? f["allergy"] ?? f["history"] ?? f["age"].map { "\($0) y/o" }].compactMap { $0 }.joined(separator: ": ")
        case .dispatch: return f.map { "\($0.key.replacingOccurrences(of: "_", with: " ")): \($0.value)" }.joined(separator: ", ")
        case .transport: return f.values.sorted().joined(separator: ", ")
        case .consent: return "Consent: \(f["consent"] ?? "")"
        case .arrival: return "Arrived at destination (eTimes.11)"
        case .handoff: return "Transfer of care (eTimes.12)"
        case .audioGap: return "Audio gap \(f["duration_ms"] ?? "") ms"
        }
    }
}

struct VitalsDueBanner: View {
    @Environment(AppModel.self) var model
    var body: some View {
        TimelineViewClock { now in
            let last = model.lastVitals.flatMap { e in model.session.map { Date(timeIntervalSince1970: Double($0.clock.epochMs(e.tMs)) / 1000) } }
            let mins = last.map { now.timeIntervalSince($0) / 60 } ?? now.timeIntervalSince(model.callStart) / 60
            let due = Double(model.vitalsIntervalMin)
            Label(mins >= due ? "Vitals due (every \(model.vitalsIntervalMin) min)" : String(format: "Next vitals in %.0f min", max(0, due - mins)),
                  systemImage: mins >= due ? "bell.badge.fill" : "heart.text.square")
                .foregroundStyle(mins >= due ? .red : .secondary)
        }
    }
}

/// Small wrapper so views can refresh every second.
struct TimelineViewClock<Content: View>: View {
    let content: (Date) -> Content
    init(@ViewBuilder _ content: @escaping (Date) -> Content) { self.content = content }
    var body: some View {
        SwiftUI.TimelineView(.periodic(from: .now, by: 1)) { ctx in content(ctx.date) }
    }
}
