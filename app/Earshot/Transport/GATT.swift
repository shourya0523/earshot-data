import CoreBluetooth

/// Earshot GATT service (must match firmware/common/earshot_proto.h).
enum EarshotGATT {
    static let service = CBUUID(string: "E5A1D000-0B5E-4C6B-9C5E-EA5407000000")
    static let audio   = CBUUID(string: "E5A1D001-0B5E-4C6B-9C5E-EA5407000000") // notify
    static let tap     = CBUUID(string: "E5A1D002-0B5E-4C6B-9C5E-EA5407000000") // notify (resent until acked)
    static let state   = CBUUID(string: "E5A1D003-0B5E-4C6B-9C5E-EA5407000000") // read / notify / write
    static let clock   = CBUUID(string: "E5A1D004-0B5E-4C6B-9C5E-EA5407000000") // write
    static let ack     = CBUUID(string: "E5A1D005-0B5E-4C6B-9C5E-EA5407000000") // write
    static let deviceName = "Earshot"
}
