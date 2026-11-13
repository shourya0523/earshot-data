import Foundation
import Network
import EarshotCore

/// Wi-Fi fallback: the clip runs a soft AP ("Earshot-XXXX", WPA2) at
/// 192.168.4.1; TCP port 7070; length-prefixed packets (u16 LE length +
/// packet), the same framing as replay files.
final class WiFiPacketSource: PacketSource {
    let name = "Wi-Fi"
    var onPacket: ((Packet) -> Void)?
    var onStatus: ((LinkStatus) -> Void)?
    var host = "192.168.4.1"
    var port: UInt16 = 7070
    private var conn: NWConnection?
    private var deframer = StreamDeframer()
    private let queue = DispatchQueue(label: "earshot.wifi")
    let meter = ThroughputMeter()

    func start() {
        let c = NWConnection(host: NWEndpoint.Host(host), port: NWEndpoint.Port(rawValue: port)!, using: .tcp)
        conn = c
        c.stateUpdateHandler = { [weak self] st in
            guard let self else { return }
            switch st {
            case .ready: self.onStatus?(LinkStatus(connected: true, transport: self.name, detail: "connected to \(self.host)")); self.receive()
            case .failed(let e): self.onStatus?(LinkStatus(connected: false, transport: self.name, detail: "failed: \(e)")); self.retry()
            case .waiting(let e): self.onStatus?(LinkStatus(connected: false, transport: self.name, detail: "waiting: \(e). Join the Earshot Wi-Fi."))
            default: break
            }
        }
        c.start(queue: queue)
    }

    private func retry() {
        queue.asyncAfter(deadline: .now() + 2) { [weak self] in self?.conn?.cancel(); self?.start() }
    }

    private func receive() {
        conn?.receive(minimumIncompleteLength: 1, maximumLength: 8192) { [weak self] data, _, done, err in
            guard let self else { return }
            if let d = data {
                for p in self.deframer.push([UInt8](d)) {
                    self.meter.record(p, bytes: Wire.encode(p).count + 2)
                    self.onPacket?(p)
                }
                if self.meter.shouldReport {
                    self.onStatus?(LinkStatus(connected: true, transport: self.name, detail: "streaming", kbps: self.meter.kbps, lossPct: self.meter.lossPct))
                }
            }
            if done || err != nil { self.retry() } else { self.receive() }
        }
    }

    func stop() { conn?.cancel(); conn = nil }

    func send(_ p: Packet) { conn?.send(content: Data(Wire.frame(p)), completion: .contentProcessed { _ in }) }
}
