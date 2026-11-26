import AppKit
import CoreGraphics
import CoreImage
import Foundation
import Vision

// Native macOS Apple Neural Engine product fidelity toolkit for high-CTR covers:
//   1. sharpest <out.jpg> <img1> [img2 ...] [--crop x,y,w,h]
//        Picks the sharpest (least motion-blurred) frame via Laplacian variance,
//        optionally tight-crops to normalized box (or auto-crops around Vision subject).
//   2. cutout <in_img> <out_cutout.png> [--crop x,y,w,h]
//        Uses Apple Vision VNGenerateForegroundInstanceMaskRequest (iPhone Lift Subject engine)
//        to extract a crisp transparent RGBA PNG of the real product, trimmed to tight bounds.
//   3. composite <bg_cover.jpg> <cutout.png> <out_cover.jpg> <cx> <cy> <max_w_ratio> <max_h_ratio>
//        Composites a 100% real product cutout onto an AI-generated stage/typography cover
//        with realistic elliptical ground contact shadow + soft studio drop shadow.

func loadCGImage(_ path: String) -> CGImage? {
    guard let src = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil) else { return nil }
    return CGImageSourceCreateImageAtIndex(src, 0, nil)
}

func saveJPG(_ cg: CGImage, to path: String, quality: CGFloat = 0.94) throws {
    let rep = NSBitmapImageRep(cgImage: cg)
    guard let data = rep.representation(using: .jpeg, properties: [.compressionFactor: quality]) else {
        throw NSError(domain: "product_tools", code: 1, userInfo: [NSLocalizedDescriptionKey: "JPEG encode failed"])
    }
    try data.write(to: URL(fileURLWithPath: path))
}

func savePNG(_ cg: CGImage, to path: String) throws {
    let rep = NSBitmapImageRep(cgImage: cg)
    guard let data = rep.representation(using: .png, properties: [:]) else {
        throw NSError(domain: "product_tools", code: 2, userInfo: [NSLocalizedDescriptionKey: "PNG encode failed"])
    }
    try data.write(to: URL(fileURLWithPath: path))
}

func cropNormalized(_ cg: CGImage, box: [Double]) -> CGImage {
    let w = Double(cg.width)
    let h = Double(cg.height)
    let rx = max(0, min(w - 2, (box[0] * w).rounded()))
    let ry = max(0, min(h - 2, (box[1] * h).rounded()))
    let rw = max(2, min(w - rx, (box[2] * w).rounded()))
    let rh = max(2, min(h - ry, (box[3] * h).rounded()))
    return cg.cropping(to: CGRect(x: rx, y: ry, width: rw, height: rh)) ?? cg
}

// Fast sharpness score using high-frequency gradient energy on downscaled grayscale ROI
func sharpnessScore(_ cg: CGImage) -> Double {
    let targetW = min(480, cg.width)
    let targetH = max(1, Int(Double(cg.height) * Double(targetW) / Double(cg.width)))
    let colorSpace = CGColorSpaceCreateDeviceGray()
    var buf = [UInt8](repeating: 0, count: targetW * targetH)
    guard let ctx = CGContext(
        data: &buf, width: targetW, height: targetH,
        bitsPerComponent: 8, bytesPerRow: targetW,
        space: colorSpace, bitmapInfo: 0
    ) else { return 0.0 }
    ctx.interpolationQuality = .medium
    ctx.draw(cg, in: CGRect(x: 0, y: 0, width: targetW, height: targetH))

    var sumSq = 0.0
    var count = 0
    for y in 1..<(targetH - 1) {
        let row = y * targetW
        for x in 1..<(targetW - 1) {
            let idx = row + x
            let lap = -4 * Int(buf[idx]) + Int(buf[idx - 1]) + Int(buf[idx + 1]) + Int(buf[idx - targetW]) + Int(buf[idx + targetW])
            sumSq += Double(lap * lap)
            count += 1
        }
    }
    return count > 0 ? sumSq / Double(count) : 0.0
}

// Apple Vision VNGenerateForegroundInstanceMaskRequest subject cutout
func visionCutout(_ cg: CGImage) throws -> CGImage {
    guard #available(macOS 14.0, *) else {
        throw NSError(domain: "product_tools", code: 10, userInfo: [NSLocalizedDescriptionKey: "macOS 14+ required for Vision subject cutout"])
    }
    let req = VNGenerateForegroundInstanceMaskRequest()
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    try handler.perform([req])
    guard let obs = req.results?.first else {
        throw NSError(domain: "product_tools", code: 11, userInfo: [NSLocalizedDescriptionKey: "No foreground subject detected"])
    }
    let maskedBuf = try obs.generateMaskedImage(
        ofInstances: obs.allInstances,
        from: handler,
        croppedToInstancesExtent: true
    )
    let ci = CIImage(cvPixelBuffer: maskedBuf)
    let ctx = CIContext()
    guard let outCG = ctx.createCGImage(ci, from: ci.extent) else {
        throw NSError(domain: "product_tools", code: 12, userInfo: [NSLocalizedDescriptionKey: "Failed to render masked CGImage"])
    }
    return outCG
}

