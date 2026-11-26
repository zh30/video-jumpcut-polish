import AppKit
import CoreGraphics
import Foundation

// Renders crisp Retina-quality transparent RGBA PNG subtitles & optional chapter badges
// using macOS native PingFang SC typography, thin stroke, soft drop shadow, and *keyword*
// gold highlights, plus an ffmpeg concat demuxer script and standard .srt sidecar.
//
// Usage: render_subs <captions.json> <width> <height> <total_dur> <out_dir> [srt_out_path]

struct CaptionItem: Decodable {
    let start: Double
    let end: Double
    let text: String
    let badge: String?
}

func formatSRTTime(_ sec: Double) -> String {
    let clamped = max(0.0, sec)
    let msTotal = Int((clamped * 1000.0).rounded())
    let h = msTotal / 3_600_000
    let m = (msTotal % 3_600_000) / 60_000
    let s = (msTotal % 60_000) / 1000
    let ms = msTotal % 1000
    return String(format: "%02d:%02d:%02d,%03d", h, m, s, ms)
}

func makeFont(size: CGFloat, bold: Bool = true) -> NSFont {
    let candidates = bold
        ? ["PingFangSC-Semibold", "PingFangSC-Medium", "HiraginoSansGB-W6", "STHeitiSC-Medium"]
        : ["PingFangSC-Medium", "HiraginoSansGB-W3"]
    for name in candidates {
        if let f = NSFont(name: name, size: size) {
            return f
        }
    }
    return NSFont.boldSystemFont(ofSize: size)
}

func parseHighlightedString(_ raw: String, fontSize: CGFloat, strokePass: Bool) -> NSAttributedString {
    let baseFont = makeFont(size: fontSize, bold: true)
    let hiFont = makeFont(size: fontSize * 1.12, bold: true)

    let paragraph = NSMutableParagraphStyle()
    paragraph.alignment = .center
    paragraph.lineSpacing = fontSize * 0.22

    let shadow = NSShadow()
    shadow.shadowColor = NSColor.black.withAlphaComponent(0.82)
    shadow.shadowOffset = NSSize(width: 0, height: -max(2.0, fontSize * 0.05))
    shadow.shadowBlurRadius = max(5.0, fontSize * 0.16)

    let normalAttrs: [NSAttributedString.Key: Any]
    let hiAttrs: [NSAttributedString.Key: Any]
    if strokePass {
        normalAttrs = [
            .font: baseFont,
            .strokeColor: NSColor.black.withAlphaComponent(0.92),
            .strokeWidth: 7.5,
            .paragraphStyle: paragraph,
            .shadow: shadow,
        ]
        hiAttrs = [
            .font: hiFont,
            .strokeColor: NSColor.black.withAlphaComponent(0.95),
            .strokeWidth: 8.0,
            .paragraphStyle: paragraph,
            .shadow: shadow,
        ]
    } else {
        normalAttrs = [
            .font: baseFont,
            .foregroundColor: NSColor.white,
            .paragraphStyle: paragraph,
        ]
        hiAttrs = [
            .font: hiFont,
            .foregroundColor: NSColor(calibratedRed: 1.0, green: 0.85, blue: 0.22, alpha: 1.0),
            .paragraphStyle: paragraph,
        ]
    }

    let result = NSMutableAttributedString()
    // Split on *keyword* markers
    let parts = raw.components(separatedBy: "*")
    for (idx, part) in parts.enumerated() {
        if part.isEmpty { continue }
        let isHi = (idx % 2 == 1) && (parts.count > 1)
        result.append(NSAttributedString(string: part, attributes: isHi ? hiAttrs : normalAttrs))
    }
    return result
}

func writePNG(_ rep: NSBitmapImageRep, to path: String) throws {
    guard let data = rep.representation(using: .png, properties: [:]) else {
        throw NSError(domain: "render_subs", code: 1, userInfo: [NSLocalizedDescriptionKey: "Failed PNG encode"])
    }
    try data.write(to: URL(fileURLWithPath: path))
}

