#!/usr/bin/env python3
"""
Instant (0-second, zero-render) Final Cut Pro FCPXML v1.10 project exporter.
Creates a frame-accurate, non-destructive timeline linked directly to the
original camera file (preserving 10-bit Dolby Vision / HLG HDR natively),
ready for FCP Voice Isolation, captions, titles, and color presets.
"""
from __future__ import annotations
import argparse
import json
import os
import urllib.parse
import xml.sax.saxutils as saxutils


def rational_fps(fps: float) -> tuple[int, int]:
    """Return (frame_dur_num, frame_dur_den) for standard frame rates."""
    candidates = [
        (60.0, 100, 6000),
        (59.94, 1001, 60000),
        (50.0, 100, 5000),
        (30.0, 100, 3000),
        (29.97, 1001, 30000),
        (25.0, 100, 2500),
        (24.0, 100, 2400),
        (23.976, 1001, 24000),
    ]
    for target, num, den in candidates:
        if abs(fps - target) < 0.05:
            return num, den
    den = int(round(fps * 100))
    return 100, den


def frames_to_fcptime(n_frames: int, fnum: int, fden: int) -> str:
    if n_frames == 0:
        return "0s"
    return f"{n_frames * fnum}/{fden}s"


def export_fcpxml(meta: dict, segs: list[dict], out_path: str, captions: list[dict] | None = None):
    fps = meta["fps"]
    fnum, fden = rational_fps(fps)
    w, h = meta["width"], meta["height"]
    src_path = os.path.abspath(meta["input_path"])
    src_uri = "file://" + urllib.parse.quote(src_path)
    src_name = os.path.splitext(os.path.basename(src_path))[0]
    proj_name = f"{src_name}_精剪"

    src_total_frames = int(meta.get("nb_frames") or round(meta["duration"] * fps))
    seq_total_frames = sum(s["n_frames"] for s in segs)

    color_space = "9-18-9 (Rec. 2020 HLG)" if meta.get("is_hdr") and meta.get("color_transfer") == "arib-std-b67" else (
        "9-16-9 (Rec. 2020 PQ)" if meta.get("is_hdr") else "1-1-1 (Rec. 709)"
    )

    # Optional timeline markers from captions/badges
    markers_by_clip = {}
    if captions:
        # Map each caption with a badge or first few words to the overlapping output segment
        cur_f = 0
        seg_ranges = []
        for idx, s in enumerate(segs):
            seg_ranges.append((idx, cur_f, cur_f + s["n_frames"], s["start_frame"]))
            cur_f += s["n_frames"]
        for cap in captions:
            cf = int(round(float(cap["start"]) * fps))
            for idx, r0, r1, sf in seg_ranges:
                if r0 <= cf < r1:
                    local_src_f = sf + (cf - r0)
                    label = cap.get("badge") or cap.get("text", "").replace("*", "")[:20]
                    if label:
                        markers_by_clip.setdefault(idx, []).append((local_src_f, label))
                    break

    clips_xml = []
    offset_frames = 0
    for idx, s in enumerate(segs):
        sf = s["start_frame"]
        nf = s["n_frames"]
        clip_name = saxutils.escape(s.get("label") or f"Clip {idx+1:02d}")
        m_xml = ""
        for mf, mlabel in markers_by_clip.get(idx, []):
            m_xml += f'\n                            <marker start="{frames_to_fcptime(mf, fnum, fden)}" duration="{frames_to_fcptime(1, fnum, fden)}" value="{saxutils.escape(mlabel)}"/>'
        tail_ws = "\n                        " if m_xml else ""
        clips_xml.append(
            f'                        <asset-clip ref="r2" offset="{frames_to_fcptime(offset_frames, fnum, fden)}" '
            f'name="{clip_name}" start="{frames_to_fcptime(sf, fnum, fden)}" '
            f'duration="{frames_to_fcptime(nf, fnum, fden)}" audioRole="dialogue">{m_xml}'
            f'{tail_ws}</asset-clip>'
        )
        offset_frames += nf

    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.10">
    <resources>
        <format id="r1" name="FFVideoFormat{w}x{h}p{int(round(fps))}" frameDuration="{fnum}/{fden}s" width="{w}" height="{h}" colorSpace="{saxutils.escape(color_space)}"/>
        <asset id="r2" name="{saxutils.escape(src_name)}" start="0s" duration="{frames_to_fcptime(src_total_frames, fnum, fden)}" hasVideo="1" format="r1" hasAudio="1" audioSources="1" audioChannels="{meta.get('audio_channels', 2)}" audioRate="{meta.get('audio_sr', 48000)}">
            <media-rep kind="original-media" src="{saxutils.escape(src_uri)}"/>
        </asset>
    </resources>
    <library>
        <event name="{saxutils.escape(proj_name)}">
            <project name="{saxutils.escape(proj_name)}">
                <sequence format="r1" duration="{frames_to_fcptime(seq_total_frames, fnum, fden)}" tcStart="0s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">
                    <spine>
{chr(10).join(clips_xml)}
                    </spine>
                </sequence>
            </project>
        </event>
    </library>
</fcpxml>
'''
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"Exported Final Cut Pro timeline ({len(segs)} clips, {seq_total_frames/fps:.2f}s, 0s render): {out_path}")


def main():
    ap = argparse.ArgumentParser(description="Export cutlist to Final Cut Pro FCPXML v1.10 (0-second lossless timeline).")
    ap.add_argument("work_dir", help="Working directory from analyze.py")
    ap.add_argument("cutlist", help="JSON keep-list file")
    ap.add_argument("out_fcpxml", help="Output .fcpxml path")
    ap.add_argument("--captions", default="", help="Optional captions.json for timeline markers")
    args = ap.parse_args()

    meta = json.load(open(os.path.join(args.work_dir, "meta.json"), encoding="utf-8"))
    fps = meta["fps"]
    raw = json.load(open(args.cutlist, encoding="utf-8"))
    items = raw["segments"] if isinstance(raw, dict) and "segments" in raw else raw
    segs = []
    max_f = int(round(meta["duration"] * fps))
    for it in items:
        s = float(it["start"] if "start" in it else it["start_sec"])
        e = float(it["end"] if "end" in it else it["end_sec"])
        sf = max(0, int(round(s * fps)))
        ef = min(max_f, int(round(e * fps)))
        if ef > sf:
            segs.append({"start_frame": sf, "end_frame": ef, "n_frames": ef - sf, "label": it.get("label", "")})

    caps = json.load(open(args.captions, encoding="utf-8")) if args.captions else None
    export_fcpxml(meta, segs, args.out_fcpxml, caps)


if __name__ == "__main__":
    main()
