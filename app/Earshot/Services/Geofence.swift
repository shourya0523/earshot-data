import Foundation
import CoreLocation

/// Arrival (eTimes.11) from a geofence around the destination ED. The manual
/// "Arrived" button on the handoff card is the backup.
final class Geofence: NSObject, CLLocationManagerDelegate {
    var onEnter: (() -> Void)?
    private let mgr = CLLocationManager()
    private var region: CLCircularRegion?

    override init() { super.init(); mgr.delegate = self }

    func start(lat: Double, lon: Double, radius: Double) {
        guard CLLocationManager.isMonitoringAvailable(for: CLCircularRegion.self) else { return }
        mgr.requestWhenInUseAuthorization()
        let r = CLCircularRegion(center: CLLocationCoordinate2D(latitude: lat, longitude: lon), radius: radius, identifier: "destination")
        r.notifyOnEntry = true; r.notifyOnExit = false
        region = r
        mgr.startMonitoring(for: r)
        mgr.requestState(for: r)
    }

    func stop() { if let r = region { mgr.stopMonitoring(for: r) }; region = nil }

    func locationManager(_ m: CLLocationManager, didEnterRegion r: CLRegion) { DispatchQueue.main.async { self.onEnter?() } }
    func locationManager(_ m: CLLocationManager, didDetermineState s: CLRegionState, for r: CLRegion) {
        if s == .inside { DispatchQueue.main.async { self.onEnter?() } }
    }
}
