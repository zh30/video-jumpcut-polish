import AppKit
import CoreGraphics
import CoreImage
import Foundation

// Renders 3 platform-optimized covers from a hero frame JPG + JSON spec in < 0.5s:
//   1. cover_xiaohongshu_3x4.jpg   (1080 x 1440, 3:4 waterfall safe zone)
//   2. cover_douyin_9x16.jpg       (1080 x 1920, clears right icons + bottom 22% bar)
//   3. cover_bilibili_16x9.jpg     (1920 x 1080, wide card layout, clears bottom-right duration badge)
//
// Usage: make_covers <hero_frame.jpg> <cover_spec.json> <out_dir>

struct CoverSpec: Decodable {
    let tag: String?          // e.g. "百元真香实测"
    let headline: String      // supports *gold highlight*, e.g. "国补 *84块* 买到"
    let subline: String?      // e.g. "手感像 AirPods 的半入耳耳机"
    let xhs_name: String?
    let douyin_name: String?
    let bilibili_name: String?
}

func makeFont(size: CGFloat, heavy: Bool = true) -> NSFont {
    let names = heavy
        ? ["PingFangSC-Semibold", "HiraginoSansGB-W6", "STHeitiSC-Medium"]
        : ["PingFangSC-Medium", "HiraginoSansGB-W3"]
    for n in names {
        if let f = NSFont(name: n, size: size) { return f }
    }
    return NSFont.boldSystemFont(ofSize: size)
}

func makeStyled(_ raw: String, size: CGFloat, align: NSTextAlignment, strokePass: Bool, goldHi: Bool = true) -> NSAttributedString {
    let baseFont = makeFont(size: size, heavy: true)
    let hiFont = makeFont(size: size * 1.14, heavy: true)

    let p = NSMutableParagraphStyle()
    p.alignment = align
    p.lineSpacing = size * 0.16

    let shadow = NSShadow()
    shadow.shadowColor = NSColor.black.withAlphaComponent(0.85)
    shadow.shadowOffset = NSSize(width: 0, height: -max(3.0, size * 0.05))
    shadow.shadowBlurRadius = max(8.0, size * 0.18)

    let norm: [NSAttributedString.Key: Any]
    let hi: [NSAttributedString.Key: Any]
    if strokePass {
        norm = [
            .font: baseFont,
            .strokeColor: NSColor.black.withAlphaComponent(0.92),
            .strokeWidth: 9.0,
            .paragraphStyle: p,
            .shadow: shadow,
        ]
        hi = [
            .font: hiFont,
            .strokeColor: NSColor.black.withAlphaComponent(0.95),
            .strokeWidth: 9.5,
            .paragraphStyle: p,
            .shadow: shadow,
        ]
    } else {
        norm = [
            .font: baseFont,
            .foregroundColor: NSColor.white,
            .paragraphStyle: p,
        ]
        hi = [
            .font: hiFont,
            .foregroundColor: goldHi
                ? NSColor(calibratedRed: 1.0, green: 0.85, blue: 0.20, alpha: 1.0)
                : NSColor(calibratedRed: 0.35, green: 0.95, blue: 0.65, alpha: 1.0),
            .paragraphStyle: p,
        ]
    }

    let out = NSMutableAttributedString()
    let parts = raw.components(separatedBy: "*")
    for (i, part) in parts.enumerated() {
        if part.isEmpty { continue }
        let isHi = (i % 2 == 1) && (parts.count > 1)
        out.append(NSAttributedString(string: part, attributes: isHi ? hi : norm))
    }
    return out
}

func drawTwoPass(_ raw: String, in rect: NSRect, size: CGFloat, align: NSTextAlignment) {
    let sPass = makeStyled(raw, size: size, align: align, strokePass: true)
    let fPass = makeStyled(raw, size: size, align: align, strokePass: false)
    sPass.draw(with: rect, options: [.usesLineFragmentOrigin, .usesFontLeading])
    fPass.draw(with: rect, options: [.usesLineFragmentOrigin, .usesFontLeading])
}