// Auto-find tight bounding box around Vision subject with padding
func autoSubjectCrop(_ cg: CGImage, padFrac: Double = 0.16) -> CGImage {
    guard #available(macOS 14.0, *) else { return cg }
    let req = VNGenerateForegroundInstanceMaskRequest()
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    guard (try? handler.perform([req])) != nil,
          let obs = req.results?.first,
          let maskBuf = try? obs.generateScaledMaskForImage(forInstances: obs.allInstances, from: handler) else {
        return cg
    }
    CVPixelBufferLockBaseAddress(maskBuf, .readOnly)
    defer { CVPixelBufferUnlockBaseAddress(maskBuf, .readOnly) }
    let mw = CVPixelBufferGetWidth(maskBuf)
    let mh = CVPixelBufferGetHeight(maskBuf)
    let bpr = CVPixelBufferGetBytesPerRow(maskBuf)
    guard let base = CVPixelBufferGetBaseAddress(maskBuf) else { return cg }
    let ptr = base.assumingMemoryBound(to: Float32.self)
    let floatsPerRow = bpr / MemoryLayout<Float32>.size

    var minX = mw, minY = mh, maxX = 0, maxY = 0
    for y in stride(from: 0, to: mh, by: 2) {
        for x in stride(from: 0, to: mw, by: 2) {
            if ptr[y * floatsPerRow + x] > 0.45 {
                if x < minX { minX = x }
                if x > maxX { maxX = x }
                if y < minY { minY = y }
                if y > maxY { maxY = y }
            }
        }
    }
    guard maxX > minX + 10 && maxY > minY + 10 else { return cg }
    let bw = Double(maxX - minX)
    let bh = Double(maxY - minY)
    let padX = bw * padFrac
    let padY = bh * padFrac
    let sx = Double(cg.width) / Double(mw)
    let sy = Double(cg.height) / Double(mh)
    let rx = max(0, (Double(minX) - padX) * sx).rounded()
    let ry = max(0, (Double(minY) - padY) * sy).rounded()
    let rw = min(Double(cg.width) - rx, (bw + padX * 2) * sx).rounded()
    let rh = min(Double(cg.height) - ry, (bh + padY * 2) * sy).rounded()
    return cg.cropping(to: CGRect(x: rx, y: ry, width: rw, height: rh)) ?? cg
}

// Composite real cutout onto AI stage background with realistic ground contact shadow + studio depth shadow
func compositeProduct(bgPath: String, cutoutPath: String, outPath: String, cxRatio: Double, cyRatio: Double, maxWRatio: Double, maxHRatio: Double) throws {
    guard let bgCG = loadCGImage(bgPath), let cutCG = loadCGImage(cutoutPath) else {
        throw NSError(domain: "product_tools", code: 20, userInfo: [NSLocalizedDescriptionKey: "Failed to load bg or cutout"])
    }
    let W = bgCG.width
    let H = bgCG.height
    let rep = NSBitmapImageRep(
        bitmapDataPlanes: nil, pixelsWide: W, pixelsHigh: H,
        bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
        colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0
    )!

    NSGraphicsContext.saveGraphicsState()
    guard let nsCtx = NSGraphicsContext(bitmapImageRep: rep) else {
        throw NSError(domain: "product_tools", code: 21, userInfo: [NSLocalizedDescriptionKey: "No NSGraphicsContext"])
    }
    NSGraphicsContext.current = nsCtx
    let cgCtx = nsCtx.cgContext
    cgCtx.interpolationQuality = .high

    // 1. Draw AI background
    let bgImg = NSImage(cgImage: bgCG, size: NSSize(width: W, height: H))
    bgImg.draw(in: NSRect(x: 0, y: 0, width: W, height: H))

    // 2. Compute target rect (AppKit origin is bottom-left; cyRatio is top-down 0..1 for intuitive UX!)
    let maxW = Double(W) * maxWRatio
    let maxH = Double(H) * maxHRatio
    let scale = min(maxW / Double(cutCG.width), maxH / Double(cutCG.height))
    let dw = Double(cutCG.width) * scale
    let dh = Double(cutCG.height) * scale
    let centerX = Double(W) * cxRatio
    let centerY = Double(H) * (1.0 - cyRatio)
    let dstRect = NSRect(x: centerX - dw / 2.0, y: centerY - dh / 2.0, width: dw, height: dh)

    // 3. Draw realistic elliptical ground contact shadow under the base of the product
    cgCtx.saveGState()
    let shW = dw * 0.88
    let shH = max(18.0, dh * 0.14)
    let shRect = CGRect(x: centerX - shW / 2.0, y: dstRect.minY - shH * 0.35, width: shW, height: shH)
    let colors = [
        CGColor(red: 0, green: 0, blue: 0, alpha: 0.72),
        CGColor(red: 0, green: 0, blue: 0, alpha: 0.30),
        CGColor(red: 0, green: 0, blue: 0, alpha: 0.0),
    ] as CFArray
    let locs: [CGFloat] = [0.0, 0.55, 1.0]
    if let grad = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: colors, locations: locs) {
        cgCtx.translateBy(x: shRect.midX, y: shRect.midY)
        cgCtx.scaleBy(x: 1.0, y: shRect.height / shRect.width)
        cgCtx.drawRadialGradient(grad, startCenter: .zero, startRadius: 0, endCenter: .zero, endRadius: shRect.width / 2.0, options: [])
    }
    cgCtx.restoreGState()

    // 4. Draw soft ambient drop shadow + crisp real product cutout
    cgCtx.saveGState()
    let drop = NSShadow()
    drop.shadowColor = NSColor.black.withAlphaComponent(0.55)
    drop.shadowBlurRadius = CGFloat(max(16.0, dw * 0.06))
    drop.shadowOffset = NSSize(width: 0, height: -CGFloat(max(6.0, dh * 0.025)))
    drop.set()
    let cutImg = NSImage(cgImage: cutCG, size: NSSize(width: cutCG.width, height: cutCG.height))
    cutImg.draw(in: dstRect)
    cgCtx.restoreGState()

    NSGraphicsContext.restoreGraphicsState()
    guard let outCG = rep.cgImage else {
        throw NSError(domain: "product_tools", code: 22, userInfo: [NSLocalizedDescriptionKey: "Failed finalizing composite"])
    }
    try saveJPG(outCG, to: outPath)
    print("Composited 100% real product (\(Int(dw))x\(Int(dh))) onto \(W)x\(H) cover -> \(outPath)")
}

