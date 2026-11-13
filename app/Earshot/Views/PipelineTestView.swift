import SwiftUI
import EarshotCore

/// Barebones pipeline test screen. The real UI comes later.
struct PipelineTestView: View {
    @Environment(AppModel.self) var model
    @State private var output = 0
    @State private var receipt: EarshotEvent?
    @State private var shareURLs: [URL] = []
    @State private var showThroughput = false

    var body: some View {
        @Bindable var m = model
        NavigationStack {
            HStack(alignment: .top, spacing: 0) {
                List {
                    Section("Run") {
                        Picker("Transport", selection: $m.transport) { ForEach(TransportKind.allCases) { Text($0.rawValue).tag($0) } }
                        Picker("ASR model", selection: $m.asrSlot) { ForEach(ModelSlot.allCases) { Text($0.rawValue).tag($0) } }
                        Toggle("Tagger", isOn: $m.useTagger)
                        HStack {
                            Button("Start") { model.startCall() }.buttonStyle(.borderedProminent)
                            Button("Stop") { model.stopCall() }
                            Button("Mark") { model.manualMark() }
                            Button("Arrived") { model.markArrival() }
                            Button("Nurse accept") { model.nurseAccept() }
                        }.buttonStyle(.bordered)
                        Button("BLE throughput test") { showThroughput = true }
                    }
                    Section("Status") {
                        Text("Clip: \(model.clipState.name) · \(model.link.transport) · \(model.link.detail)")
                        Text(String(format: "%.1f kbps · loss %.1f%% · audio sent: %d bytes", model.link.kbps, model.link.lossPct, model.ledger.audioBytesSent))
                        if let w = model.chart?.wallTimeMs { Text("Wall time: \(ChartModel.duration(w))") }
                        if !model.statusMessage.isEmpty { Text(model.statusMessage).foregroundStyle(.orange) }
                    }
                    Section("Events (\(model.events.count))") {
                        ForEach(model.events) { e in
                            Button { receipt = e } label: {
                                VStack(alignment: .leading) {
                                    Text("\(model.session?.clock.clock(e.tMs) ?? "") \(e.type.rawValue) · \(e.source.rawValue)\(e.needsConfirm ? " · confirm" : "")")
                                        .font(.caption.monospaced())
                                    Text(e.fields.sorted { $0.key < $1.key }.map { "\($0.key)=\($0.value)" }.joined(separator: " ")).font(.caption)
                                }
                            }.buttonStyle(.plain)
                        }
                    }
                }
                .frame(maxWidth: 480)
                VStack {
                    Picker("Output", selection: $output) {
                        Text("SOAP").tag(0); Text("CHART").tag(1); Text("IMIST-AMBO").tag(2); Text("NEMSIS").tag(3)
                    }.pickerStyle(.segmented).padding()
                    ScrollView {
                        Text(docs.indices.contains(output) ? docs[output].text : "Start a call.")
                            .font(.caption.monospaced()).textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading).padding()
                    }
                }
            }
            .navigationTitle("Earshot pipeline test")
            .toolbar {
                if !shareURLs.isEmpty {
                    ShareLink(items: shareURLs) { Label("Export", systemImage: "square.and.arrow.up") }
                }
                Button("Prepare export") { shareURLs = model.exportFiles(); model.recordShare(shareURLs, to: "share sheet") }
                Button("Sign & wipe", role: .destructive) { model.sign() }
            }
            .sheet(item: $receipt) { e in
                NavigationStack {
                    List {
                        Text("“\(e.quote ?? "tap only")”").italic()
                        Text("span \(e.rawSpan ?? "-") · \(ChartModel.srcLabel(e)) · conf \(String(format: "%.2f", e.confidence))")
                        ForEach((e.receipts ?? [:]).sorted { $0.key < $1.key }, id: \.key) { k, r in Text("\(k): “\(r.quote)” (\(r.rawSpan))") }
                    }.navigationTitle("Receipt \(e.id)")
                }
            }
            .sheet(isPresented: $showThroughput) { ThroughputTestView() }
        }
    }

    var docs: [RenderedDoc] { model.session?.render() ?? [] }
}

/// First run on a real iPad: BLE throughput, loss and latency.
struct ThroughputTestView: View {
    @State private var source = BLEPacketSource()
    @State private var detail = "starting"
    @State private var tick = 0
    var body: some View {
        NavigationStack {
            List {
                Text("Link: \(detail)")
                Text(String(format: "%.1f kbps · loss %.2f%% · latency %.0f ms (max %.0f)", source.meter.kbps, source.meter.lossPct,
                            source.meter.latencyMs, source.meter.maxLatencyMs)).id(tick)
                Text("Pass: ≥ 80 kbps sustained and < 1 % loss for 2 min while LISTENING. Otherwise the clip needs 8 kHz audio or stronger compression.").font(.footnote)
            }
            .navigationTitle("BLE throughput")
            .task {
                source.onStatus = { s in DispatchQueue.main.async { detail = s.detail } }
                source.start()
                while !Task.isCancelled { try? await Task.sleep(for: .seconds(1)); tick += 1 }
            }
            .onDisappear { source.stop() }
        }
    }
}