func drawAspectFill(_ img: NSImage, in dst: NSRect, yBias: CGFloat = 0.5) {
    let iw = img.size.width
    let ih = img.size.height
    let scale = max(dst.width / iw, dst.height / ih)
    let sw = iw * scale
    let sh = ih * scale
    let x = dst.minX + (dst.width - sw) / 2.0
    let y = dst.minY + (dst.height - sh) * yBias
    NSGraphicsContext.current?.cgContext.saveGState()
    NSBezierPath(rect: dst).addClip()
    img.draw(in: NSRect(x: x, y: y, width: sw, height: sh))
    NSGraphicsContext.current?.cgContext.restoreGState()
}

func drawBlurredBackdrop(_ cgImg: CGImage, in dst: NSRect) {
    let ci = CIImage(cgImage: cgImg)
    let filter = CIFilter(name: "CIGaussianBlur")!
    filter.setValue(ci.clampedToExtent(), forKey: kCIInputImageKey)
    filter.setValue(28.0, forKey: kCIInputRadiusKey)
    let ctx = CIContext()
    if let outCI = filter.outputImage?.cropped(to: ci.extent),
       let blurredCG = ctx.createCGImage(outCI, from: ci.extent) {
        let blurredNS = NSImage(cgImage: blurredCG, size: NSSize(width: cgImg.width, height: cgImg.height))
        drawAspectFill(blurredNS, in: dst)
    }
    NSColor.black.withAlphaComponent(0.45).setFill()
    dst.fill()
}

func drawGradientScrim(in rect: NSRect, topAlpha: CGFloat, bottomAlpha: CGFloat) {
    let grad = NSGradient(
        starting: NSColor.black.withAlphaComponent(bottomAlpha),
        ending: NSColor.black.withAlphaComponent(topAlpha)
    )
    grad?.draw(in: rect, angle: 90)
}

func drawPillTag(_ text: String, x: CGFloat, y: CGFloat, fontSize: CGFloat, centeredInWidth: CGFloat? = nil) {
    let font = makeFont(size: fontSize, heavy: true)
    let attrs: [NSAttributedString.Key: Any] = [
        .font: font,
        .foregroundColor: NSColor.black,
    ]
    let str = NSAttributedString(string: text, attributes: attrs)
    let sz = str.size()
    let padX = fontSize * 0.75
    let padY = fontSize * 0.30
    let pw = sz.width + padX * 2
    let ph = sz.height + padY * 2
    let px = centeredInWidth != nil ? (centeredInWidth! - pw) / 2.0 : x
    let rect = NSRect(x: px, y: y, width: pw, height: ph)
    let path = NSBezierPath(roundedRect: rect, xRadius: ph * 0.28, yRadius: ph * 0.28)
    NSColor(calibratedRed: 1.0, green: 0.85, blue: 0.20, alpha: 1.0).setFill()
    path.fill()
    str.draw(at: NSPoint(x: px + padX, y: y + padY * 0.92))
}

func makeCanvas(w: Int, h: Int) -> NSBitmapImageRep {
    return NSBitmapImageRep(
        bitmapDataPlanes: nil, pixelsWide: w, pixelsHigh: h,
        bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
        colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0
    )!
}

func saveJPG(_ rep: NSBitmapImageRep, to path: String) throws {
    guard let data = rep.representation(using: .jpeg, properties: [.compressionFactor: 0.92]) else {
        throw NSError(domain: "make_covers", code: 1, userInfo: [NSLocalizedDescriptionKey: "JPEG encode failed"])
    }
    try data.write(to: URL(fileURLWithPath: path))
}

