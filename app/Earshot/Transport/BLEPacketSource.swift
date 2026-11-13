import Foundation
import CoreBluetooth
import EarshotCore

/// Clip -> iPad over BLE. Each notification carries exactly one Earshot
/// packet (7-byte header + payload, no length prefix). iOS negotiates the
/// largest MTU itself; the clip requests 2M PHY, DLE and a 15 ms interval.
/// Pairing is encrypted: characteristics require an encrypted link, so iOS
/// shows the pairing prompt on first connect.
final class BLEPacketSource: NSObject, PacketSource, CBCentralManagerDelegate, CBPeripheralDelegate {
    let name = "Bluetooth LE"
    var onPacket: ((Packet) -> Void)?
    var onStatus: ((LinkStatus) -> Void)?

    private var central: CBCentralManager!
    private var peripheral: CBPeripheral?
    private var chars: [CBUUID: CBCharacteristic] = [:]
    private let queue = DispatchQueue(label: "earshot.ble")
    private var pendingWrites: [Packet] = []
    let meter = ThroughputMeter()

    override init() {
        super.init()
        central = CBCentralManager(delegate: self, queue: queue, options: [CBCentralManagerOptionShowPowerAlertKey: true])
    }

    func start() {
        if central.state == .poweredOn { scan() }
    }

    func stop() {
        central.stopScan()
        if let p = peripheral { central.cancelPeripheralConnection(p) }
        peripheral = nil; chars = [:]
    }

    func send(_ p: Packet) {
        queue.async {
            let target: CBUUID
            switch p {
            case .clock: target = EarshotGATT.clock
            case .ack: target = EarshotGATT.ack
            case .state: target = EarshotGATT.state
            default: return
            }
            guard let per = self.peripheral, let c = self.chars[target] else { self.pendingWrites.append(p); return }
            per.writeValue(Data(Wire.encode(p)), for: c, type: target == EarshotGATT.ack ? .withoutResponse : .withResponse)
        }
    }

    private func scan() {
        status(false, "scanning")
        central.scanForPeripherals(withServices: [EarshotGATT.service], options: nil)
    }

    private func status(_ connected: Bool, _ detail: String) {
        onStatus?(LinkStatus(connected: connected, transport: name, detail: detail, kbps: meter.kbps, lossPct: meter.lossPct))
    }

    // MARK: central

    func centralManagerDidUpdateState(_ c: CBCentralManager) {
        switch c.state {
        case .poweredOn: scan()
        case .unauthorized: status(false, "Bluetooth permission denied")
        case .poweredOff: status(false, "Bluetooth is off")
        case .unsupported: status(false, "Bluetooth unsupported (Simulator? use Replay or Wi-Fi)")
        default: status(false, "Bluetooth \(c.state.rawValue)")
        }
    }

    func centralManager(_ c: CBCentralManager, didDiscover p: CBPeripheral, advertisementData: [String: Any], rssi: NSNumber) {
        c.stopScan()
        peripheral = p
        p.delegate = self
        status(false, "connecting (RSSI \(rssi))")
        c.connect(p, options: nil)
    }

    func centralManager(_ c: CBCentralManager, didConnect p: CBPeripheral) {
        status(true, "connected, MTU \(p.maximumWriteValueLength(for: .withoutResponse) + 3)")
        p.discoverServices([EarshotGATT.service])
    }

    func centralManager(_ c: CBCentralManager, didDisconnectPeripheral p: CBPeripheral, error: Error?) {
        status(false, "disconnected — reconnecting")
        chars = [:]
        c.connect(p, options: nil) // pending connect, iOS reconnects when in range
    }

    func centralManager(_ c: CBCentralManager, didFailToConnect p: CBPeripheral, error: Error?) {
        status(false, "connect failed: \(error?.localizedDescription ?? "?")"); scan()
    }

    // MARK: peripheral

    func peripheral(_ p: CBPeripheral, didDiscoverServices error: Error?) {
        for s in p.services ?? [] where s.uuid == EarshotGATT.service {
            p.discoverCharacteristics([EarshotGATT.audio, EarshotGATT.tap, EarshotGATT.state, EarshotGATT.clock, EarshotGATT.ack], for: s)
        }
    }

    func peripheral(_ p: CBPeripheral, didDiscoverCharacteristicsFor s: CBService, error: Error?) {
        for c in s.characteristics ?? [] {
            chars[c.uuid] = c
            if [EarshotGATT.audio, EarshotGATT.tap, EarshotGATT.state].contains(c.uuid) { p.setNotifyValue(true, for: c) }
            if c.uuid == EarshotGATT.state { p.readValue(for: c) }
        }
        let w = pendingWrites; pendingWrites = []
        for x in w { send(x) }
        status(true, "ready")
    }

    func peripheral(_ p: CBPeripheral, didUpdateValueFor c: CBCharacteristic, error: Error?) {
        guard let d = c.value, let pkt = try? Wire.decode([UInt8](d)) else { return }
        meter.record(pkt, bytes: d.count)
        onPacket?(pkt)
        if meter.shouldReport { status(true, "streaming") }
    }
}