func makeBlankRep(w: Int, h: Int) -> NSBitmapImageRep {
    return NSBitmapImageRep(
        bitmapDataPlanes: nil,
        pixelsWide: w,
        pixelsHigh: h,
        bitsPerSample: 8,
        samplesPerPixel: 4,
        hasAlpha: true,
        isPlanar: false,
        colorSpaceName: .deviceRGB,
        bytesPerRow: 0,
        bitsPerPixel: 0
    )!
}

func renderOverlayPNG(text: String, badge: String?, width: Int, height: Int, stripMode: Bool, outPath: String) throws {
    let isPortrait = height >= width
    let canvasW = width
    let stripH = Int((Double(height) * (isPortrait ? 0.16 : 0.20)).rounded()) & ~1
    let canvasH = stripMode ? stripH : height

    let rep = makeBlankRep(w: canvasW, h: canvasH)
    NSGraphicsContext.saveGraphicsState()
    guard let ctx = NSGraphicsContext(bitmapImageRep: rep) else {
        throw NSError(domain: "render_subs", code: 2, userInfo: [NSLocalizedDescriptionKey: "No graphics context"])
    }
    NSGraphicsContext.current = ctx
    ctx.shouldAntialias = true

    // Clear transparent
    NSColor.clear.setFill()
    NSRect(x: 0, y: 0, width: canvasW, height: canvasH).fill()

    // Draw subtitle text (two-pass: outer outline + shadow first, then crisp solid fill on top)
    if !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        let baseUnit = CGFloat(min(width, height))
        let fontSize = baseUnit * (isPortrait ? 0.045 : 0.048)
        let strokeStr = parseHighlightedString(text, fontSize: fontSize, strokePass: true)
        let fillStr = parseHighlightedString(text, fontSize: fontSize, strokePass: false)

        let sideMargin = CGFloat(width) * (isPortrait ? 0.09 : 0.08)
        let maxTextW = CGFloat(width) - sideMargin * 2
        let bounds = fillStr.boundingRect(
            with: NSSize(width: maxTextW, height: CGFloat(stripH)),
            options: [.usesLineFragmentOrigin, .usesFontLeading]
        )
        let drawY: CGFloat
        if stripMode {
            drawY = max(8.0, (CGFloat(canvasH) - bounds.height) / 2.0)
        } else {
            // Portrait: ~20% from bottom (clears Douyin/Xiaohongshu/Bilibili UI); Landscape: ~8% from bottom
            let bottomMargin = CGFloat(height) * (isPortrait ? 0.19 : 0.08)
            drawY = bottomMargin
        }
        let drawRect = NSRect(x: sideMargin, y: drawY, width: maxTextW, height: bounds.height + fontSize * 0.4)
        strokeStr.draw(with: drawRect, options: [.usesLineFragmentOrigin, .usesFontLeading])
        fillStr.draw(with: drawRect, options: [.usesLineFragmentOrigin, .usesFontLeading])
    }

    // Draw optional chapter badge pill (only when !stripMode)
    if !stripMode, let badgeText = badge, !badgeText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        let baseUnit = CGFloat(min(width, height))
        let bFontSize = baseUnit * (isPortrait ? 0.032 : 0.030)
        let bFont = makeFont(size: bFontSize, bold: true)
        let bAttrs: [NSAttributedString.Key: Any] = [
            .font: bFont,
            .foregroundColor: NSColor.white,
        ]
        let bStr = NSAttributedString(string: badgeText, attributes: bAttrs)
        let bSize = bStr.size()
        let padX = bFontSize * 0.75
        let padY = bFontSize * 0.38
        let dotR = bFontSize * 0.22
        let pillW = bSize.width + padX * 2 + dotR * 3.2
        let pillH = bSize.height + padY * 2
        let pillX = CGFloat(width) * 0.06
        let pillY = CGFloat(height) * (isPortrait ? 0.84 : 0.88) - pillH

        let pillRect = NSRect(x: pillX, y: pillY, width: pillW, height: pillH)
        let pillPath = NSBezierPath(roundedRect: pillRect, xRadius: pillH / 2, yRadius: pillH / 2)
        NSColor.black.withAlphaComponent(0.58).setFill()
        pillPath.fill()
        NSColor.white.withAlphaComponent(0.22).setStroke()
        pillPath.lineWidth = max(1.5, baseUnit * 0.002)
        pillPath.stroke()

        // Warm gold accent dot
        let dotRect = NSRect(
            x: pillX + padX * 0.85,
            y: pillY + (pillH - dotR * 2) / 2,
            width: dotR * 2,
            height: dotR * 2
        )
        NSColor(calibratedRed: 1.0, green: 0.85, blue: 0.24, alpha: 1.0).setFill()
        NSBezierPath(ovalIn: dotRect).fill()

        bStr.draw(at: NSPoint(x: dotRect.maxX + dotR * 1.1, y: pillY + padY * 0.92))
    }

    NSGraphicsContext.restoreGraphicsState()
    try writePNG(rep, to: outPath)
}

