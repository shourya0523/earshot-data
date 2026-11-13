import SwiftUI
import EarshotCore

struct ConnectView: View {
    @Environment(AppModel.self) var model
    @State private var showThroughput = false
    var body: some View {
        @Bindable var m = model
        NavigationStack {
            Form {
                Section("Clip") {
                    LabeledContent("State") { StatePill(state: model.clipState) }
                    LabeledContent("Transport", value: model.link.transport)
                    LabeledContent("Link", value: model.link.connected ? "connected" : "not connected")
                    LabeledContent("Detail", value: model.link.detail)
                    LabeledContent("Throughput", value: String(format: "%.1f kbps (need ~68)", model.link.kbps))
                    LabeledContent("Audio loss", value: String(format: "%.1f %%", model.link.lossPct))
                    LabeledContent("Power", value: "USB power bank")
                }
                Section("Transport") {
                    Picker("Use", selection: $m.transport) {
                        ForEach(TransportKind.allCases) { Text($0.rawValue).tag($0) }
                    }
                    if model.transport == .replay {
                        Picker("Replay speed", selection: $m.replaySpeed) {
                            Text("1×").tag(1.0); Text("2×").tag(2.0); Text("4×").tag(4.0)
                        }
                    }
                }
                Section {
                    Button("Start call") { model.startCall() }.buttonStyle(.borderedProminent)
                    Button("Stop listening", role: .destructive) { model.stopCall() }
                    Button("Bluetooth throughput test") { showThroughput = true }
                } footer: {
                    Text("Consent is asked on the clip: press once to ask, press again for yes, hold for no. Nothing is captured before a yes. Audio stays in memory and is dropped once transcribed.")
                }
                if !model.statusMessage.isEmpty { Section("Notice") { Text(model.statusMessage).foregroundStyle(.orange) } }
            }
            .navigationTitle("Earshot")
            .sheet(isPresented: $showThroughput) { ThroughputTestView() }
        }
    }
}

struct StatePill: View {
    let state: ClipState
    var body: some View {
        Text(state.name)
            .font(.caption.bold()).padding(.horizontal, 8).padding(.vertical, 3)
            .background(color.opacity(0.2), in: Capsule()).foregroundStyle(color)
    }
    var color: Color {
        switch state { case .listening: .red; case .asking: .orange; case .refused: .gray; case .off: .secondary }
    }
}

/// First run on a real iPad: measures BLE throughput, loss and latency.
struct ThroughputTestView: View {
    @State private var source = BLEPacketSource()
    @State private var status = LinkStatus(connected: false, transport: "Bluetooth LE")
    @State private var packets = 0
    @State private var timer: Timer?
    var body: some View {
        NavigationStack {
            Form {
                Section("Live") {
                    LabeledContent("Link", value: status.detail)
                    LabeledContent("Throughput", value: String(format: "%.1f kbps", source.meter.kbps))
                    LabeledContent("Loss", value: String(format: "%.2f %%", source.meter.lossPct))
                    LabeledContent("Latency (rel.)", value: String(format: "%.0f ms (max %.0f)", source.meter.latencyMs, source.meter.maxLatencyMs))
                    LabeledContent("Packets", value: "\(packets)")
                }
                Section {
                    Text("Pass: ≥ 80 kbps sustained, < 1 % loss over 2 minutes with the clip LISTENING. If it fails, set AUDIO_RATE_8K in firmware (half the bitrate) and re-test.")
                        .font(.footnote)
                }
            }
            .navigationTitle("Throughput test")
            .onAppear {
                source.onStatus = { s in DispatchQueue.main.async { status = s } }
                source.onPacket = { _ in DispatchQueue.main.async { packets += 1 } }
                source.start()
                timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { _ in packets += 0 }
            }
            .onDisappear { source.stop(); timer?.invalidate() }
        }
    }
}
