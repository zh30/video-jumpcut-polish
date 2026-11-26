#!/usr/bin/env python3
"""
Fast pre-analysis for video jump-cut editing (< 3s typical).
Extracts metadata, 48kHz stereo PCM WAV, compact MP3(s) for multimodal listening,
10ms RMS dB curve, calibrated PAUSE/SOUND timeline, baseline keep-list, and
a visual overview contact sheet. Standard library + ffmpeg/ffprobe only.
"""
from __future__ import annotations
import argparse
import array
import json
import math
import os
import subprocess
import sys
import time
import wave
from concurrent.futures import ThreadPoolExecutor


def parse_frac(s: str) -> float:
    if not s or s == "0/0":
        return 0.0
    if "/" in s:
        a, b = s.split("/", 1)
        return float(a) / float(b) if float(b) else 0.0
    return float(s)


def probe_video(input_path: str) -> dict:
    raw = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", input_path
    ])
    info = json.loads(raw)
    vstream = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    astream = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    if not vstream or not astream:
        raise RuntimeError("Input file must contain both video and audio streams.")

    r_fps = parse_frac(vstream.get("r_frame_rate", "0"))
    avg_fps = parse_frac(vstream.get("avg_frame_rate", "0"))
    fps = r_fps if r_fps > 0 else avg_fps
    is_vfr = abs(r_fps - avg_fps) > 0.5 and avg_fps > 0

    pix_fmt = vstream.get("pix_fmt", "yuv420p")
    color_trc = vstream.get("color_transfer", "")
    color_prim = vstream.get("color_primaries", "")
    color_space = vstream.get("color_space", "")
    color_range = vstream.get("color_range", "")
    is_10bit = "10" in pix_fmt or "main 10" in str(vstream.get("profile", "")).lower()
    is_hdr = color_trc in ("arib-std-b67", "smpte2084") or color_prim == "bt2020"

    rotation = 0
    for sd in vstream.get("side_data_list", []):
        if "rotation" in sd:
            rotation = int(sd["rotation"])

    dur = float(vstream.get("duration") or info["format"].get("duration") or 0.0)
    nb_frames = int(vstream.get("nb_frames") or round(dur * fps))
    v_bitrate = int(vstream.get("bit_rate") or info["format"].get("bit_rate") or 0)

    return {
        "input_path": os.path.abspath(input_path),
        "duration": dur,
        "width": int(vstream["width"]),
        "height": int(vstream["height"]),
        "rotation": rotation,
        "video_codec": vstream.get("codec_name", ""),
        "video_profile": vstream.get("profile", ""),
        "pix_fmt": pix_fmt,
        "color_primaries": color_prim,
        "color_transfer": color_trc,
        "color_space": color_space,
        "color_range": color_range,
        "is_10bit": is_10bit,
        "is_hdr": is_hdr,
        "r_fps": round(r_fps, 6),
        "avg_fps": round(avg_fps, 6),
        "fps": round(fps, 6),
        "is_vfr": is_vfr,
        "nb_frames": nb_frames,
        "video_bitrate": v_bitrate,
        "audio_codec": astream.get("codec_name", ""),
        "audio_sr": int(astream.get("sample_rate", 48000)),
        "audio_channels": int(astream.get("channels", 2)),
    }


def extract_audio_assets(input_path: str, work_dir: str, duration: float, chunk_sec: int):
    wav48 = os.path.join(work_dir, "audio_48k.wav")
    wav16 = os.path.join(work_dir, "audio_16k.wav")
    # Single decode pass produces both 48k stereo editing WAV and 16k mono analysis WAV
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", input_path,
        "-map", "0:a:0", "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", wav48,
        "-map", "0:a:0", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav16,
    ], check=True)

    mp3_files = []
    if duration <= chunk_sec + 30:
        mp3 = os.path.join(work_dir, "audio_full.mp3")
        subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-i", wav16,
            "-c:a", "libmp3lame", "-b:a", "64k", mp3
        ], check=True)
        mp3_files.append(mp3)
    else:
        n_parts = math.ceil(duration / chunk_sec)
        for i in range(n_parts):
            s = i * chunk_sec
            mp3 = os.path.join(work_dir, f"audio_part_{i+1:02d}.mp3")
            subprocess.run([
                "ffmpeg", "-y", "-v", "error",
                "-ss", f"{s:.3f}", "-t", f"{chunk_sec:.3f}",
                "-i", wav16, "-c:a", "libmp3lame", "-b:a", "64k", mp3
            ], check=True)
            mp3_files.append(mp3)
    return wav48, wav16, mp3_files