// 1. XiaoHongShu 3:4 (1080 x 1440)
func renderXHS(hero: NSImage, spec: CoverSpec, outPath: String) throws {
    let w = 1080, h = 1440
    let rep = makeCanvas(w: w, h: h)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    NSGraphicsContext.current?.shouldAntialias = true

    drawAspectFill(hero, in: NSRect(x: 0, y: 0, width: w, height: h), yBias: 0.5)
    // Top + bottom scrims for crisp readability
    drawGradientScrim(in: NSRect(x: 0, y: 0, width: w, height: 520), topAlpha: 0.0, bottomAlpha: 0.78)
    drawGradientScrim(in: NSRect(x: 0, y: h - 360, width: w, height: 360), topAlpha: 0.65, bottomAlpha: 0.0)

    if let tag = spec.tag, !tag.isEmpty {
        drawPillTag(tag, x: 0, y: CGFloat(h) - 180, fontSize: 40, centeredInWidth: CGFloat(w))
    }

    let headRect = NSRect(x: 64, y: 175, width: w - 128, height: 240)
    drawTwoPass(spec.headline, in: headRect, size: 84, align: .center)

    if let sub = spec.subline, !sub.isEmpty {
        let subRect = NSRect(x: 72, y: 82, width: w - 144, height: 95)
        drawTwoPass(sub, in: subRect, size: 46, align: .center)
    }

    NSGraphicsContext.restoreGraphicsState()
    try saveJPG(rep, to: outPath)
}

// 2. Douyin / WeChat Channels 9:16 (1080 x 1920)
func renderDouyin(hero: NSImage, spec: CoverSpec, outPath: String) throws {
    let w = 1080, h = 1920
    let rep = makeCanvas(w: w, h: h)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    NSGraphicsContext.current?.shouldAntialias = true

    drawAspectFill(hero, in: NSRect(x: 0, y: 0, width: w, height: h), yBias: 0.5)
    // Safe-zone scrim: keep headline in upper-middle & lower-middle (above bottom 22% UI bar, away from right edge!)
    drawGradientScrim(in: NSRect(x: 0, y: h - 580, width: w, height: 580), topAlpha: 0.72, bottomAlpha: 0.0)
    drawGradientScrim(in: NSRect(x: 0, y: 0, width: w, height: 540), topAlpha: 0.0, bottomAlpha: 0.65)

    // Upper safe block (y: 1320..1720 -> clears top status bar & right icons)
    if let tag = spec.tag, !tag.isEmpty {
        drawPillTag(tag, x: 0, y: 1620, fontSize: 38, centeredInWidth: CGFloat(w))
    }
    let headRect = NSRect(x: 70, y: 1365, width: w - 140, height: 240)
    drawTwoPass(spec.headline, in: headRect, size: 86, align: .center)

    if let sub = spec.subline, !sub.isEmpty {
        // Placed at y=470 (~24% from bottom -> cleanly clears Douyin bottom title bar!)
        let subRect = NSRect(x: 80, y: 450, width: w - 200, height: 110)
        drawTwoPass(sub, in: subRect, size: 48, align: .center)
    }

    NSGraphicsContext.restoreGraphicsState()
    try saveJPG(rep, to: outPath)
}

