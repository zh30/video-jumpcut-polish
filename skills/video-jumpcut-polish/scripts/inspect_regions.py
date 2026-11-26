#!/usr/bin/env python3
"""
Parallel micro-inspector for verbal tics, stutters, and action beats (< 1s).
Slices candidate ranges from audio_48k.wav to clips/*.mp3 and prints 50ms ASCII
dB bar charts (for ranges <= 5s) or VOX/dip summaries (for longer ranges).
Optionally builds a zoomed 1fps visual contact sheet for unboxing/action sections.
"""
from __future__ import annotations
import argparse
import json
import math
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor


def parse_regions(spec: str) -> list[tuple[str, float, float]]:
    if os.path.isfile(spec):
        raw = json.load(open(spec, encoding="utf-8"))
        out = []
        for idx, item in enumerate(raw, 1):
            if isinstance(item, dict):
                out.append((item.get("name", f"r{idx:02d}"), float(item["start"]), float(item["end"])))
            else:
                name = item[2] if len(item) > 2 else f"r{idx:02d}"
                out.append((name, float(item[0]), float(item[1])))
        return out

    out = []
    for idx, part in enumerate(spec.split(","), 1):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            name, rng = part.split(":", 1)
        else:
            name, rng = f"r{idx:02d}", part
        s, e = map(float, rng.split("-", 1))
        out.append((name.strip(), s, e))
    return out


def slice_mp3(wav48: str, out_mp3: str, s: float, e: float):
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-ss", f"{s:.3f}", "-to", f"{e:.3f}",
        "-i", wav48, "-c:a", "libmp3lame", "-b:a", "128k", out_mp3
    ], check=True)
    return out_mp3


def make_zoom_sheet(meta: dict, work_dir: str, s: float, e: float, fps: float):
    out_jpg = os.path.join(work_dir, "zoom_sheet.jpg")
    n_tiles = max(1, int(math.ceil((e - s) * fps)))
    cols = min(8, n_tiles)
    rows = math.ceil(n_tiles / cols)
    w, h = meta["width"], meta["height"]
    if abs(meta.get("rotation", 0)) in (90, 270):
        w, h = h, w
    tw = 180 if h >= w else 240
    th = int(round(tw * h / w)) // 2 * 2
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-hwaccel", "videotoolbox",
        "-ss", f"{s:.3f}", "-to", f"{e:.3f}",
        "-i", meta["input_path"],
        "-vf", f"fps={fps},scale={tw}:{th},tile={cols}x{rows}",
        "-frames:v", "1", "-q:v", "4", out_jpg
    ], check=True)
    return out_jpg


def main():
    ap = argparse.ArgumentParser(description="Inspect candidate filler/stutter audio regions and zoom contact sheets.")
    ap.add_argument("work_dir", help="Working directory created by analyze.py")
    ap.add_argument("regions", nargs="?", default="", help='Comma ranges "10.0-18.5,75.8-78.6" or "name:s-e" or JSON path')
    ap.add_argument("--sheet", default="", help='Optional zoomed visual sheet range "START-END"')
    ap.add_argument("--sheet-fps", type=float, default=1.0, help="FPS for zoomed sheet (default: 1.0)")
    args = ap.parse_args()

    meta = json.load(open(os.path.join(args.work_dir, "meta.json"), encoding="utf-8"))
    dbs = json.load(open(os.path.join(args.work_dir, "db_10ms.json")))
    thresh = meta["silence_threshold_db"]
    wav48 = os.path.join(args.work_dir, "audio_48k.wav")
    clips_dir = os.path.join(args.work_dir, "clips")
    os.makedirs(clips_dir, exist_ok=True)

    regions = parse_regions(args.regions) if args.regions else []

    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = []
        for name, s, e in regions:
            out_mp3 = os.path.join(clips_dir, f"{name}.mp3")
            futs.append((name, s, e, ex.submit(slice_mp3, wav48, out_mp3, s, e)))
        sheet_fut = None
        if args.sheet:
            ss, se = map(float, args.sheet.split("-", 1))
            sheet_fut = ex.submit(make_zoom_sheet, meta, args.work_dir, ss, se, args.sheet_fps)

        for name, s, e, fut in futs:
            mp3_path = fut.result()
            print(f"\n=== {name}: {s:.2f}s - {e:.2f}s (dur {e-s:.2f}s) -> {mp3_path} ===")
            if e - s <= 5.0:
                t = s
                while t < e - 0.001:
                    idx = int(round(t * 100))
                    chunk = dbs[idx : min(len(dbs), idx + 5)]
                    mx = max(chunk) if chunk else -60.0
                    bars = "#" * max(0, int((mx + 48) / 2))
                    print(f"  {t:6.2f}s (+{t-s:4.2f}s) {mx:5.1f}dB |{bars}")
                    t += 0.05
            else:
                i0 = max(0, int(round(s * 100)))
                i1 = min(len(dbs), int(round(e * 100)))
                if i0 >= i1:
                    continue
                state = dbs[i0] >= thresh
                rs = i0
                for idx in range(i0 + 1, i1 + 1):
                    cur = (dbs[idx] >= thresh) if idx < i1 else (not state)
                    if cur != state:
                        dur = (idx - rs) * 0.01
                        if dur >= 0.05:
                            pk = max(dbs[rs:idx])
                            print(f"  {'VOX' if state else 'dip'} {rs*0.01:6.2f} - {idx*0.01:6.2f} ({dur:4.2f}s, rel {rs*0.01-s:5.2f}-{idx*0.01-s:5.2f}s, peak {pk:5.1f}dB)")
                        rs = idx
                        state = cur

        if sheet_fut:
            print(f"\nZoomed contact sheet ({args.sheet_fps}fps, {args.sheet}s): {sheet_fut.result()}")


if __name__ == "__main__":
    main()
