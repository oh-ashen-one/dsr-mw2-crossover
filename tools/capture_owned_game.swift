// Original bounded process-filtered audiovisual capture. No microphone or input.
import Foundation
import ScreenCaptureKit
import AVFoundation
import CoreGraphics

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8)); exit(1)
}
final class RecordingDelegate: NSObject, SCRecordingOutputDelegate {
    private let lock = NSLock()
    private var finished = false
    private var failure: String? = nil
    func recordingOutputDidStartRecording(_ output: SCRecordingOutput) {
        print("RECORDING_STARTED"); fflush(stdout)
    }
    func recordingOutput(_ output: SCRecordingOutput, didFailWithError error: Error) {
        lock.lock(); failure = error.localizedDescription; finished = true; lock.unlock()
    }
    func recordingOutputDidFinishRecording(_ output: SCRecordingOutput) {
        lock.lock(); finished = true; lock.unlock()
    }
    func status() -> (Bool, String?) {
        lock.lock(); defer { lock.unlock() }; return (finished, failure)
    }
}
@main struct Capture {
    static func main() async {
        let args = CommandLine.arguments
        guard args.count == 5, let pid = Int32(args[1]), let windowID = UInt32(args[2]),
              let seconds = Double(args[3]), (1...60).contains(seconds) else {
            fail("Expected verified PID WINDOW_ID SECONDS OUTPUT.mp4")
        }
        guard CGPreflightScreenCaptureAccess() else {
            fail("Existing capture permission absent; no permission prompt requested")
        }
        let url = URL(fileURLWithPath: args[4])
        guard url.pathExtension == "mp4", !FileManager.default.fileExists(atPath: url.path) else {
            fail("Expected a fresh MP4 path")
        }
        do {
            let content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: true)
            guard let window = content.windows.first(where: { $0.windowID == windowID }),
                  window.title == "DARK SOULS™: REMASTERED",
                  let app = window.owningApplication, app.processID == pid,
                  let display = content.displays.first(where: { $0.frame.contains(window.frame) }) else {
                fail("Task game/window/display identity differs")
            }
            // The explicit application filter also bounds the captured system audio.
            let filter = SCContentFilter(display: display, including: [app], exceptingWindows: [])
            let config = SCStreamConfiguration()
            config.sourceRect = window.frame.offsetBy(dx: -display.frame.minX, dy: -display.frame.minY)
            config.width = 1720
            config.height = Int((1720 * window.frame.height / window.frame.width) / 2) * 2
            config.minimumFrameInterval = CMTime(value: 1, timescale: 30)
            config.showsCursor = false
            config.capturesAudio = true
            config.sampleRate = 48000
            config.channelCount = 2
            config.captureMicrophone = false
            let delegate = RecordingDelegate()
            let recordingConfig = SCRecordingOutputConfiguration()
            recordingConfig.outputURL = url
            recordingConfig.videoCodecType = .h264
            recordingConfig.outputFileType = .mp4
            let recording = SCRecordingOutput(configuration: recordingConfig, delegate: delegate)
            let stream = SCStream(filter: filter, configuration: config, delegate: nil)
            try stream.addRecordingOutput(recording)
            try await stream.startCapture()
            try await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
            try await stream.stopCapture()
            for _ in 0..<100 {
                let (done, failure) = delegate.status()
                if let failure { fail(failure) }
                if done {
                    print("RECORDING_FINISHED pid=\(pid) window=\(windowID) microphone=false application_filter=true")
                    return
                }
                try await Task.sleep(nanoseconds: 100_000_000)
            }
            fail("Recording completion callback timed out")
        } catch { fail(error.localizedDescription) }
    }
}
