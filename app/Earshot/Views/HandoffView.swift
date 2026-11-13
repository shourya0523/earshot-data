import SwiftUI
import EarshotCore

/// 30-second nurse handoff card. The nurse's Accept records eTimes.12 and
/// stops the wall-time clock (which starts at arrival, eTimes.11).
struct HandoffView: View {
    @Environment(AppModel.self) var model
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    WallClock()
                    if let doc = model.session?.render()[2] {
                        Text(.init(doc.text.components(separatedBy: "\n---")[0]))
                            .font(.title3)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    HStack(spacing: 16) {
                        Button { model.markArrival() } label: {
                            Label(model.arrival == nil ? "Arrived at ED" : "Arrived \(model.session?.clock.clock(model.arrival!.tMs) ?? "")", systemImage: "mappin.and.ellipse")
                                .frame(maxWidth: .infinity, minHeight: 60)
                        }.buttonStyle(.bordered).disabled(model.arrival != nil || model.session == nil)
                        Button { model.nurseAccept() } label: {
                            Label(model.handoff == nil ? "Nurse: accept patient" : "Accepted \(model.session?.clock.clock(model.handoff!.tMs) ?? "")", systemImage: "signature")
                                .frame(maxWidth: .infinity, minHeight: 60)
                        }.buttonStyle(.borderedProminent).disabled(model.handoff != nil || model.session == nil)
                    }
                    Text("Arrival comes from the GPS geofence around \(model.destinationName); the Arrived button is the backup.")
                        .font(.footnote).foregroundStyle(.secondary)
                }.padding()
            }
            .navigationTitle("Handoff")
        }
    }
}

struct WallClock: View {
    @Environment(AppModel.self) var model
    var body: some View {
        TimelineViewClock { now in
            HStack {
                Text("Wall time").font(.headline)
                Spacer()
                Text(text(now)).font(.system(size: 40, weight: .semibold, design: .rounded).monospacedDigit())
                    .foregroundStyle(model.handoff == nil && model.arrival != nil ? .red : .primary)
            }
            .padding().background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
        }
    }
    func text(_ now: Date) -> String {
        guard let s = model.session, let a = model.arrival else { return "--:--" }
        let start = Double(s.clock.epochMs(a.tMs)) / 1000
        let end = model.handoff.map { Double(s.clock.epochMs($0.tMs)) / 1000 } ?? now.timeIntervalSince1970
        let sec = max(0, Int(end - start))
        return String(format: "%d:%02d", sec / 60, sec % 60)
    }
}
