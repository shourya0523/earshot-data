import SwiftUI
import EarshotCore

/// Barebones test harness for the pipeline. The real screens come later;
/// everything here is just enough to run a call end to end.
@main
struct EarshotApp: App {
    @State private var model = AppModel()
    var body: some Scene {
        WindowGroup { PipelineTestView().environment(model) }
    }
}

extension EarshotEvent: @retroactive Identifiable {}