// Entry point
let args = CommandLine.arguments
guard args.count >= 6 else {
    fputs("Usage: render_subs <captions.json> <width> <height> <total_dur> <out_dir> [srt_out]\n", stderr)
    exit(1)
}
let captionsPath = args[1]
let width = Int(args[2])!
let height = Int(args[3])!
let totalDur = Double(args[4])!
let outDir = args[5]
let srtOut = args.count >= 7 ? args[6] : nil

try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
let rawData = try Data(contentsOf: URL(fileURLWithPath: captionsPath))
let items = try JSONDecoder().decode([CaptionItem].self, from: rawData).sorted { $0.start < $1.start }

let hasBadges = items.contains { ($0.badge ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false }
let stripMode = !hasBadges
let isPortrait = height >= width
let stripH = Int((Double(height) * (isPortrait ? 0.16 : 0.20)).rounded()) & ~1
let canvasH = stripMode ? stripH : height

// Write blank PNG
let blankPath = "\(outDir)/blank.png"
try writePNG(makeBlankRep(w: width, h: canvasH), to: blankPath)

// Render each caption PNG and build concat demuxer timeline
var concatLines: [String] = []
var srtLines: [String] = []
var cursor = 0.0
var lastFile = blankPath

for (idx, item) in items.enumerated() {
    let s = max(cursor, min(totalDur, item.start))
    let e = max(s, min(totalDur, item.end))
    if e - s < 0.04 { continue }

    if s - cursor >= 0.02 {
        concatLines.append("file '\(blankPath)'")
        concatLines.append(String(format: "duration %.4f", s - cursor))
        lastFile = blankPath
    }

    let pngPath = String(format: "%@/sub_%04d.png", outDir, idx + 1)
    try renderOverlayPNG(text: item.text, badge: item.badge, width: width, height: height, stripMode: stripMode, outPath: pngPath)
    concatLines.append("file '\(pngPath)'")
    concatLines.append(String(format: "duration %.4f", e - s))
    lastFile = pngPath
    cursor = e

    let plainText = item.text.replacingOccurrences(of: "*", with: "")
    srtLines.append("\(srtLines.count + 1)\n\(formatSRTTime(s)) --> \(formatSRTTime(e))\n\(plainText)\n")
}

if totalDur - cursor >= 0.02 {
    concatLines.append("file '\(blankPath)'")
    concatLines.append(String(format: "duration %.4f", totalDur - cursor))
    lastFile = blankPath
}
// FFmpeg concat demuxer requires repeating the final file line
concatLines.append("file '\(lastFile)'")

let concatPath = "\(outDir)/subs_concat.txt"
try (concatLines.joined(separator: "\n") + "\n").write(toFile: concatPath, atomically: true, encoding: .utf8)

if let srtPath = srtOut {
    try srtLines.joined(separator: "\n").write(toFile: srtPath, atomically: true, encoding: .utf8)
}

let overlayY = stripMode ? Int((Double(height) * (isPortrait ? 0.65 : 0.72)).rounded()) : 0
let metaOut: [String: Any] = [
    "concat_path": concatPath,
    "strip_mode": stripMode,
    "canvas_w": width,
    "canvas_h": canvasH,
    "overlay_y": overlayY,
    "count": items.count,
]
let metaJson = try JSONSerialization.data(withJSONObject: metaOut, options: [.prettyPrinted])
try metaJson.write(to: URL(fileURLWithPath: "\(outDir)/subs_meta.json"))
print("Rendered \(items.count) subtitle overlays (\(width)x\(canvasH), strip=\(stripMode))")
