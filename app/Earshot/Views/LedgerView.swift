import SwiftUI
import EarshotCore

struct LedgerView: View {
    @Environment(AppModel.self) var model
    var body: some View {
        NavigationStack {
            List {
                Section {
                    Label("Audio sent: \(model.ledger.audioBytesSent) bytes", systemImage: "waveform.slash").font(.title3.bold())
                    Text("Audio is processed in memory on this iPad and dropped once transcribed. It is never written to disk or sent anywhere.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                Section("Everything that left this device") {
                    if model.ledger.entries.isEmpty { Text("Nothing has left this device.").foregroundStyle(.secondary) }
                    ForEach(Array(model.ledger.entries.enumerated()), id: \.offset) { _, e in
                        VStack(alignment: .leading) {
                            Text(e.what).font(.body.monospaced())
                            Text("\(e.time) → \(e.destination) · \(e.bytes) bytes").font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
                Section("Network") {
                    Text("The only link is the clip (Bluetooth LE or the clip's own Wi-Fi). The app makes no other network calls.")
                        .font(.footnote)
                }
            }
            .navigationTitle("Ledger")
        }
    }
}