// 3. Bilibili / YouTube 16:9 (1920 x 1080)
func renderBilibili(hero: NSImage, cgHero: CGImage, spec: CoverSpec, outPath: String) throws {
    let w = 1920, h = 1080
    let rep = makeCanvas(w: w, h: h)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    NSGraphicsContext.current?.shouldAntialias = true

    let isHeroPortrait = hero.size.height > hero.size.width
    if isHeroPortrait {
        // Blurred wide ambient backdrop + crisp product card on right + bold typography block on left
        // Bottom-right corner stays clean (no text) so Bilibili's duration badge never covers copy!
        drawBlurredBackdrop(cgHero, in: NSRect(x: 0, y: 0, width: w, height: h))
        let cardH: CGFloat = 940
        let cardW: CGFloat = 705 // 3:4 crisp showcase card
        let cardRect = NSRect(x: CGFloat(w) - cardW - 90, y: (CGFloat(h) - cardH) / 2.0, width: cardW, height: cardH)

        // Card drop shadow
        NSGraphicsContext.current?.cgContext.saveGState()
        let cardShadow = NSShadow()
        cardShadow.shadowColor = NSColor.black.withAlphaComponent(0.65)
        cardShadow.shadowBlurRadius = 36
        cardShadow.shadowOffset = NSSize(width: 0, height: -10)
        cardShadow.set()
        let cardPath = NSBezierPath(roundedRect: cardRect, xRadius: 34, yRadius: 34)
        NSColor.black.setFill()
        cardPath.fill()
        NSGraphicsContext.current?.cgContext.restoreGState()

        // Draw clipped hero image inside rounded card
        NSGraphicsContext.current?.cgContext.saveGState()
        cardPath.addClip()
        drawAspectFill(hero, in: cardRect, yBias: 0.5)
        NSGraphicsContext.current?.cgContext.restoreGState()

        // Subtle crisp border
        NSColor.white.withAlphaComponent(0.28).setStroke()
        cardPath.lineWidth = 3.0
        cardPath.stroke()

        // Left typography panel (x: 96..1050)
        if let tag = spec.tag, !tag.isEmpty {
            drawPillTag(tag, x: 96, y: 760, fontSize: 44, centeredInWidth: nil)
        }
        let headRect = NSRect(x: 96, y: 390, width: 960, height: 340)
        drawTwoPass(spec.headline, in: headRect, size: 108, align: .left)

        if let sub = spec.subline, !sub.isEmpty {
            let subRect = NSRect(x: 96, y: 220, width: 960, height: 150)
            drawTwoPass(sub, in: subRect, size: 54, align: .left)
        }
    } else {
        // Landscape source: full-bleed hero + left-bottom safe typography (clearing bottom-right!)
        drawAspectFill(hero, in: NSRect(x: 0, y: 0, width: w, height: h))
        drawGradientScrim(in: NSRect(x: 0, y: 0, width: w, height: 520), topAlpha: 0.0, bottomAlpha: 0.80)
        if let tag = spec.tag, !tag.isEmpty {
            drawPillTag(tag, x: 88, y: 420, fontSize: 42, centeredInWidth: nil)
        }
        let headRect = NSRect(x: 88, y: 185, width: 1380, height: 220)
        drawTwoPass(spec.headline, in: headRect, size: 96, align: .left)
        if let sub = spec.subline, !sub.isEmpty {
            let subRect = NSRect(x: 88, y: 78, width: 1380, height: 105)
            drawTwoPass(sub, in: subRect, size: 50, align: .left)
        }
    }

    NSGraphicsContext.restoreGraphicsState()
    try saveJPG(rep, to: outPath)
}

let args = CommandLine.arguments
guard args.count >= 4 else {
    fputs("Usage: make_covers <hero_frame.jpg> <cover_spec.json> <out_dir>\n", stderr)
    exit(1)
}
let heroPath = args[1]
let specPath = args[2]
let outDir = args[3]

try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
guard let heroImg = NSImage(contentsOfFile: heroPath),
      let tiff = heroImg.tiffRepresentation,
      let rep = NSBitmapImageRep(data: tiff),
      let cgHero = rep.cgImage else {
    fputs("Failed to load hero image: \(heroPath)\n", stderr)
    exit(2)
}

let spec = try JSONDecoder().decode(CoverSpec.self, from: Data(contentsOf: URL(fileURLWithPath: specPath)))
let xhsOut = "\(outDir)/\(spec.xhs_name ?? "封面_小红书_3x4.jpg")"
let dyOut = "\(outDir)/\(spec.douyin_name ?? "封面_抖音视频号_9x16.jpg")"
let biliOut = "\(outDir)/\(spec.bilibili_name ?? "封面_B站YouTube_16x9.jpg")"

try renderXHS(hero: heroImg, spec: spec, outPath: xhsOut)
try renderDouyin(hero: heroImg, spec: spec, outPath: dyOut)
try renderBilibili(hero: heroImg, cgHero: cgHero, spec: spec, outPath: biliOut)
print("Generated 3 platform covers:\n  \(xhsOut)\n  \(dyOut)\n  \(biliOut)")
