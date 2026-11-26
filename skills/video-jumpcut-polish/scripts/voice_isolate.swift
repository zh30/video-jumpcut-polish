import AVFoundation
import AudioToolbox
import Foundation

// Offline Apple Neural Engine Voice Isolation CLI using macOS built-in AUSoundIsolation
// (the same underlying ML engine as Final Cut Pro Voice Isolation).
// Preserves exact sample count and automatically compensates AudioUnit processing latency
// for 0.0ms A/V sync drift.
//
// Usage: voice_isolate <input.wav> <output.wav> [mix_percent=80]

let args = CommandLine.arguments
guard args.count >= 3 else {
    fputs("Usage: voice_isolate <input.wav> <output.wav> [mix_percent=80]\n", stderr)
    exit(1)
}

let inputURL = URL(fileURLWithPath: args[1])
let outputURL = URL(fileURLWithPath: args[2])
let mixPct: Float = args.count >= 4 ? max(0.0, min(100.0, Float(args[3]) ?? 80.0)) : 80.0

let desc = AudioComponentDescription(
    componentType: kAudioUnitType_Effect,
    componentSubType: 0x766F6973, // 'vois' (AUSoundIsolation)
    componentManufacturer: kAudioUnitManufacturer_Apple,
    componentFlags: 0,
    componentFlagsMask: 0
)

let sem = DispatchSemaphore(value: 0)
var exitCode: Int32 = 0

do {
    let inputFile = try AVAudioFile(forReading: inputURL)
    let procFormat = inputFile.processingFormat
    let totalFrames = inputFile.length
    let sr = procFormat.sampleRate

    let engine = AVAudioEngine()
    let player = AVAudioPlayerNode()
    engine.attach(player)

    AVAudioUnit.instantiate(with: desc, options: []) { unit, err in
        defer { sem.signal() }
        guard let isoUnit = unit, err == nil else {
            fputs("Failed to instantiate AUSoundIsolation: \(err?.localizedDescription ?? "unknown")\n", stderr)
            exitCode = 2
            return
        }

        engine.attach(isoUnit)
        // Set Sound to Isolate = 1.0 (Voice) and Wet/Dry Mix = mixPct (0..100)
        if let tree = isoUnit.auAudioUnit.parameterTree {
            if let modeParam = tree.parameter(withAddress: 1) {
                modeParam.value = 1.0
            }
            if let mixParam = tree.parameter(withAddress: 0) {
                mixParam.value = mixPct
            }
        }

        engine.connect(player, to: isoUnit, format: procFormat)
        engine.connect(isoUnit, to: engine.mainMixerNode, format: procFormat)

        do {
            let maxFrames: AVAudioFrameCount = 4096
            try engine.enableManualRenderingMode(.offline, format: procFormat, maximumFrameCount: maxFrames)
            try engine.start()

            // Query actual AudioUnit latency AFTER render resources are allocated
            let latencySec = isoUnit.auAudioUnit.latency
            let latencyFrames = AVAudioFramePosition((latencySec * sr).rounded())

            // Schedule full file; trailing silence after EOF naturally flushes AudioUnit lookahead
            player.scheduleFile(inputFile, at: nil)
            player.play()

            if FileManager.default.fileExists(atPath: outputURL.path) {
                try FileManager.default.removeItem(at: outputURL)
            }
            // Write standard 16-bit PCM WAV matching source sample rate & channel count
            let outSettings: [String: Any] = [
                AVFormatIDKey: kAudioFormatLinearPCM,
                AVSampleRateKey: sr,
                AVNumberOfChannelsKey: procFormat.channelCount,
                AVLinearPCMBitDepthKey: 16,
                AVLinearPCMIsBigEndianKey: false,
                AVLinearPCMIsFloatKey: false,
                AVLinearPCMIsNonInterleaved: false,
            ]
            let outputFile = try AVAudioFile(forWriting: outputURL, settings: outSettings, commonFormat: .pcmFormatFloat32, interleaved: false)

            guard let buffer = AVAudioPCMBuffer(pcmFormat: engine.manualRenderingFormat, frameCapacity: maxFrames) else {
                fputs("Failed to allocate PCM buffer\n", stderr)
                exitCode = 3
                return
            }

            let t0 = CFAbsoluteTimeGetCurrent()
            var skipped: AVAudioFramePosition = 0
            var written: AVAudioFramePosition = 0
            let totalNeeded = totalFrames + latencyFrames

            while written < totalFrames && engine.manualRenderingSampleTime < totalNeeded + AVAudioFramePosition(maxFrames) {
                let remaining = totalNeeded - (skipped + written)
                let toRender = min(maxFrames, AVAudioFrameCount(max(1, remaining)))
                let status = try engine.renderOffline(toRender, to: buffer)
                if status == .error {
                    fputs("Offline rendering error\n", stderr)
                    exitCode = 4
                    return
                }
                let got = Int(buffer.frameLength)
                if got == 0 {
                    if status == .insufficientDataFromInputNode { break }
                    continue
                }

                // Skip initial AudioUnit latency frames to preserve 0.0ms A/V sync
                var offset = 0
                if skipped < latencyFrames {
                    let drop = min(got, Int(latencyFrames - skipped))
                    skipped += AVAudioFramePosition(drop)
                    offset = drop
                }
                let avail = got - offset
                if avail <= 0 { continue }

                let keep = min(avail, Int(totalFrames - written))
                if offset == 0 && keep == got {
                    try outputFile.write(from: buffer)
                } else {
                    guard let slice = AVAudioPCMBuffer(pcmFormat: buffer.format, frameCapacity: AVAudioFrameCount(keep)) else {
                        exitCode = 5
                        return
                    }
                    slice.frameLength = AVAudioFrameCount(keep)
                    let chCount = Int(buffer.format.channelCount)
                    if let srcCh = buffer.floatChannelData, let dstCh = slice.floatChannelData {
                        for c in 0..<chCount {
                            dstCh[c].update(from: srcCh[c].advanced(by: offset), count: keep)
                        }
                    }
                    try outputFile.write(from: slice)
                }
                written += AVAudioFramePosition(keep)
            }

            player.stop()
            engine.stop()
            let dt = CFAbsoluteTimeGetCurrent() - t0
            print(String(format: "AUSoundIsolation (mix=%.0f%%, latency=%.1fms): %lld/%lld frames in %.2fs", mixPct, latencySec * 1000.0, written, totalFrames, dt))
        } catch {
            fputs("Engine error: \(error)\n", stderr)
            exitCode = 6
        }
    }
    sem.wait()
} catch {
    fputs("Audio file error: \(error)\n", stderr)
    exit(1)
}
exit(exitCode)