def make_contact_sheet(input_path: str, work_dir: str, meta: dict):
    out_jpg = os.path.join(work_dir, "contact_sheet.jpg")
    dur = meta["duration"]
    # Target ~32 tiles across entire duration
    target_tiles = min(40, max(16, int(round(dur / 5.0))))
    step = max(1.0, dur / target_tiles)
    cols = 8
    rows = max(1, math.ceil((dur / step) / cols))
    # Preserve aspect ratio (portrait vs landscape)
    w, h = meta["width"], meta["height"]
    if abs(meta["rotation"]) in (90, 270):
        w, h = h, w
    tw = 180 if h >= w else 240
    th = int(round(tw * h / w)) // 2 * 2

    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-skip_frame", "nokey",
        "-hwaccel", "videotoolbox",
        "-i", input_path,
        "-vf", f"fps=1/{step:.3f},scale={tw}:{th},tile={cols}x{rows}",
        "-frames:v", "1", "-q:v", "4", out_jpg
    ], check=True)
    return out_jpg, step


def compute_db_envelope(wav16_path: str) -> tuple[list[float], dict]:
    with wave.open(wav16_path, "rb") as wf:
        sr = wf.getframerate()
        n = wf.getnframes()
        raw = wf.readframes(n)
    samples = array.array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()

    hop = int(sr * 0.01)      # 10ms
    win = int(sr * 0.025)     # 25ms
    n_frames = max(1, (n - win) // hop + 1)
    inv_norm = 1.0 / (32768.0 * 32768.0)

    # Subsample by 2 inside 25ms window (8kHz effective RMS) for 2x speed with <0.1dB diff
    dbs = []
    for i in range(n_frames):
        s = i * hop
        chunk = samples[s : s + win : 2]
        ms = sum(x * x for x in chunk) / len(chunk)
        rms_sq = ms * inv_norm
        db = 10.0 * math.log10(rms_sq + 1e-12)
        dbs.append(round(db, 2))

    s_db = sorted(dbs)
    def pct(p): return s_db[min(len(s_db) - 1, int(len(s_db) * p / 100))]
    stats = {
        "p10": round(pct(10), 1),
        "p25": round(pct(25), 1),
        "p50": round(pct(50), 1),
        "p75": round(pct(75), 1),
        "p90": round(pct(90), 1),
    }
    return dbs, stats


def build_timeline_and_baseline(dbs: list[float], stats: dict, duration: float, thresh_offset: float, min_pause: float, keep_pad: float):
    thresh = max(-45.0, min(-28.0, max(stats["p10"] + thresh_offset, stats["p75"] - 18.0)))
    thresh = round(thresh, 1)

    pauses = []
    st = None
    for i, v in enumerate(dbs):
        if v < thresh and st is None:
            st = i * 0.01
        elif v >= thresh and st is not None:
            en = i * 0.01
            if en - st >= min_pause:
                pauses.append((round(st, 2), round(en, 2), round(en - st, 2)))
            st = None
    if st is not None:
        en = min(duration, len(dbs) * 0.01)
        if en - st >= min_pause:
            pauses.append((round(st, 2), round(en, 2), round(en - st, 2)))

    lines = [
        f"Duration: {duration:.2f}s | Noise floor(p10): {stats['p10']}dB | Speech(p75/p90): {stats['p75']}/{stats['p90']}dB | Silence threshold: {thresh}dB",
        f"Detected {len(pauses)} pauses >= {min_pause:.2f}s (total {sum(x[2] for x in pauses):.2f}s)",
        "-" * 72,
    ]
    prev = 0.0
    for idx, (s, e, d) in enumerate(pauses, 1):
        if s > prev + 0.01:
            lines.append(f"  SOUND {prev:6.2f} - {s:6.2f} (dur {s - prev:5.2f}s)")
        lines.append(f"PAUSE #{idx:02d}: {s:6.2f} - {e:6.2f} (dur {d:5.2f}s)")
        prev = e
    if prev < duration - 0.01:
        lines.append(f"  SOUND {prev:6.2f} - {duration:6.2f} (dur {duration - prev:5.2f}s)")

    # Build baseline keep-list by trimming pauses >= 0.45s down to ~2*keep_pad (e.g. 0.18s)
    cuts = []
    for s, e, d in pauses:
        if s <= 0.05 and d > 0.25:
            cuts.append((0.0, max(0.0, e - 0.18)))
        elif e >= duration - 0.05 and d > 0.35:
            cuts.append((min(duration, s + 0.25), duration))
        elif d >= 0.45:
            cs = round(s + keep_pad, 2)
            ce = round(e - keep_pad, 2)
            if ce - cs >= 0.15:
                cuts.append((cs, ce))

    keeps = []
    cur = 0.0
    for cs, ce in cuts:
        if cs > cur + 0.05:
            keeps.append({"start": round(cur, 2), "end": round(cs, 2), "label": ""})
        cur = max(cur, ce)
    if cur < duration - 0.05:
        keeps.append({"start": round(cur, 2), "end": round(duration, 2), "label": ""})

    return thresh, "\n".join(lines), keeps


def main():
    ap = argparse.ArgumentParser(description="Analyze video audio/visuals for fast jump-cut editing.")
    ap.add_argument("input_video", help="Path to source video file")
    ap.add_argument("--work-dir", required=True, help="Scratch working directory")
    ap.add_argument("--thresh-offset", type=float, default=12.0, help="dB above noise floor p10 (default: 12)")
    ap.add_argument("--min-pause", type=float, default=0.30, help="Minimum pause duration in seconds (default: 0.30)")
    ap.add_argument("--keep-pad", type=float, default=0.09, help="Padding kept on each side of trimmed pause (default: 0.09)")
    ap.add_argument("--chunk-sec", type=int, default=240, help="Split MP3 chunks if video longer than this (default: 240s)")
    args = ap.parse_args()

    t0 = time.time()
    os.makedirs(args.work_dir, exist_ok=True)
    meta = probe_video(args.input_video)

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_audio = ex.submit(extract_audio_assets, args.input_video, args.work_dir, meta["duration"], args.chunk_sec)
        f_sheet = ex.submit(make_contact_sheet, args.input_video, args.work_dir, meta)
        wav48, wav16, mp3_files = f_audio.result()
        sheet_path, sheet_step = f_sheet.result()

    dbs, db_stats = compute_db_envelope(wav16)
    thresh, timeline_txt, baseline_keeps = build_timeline_and_baseline(
        dbs, db_stats, meta["duration"], args.thresh_offset, args.min_pause, args.keep_pad
    )

    meta["db_stats"] = db_stats
    meta["silence_threshold_db"] = thresh
    meta["mp3_files"] = mp3_files
    meta["contact_sheet"] = sheet_path
    meta["contact_sheet_step_sec"] = round(sheet_step, 2)

    with open(os.path.join(args.work_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.work_dir, "db_10ms.json"), "w") as f:
        json.dump(dbs, f)
    with open(os.path.join(args.work_dir, "timeline.txt"), "w", encoding="utf-8") as f:
        f.write(timeline_txt + "\n")
    with open(os.path.join(args.work_dir, "baseline_keeps.json"), "w", encoding="utf-8") as f:
        json.dump(baseline_keeps, f, ensure_ascii=False, indent=2)

    base_dur = sum(k["end"] - k["start"] for k in baseline_keeps)
    print(f"Analyzed in {time.time()-t0:.2f}s:")
    print(f"  Video: {meta['width']}x{meta['height']} @ {meta['fps']}fps ({'VFR' if meta['is_vfr'] else 'CFR'}), {meta['video_codec']} {meta['pix_fmt']}, {'HDR ' + meta['color_transfer'] if meta['is_hdr'] else 'SDR'}, {meta['duration']:.2f}s ({meta['nb_frames']} frames)")
    if meta["is_hdr"]:
        print("  [HDR Tip] 10-bit HDR detected: use --color sdr for Douyin/Xiaohongshu/Bilibili to prevent overexposure, or --color keep for native HDR.")
    print(f"  Audio: {meta['audio_sr']}Hz {meta['audio_channels']}ch, noise={db_stats['p10']}dB, speech={db_stats['p75']}dB, thresh={thresh}dB")
    print(f"  Baseline pause-only trim: {meta['duration']:.2f}s -> {base_dur:.2f}s ({len(baseline_keeps)} segments)")
    print(f"  MP3(s): {', '.join(mp3_files)}")
    print(f"  Contact sheet (~{sheet_step:.1f}s/tile): {sheet_path}")
    print(f"  Timeline: {os.path.join(args.work_dir, 'timeline.txt')}")


if __name__ == "__main__":
    main()