// CLI dispatch
let args = CommandLine.arguments
guard args.count >= 2 else {
    fputs("Usage:\n  product_tools sharpest <out.jpg> <img1> [img2 ...] [--crop x,y,w,h] [--auto-crop]\n  product_tools cutout <in_img> <out.png> [--crop x,y,w,h]\n  product_tools composite <bg.jpg> <cutout.png> <out.jpg> <cx> <cy> <max_w> <max_h>\n", stderr)
    exit(1)
}

func parseCropFlag(_ args: [String]) -> [Double]? {
    if let idx = args.firstIndex(of: "--crop"), idx + 1 < args.count {
        let vals = args[idx + 1].split(separator: ",").compactMap { Double($0) }
        if vals.count == 4 { return vals }
    }
    return nil
}

do {
    let cmd = args[1]
    if cmd == "sharpest" {
        let outPath = args[2]
        let cropBox = parseCropFlag(args)
        let autoCrop = args.contains("--auto-crop")
        var imgPaths: [String] = []
        var i = 3
        while i < args.count {
            if args[i] == "--crop" { i += 2; continue }
            if args[i] == "--auto-crop" { i += 1; continue }
            imgPaths.append(args[i])
            i += 1
        }
        var bestCG: CGImage?
        var bestPath = ""
        var bestScore = -1.0
        for p in imgPaths {
            guard let cg = loadCGImage(p) else { continue }
            let roi = cropBox != nil ? cropNormalized(cg, box: cropBox!) : cg
            let sc = sharpnessScore(roi)
            if sc > bestScore {
                bestScore = sc
                bestCG = roi
                bestPath = p
            }
        }
        guard var finalCG = bestCG else {
            fputs("No readable frames\n", stderr)
            exit(2)
        }
        if cropBox == nil && autoCrop {
            finalCG = autoSubjectCrop(finalCG)
        }
        try saveJPG(finalCG, to: outPath)
        print(String(format: "Sharpest frame: %@ (score=%.1f, out=%dx%d) -> %@", URL(fileURLWithPath: bestPath).lastPathComponent, bestScore, finalCG.width, finalCG.height, outPath))
    } else if cmd == "cutout" {
        let inPath = args[2]
        let outPath = args[3]
        let cropBox = parseCropFlag(args)
        guard var cg = loadCGImage(inPath) else {
            fputs("Failed to load image: \(inPath)\n", stderr)
            exit(2)
        }
        if let box = cropBox {
            cg = cropNormalized(cg, box: box)
        }
        let cut = try visionCutout(cg)
        try savePNG(cut, to: outPath)
        print("Apple Vision cutout saved (\(cut.width)x\(cut.height)) -> \(outPath)")
    } else if cmd == "composite" {
        guard args.count >= 9 else {
            fputs("Usage: product_tools composite <bg.jpg> <cutout.png> <out.jpg> <cx> <cy> <max_w> <max_h>\n", stderr)
            exit(1)
        }
        try compositeProduct(
            bgPath: args[2], cutoutPath: args[3], outPath: args[4],
            cxRatio: Double(args[5])!, cyRatio: Double(args[6])!,
            maxWRatio: Double(args[7])!, maxHRatio: Double(args[8])!
        )
    } else {
        fputs("Unknown command: \(cmd)\n", stderr)
        exit(1)
    }
} catch {
    fputs("Error: \(error)\n", stderr)
    exit(1)
}
