#!/usr/bin/env python3
"""
Upgraded Frame-Locked Jump-Cut & Polish Engine (v2).

Features:
- Frame-locked 0.0ms A/V sync with 12ms raised-cosine micro-fades
- Out-of-order / Golden 3-Second Hook segment support
- --voice-enhance: studio voice chain (80Hz HPF + afftdn + presence EQ + compressor + -15 LUFS loudnorm)
- --speed: subtle pacing boost (e.g. 1.08) with pitch-preserved audio
- --bgm: background music with automatic sidechaincompress ducking + optional --bgm-delay
- Per-segment semantic punch-in zoom ("zoom": 1.12 in cutlist.json)
- --color keep|sdr: native 10-bit HLG/PQ HDR preservation OR platform-safe Rec.709 SDR tone mapping
- --grade: subtle creator contrast/saturation/crispness boost
- --captions: Retina PingFang SC highlighted subtitles + optional chapter badges + .srt sidecar
- --fcpxml: instant 0-second Final Cut Pro FCPXML v1.10 timeline export
- Built-in end-syllable safety warning + post-render ffprobe verification
"""
from __future__ import annotations
import argparse
import array
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import wave

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)


def load_segments(cutlist_path: str, duration: float, fps: float) -> list[dict]:
    raw = json.load(open(cutlist_path, encoding="utf-8"))
    items = raw["segments"] if isinstance(raw, dict) and "segments" in raw else raw
    segs = []
    max_frame = int(round(duration * fps))
    for idx, it in enumerate(items, 1):
        s = float(it["start"] if "start" in it else it["start_sec"])
        e = float(it["end"] if "end" in it else it["end_sec"])
        lbl = str(it.get("label", ""))
        zoom = float(it.get("zoom", 1.0))
        zoom_y = float(it.get("zoom_y", 0.5))
        if zoom < 1.0 or zoom > 1.5:
            raise ValueError(f"Segment #{idx} zoom must be in [1.0, 1.5], got {zoom}")
        sf = max(0, int(round(s * fps)))
        ef = min(max_frame, int(round(e * fps)))
        if ef <= sf:
            raise ValueError(f"Segment #{idx} invalid or empty after frame snap: {s}-{e}")
        segs.append({
            "start_frame": sf,
            "end_frame": ef,
            "n_frames": ef - sf,
            "start_sec": round(sf / fps, 6),
            "end_sec": round(ef / fps, 6),
            "label": lbl,
            "zoom": round(zoom, 4),
            "zoom_y": max(0.15, min(0.85, round(zoom_y, 3))),
        })
    if not segs:
        raise ValueError("Cutlist contains no segments.")
    return segs


def check_ending_safety(segs: list[dict], work_dir: str, meta: dict):
    db_path = os.path.join(work_dir, "db_10ms.json")
    if not os.path.isfile(db_path):
        return
    dbs = json.load(open(db_path))
    thresh = meta.get("silence_threshold_db", -36.0)
    end_sec = segs[-1]["end_sec"]
    i0 = max(0, int(round((end_sec - 0.10) * 100)))
    i1 = min(len(dbs), int(round((end_sec + 0.05) * 100)))
    if i1 > i0:
        tail_max = max(dbs[i0:i1])
        if tail_max > thresh + 6.0:
            print(f"[WARNING] Final segment ends at {end_sec:.2f}s while audio is still active ({tail_max:.1f}dB vs thresh {thresh:.1f}dB). Consider extending end by 0.25-0.40s to avoid clipping the last syllable!")


def build_locked_voice_wav(work_dir: str, segs: list[dict], fps: float, fade_ms: float, end_fade_ms: float) -> tuple[str, int]:
    wav48 = os.path.join(work_dir, "audio_48k.wav")
    with wave.open(wav48, "rb") as wf:
        sr = wf.getframerate()
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)
    assert sw == 2 and ch == 2, f"Expected 16-bit stereo WAV, got ch={ch}, sw={sw}"

    samples = array.array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()

    fade_n = int(round(sr * fade_ms / 1000.0))
    start_fade_n = int(round(sr * 0.030))
    end_fade_n = int(round(sr * end_fade_ms / 1000.0))

    out = array.array("h")
    cum_video_frames = 0
    cum_audio_frames = 0

    for idx, seg in enumerate(segs):
        next_video_frames = cum_video_frames + seg["n_frames"]
        target_cum_audio = int(round(next_video_frames * sr / fps))
        seg_audio_len = target_cum_audio - cum_audio_frames

        src_f0 = int(round(seg["start_frame"] * sr / fps))
        src_f1 = min(nframes, src_f0 + seg_audio_len)
        chunk = array.array("h", samples[src_f0 * 2 : src_f1 * 2])
        if len(chunk) < seg_audio_len * 2:
            chunk.extend([0] * (seg_audio_len * 2 - len(chunk)))

        fi = start_fade_n if idx == 0 else min(fade_n, seg_audio_len // 4)
        fo = end_fade_n if idx == len(segs) - 1 else min(fade_n, seg_audio_len // 4)
        for i in range(fi):
            g = 0.5 * (1.0 - math.cos(math.pi * i / fi))
            chunk[i * 2] = int(chunk[i * 2] * g)
            chunk[i * 2 + 1] = int(chunk[i * 2 + 1] * g)
        for i in range(fo):
            p = seg_audio_len - 1 - i
            g = 0.5 * (1.0 - math.cos(math.pi * i / fo))
            chunk[p * 2] = int(chunk[p * 2] * g)
            chunk[p * 2 + 1] = int(chunk[p * 2 + 1] * g)

        out.extend(chunk)
        cum_video_frames = next_video_frames
        cum_audio_frames = target_cum_audio

    out_wav = os.path.join(work_dir, "edited_voice_raw.wav")
    if sys.byteorder != "little":
        out.byteswap()
    with wave.open(out_wav, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(out.tobytes())
    return out_wav, cum_video_frames


def ensure_voice_isolate_binary() -> str:
    bin_dir = os.path.join(SCRIPT_DIR, ".bin")
    bin_path = os.path.join(bin_dir, "voice_isolate")
    src_path = os.path.join(SCRIPT_DIR, "voice_isolate.swift")
    if not os.path.isfile(bin_path) or os.path.getmtime(src_path) > os.path.getmtime(bin_path):
        os.makedirs(bin_dir, exist_ok=True)
        print("Compiling native macOS AUSoundIsolation CLI (one-time)...")
        subprocess.run(["swiftc", "-O", src_path, "-o", bin_path], check=True)
    return bin_path


def run_two_pass_loudnorm(in_wav: str, out_wav: str, pre_filter: str, target_dur: float, target_lufs: float):
    """True 2-pass linear EBU R128 loudness normalization (zero pumping, broadcast accurate)."""
    ln_base = f"loudnorm=I={target_lufs:.1f}:TP=-1.5:LRA=9"
    pass1_af = f"{pre_filter},{ln_base}:print_format=json" if pre_filter else f"{ln_base}:print_format=json"
    p1 = subprocess.run(
        ["ffmpeg", "-y", "-i", in_wav, "-af", pass1_af, "-f", "null", "-"],
        capture_output=True, text=True, check=True
    )
    # Extract the last JSON object printed by loudnorm on stderr
    matches = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", p1.stderr, re.DOTALL)
    if matches:
        stats = json.loads(matches[-1])
        ln_pass2 = (
            f"{ln_base}:measured_I={stats['input_i']}:measured_TP={stats['input_tp']}"
            f":measured_LRA={stats['input_lra']}:measured_thresh={stats['input_thresh']}"
            f":offset={stats['target_offset']}:linear=true:print_format=summary"
        )
    else:
        ln_pass2 = ln_base

    pass2_af = f"{pre_filter},{ln_pass2},apad,atrim=0:{target_dur:.6f}" if pre_filter else f"{ln_pass2},apad,atrim=0:{target_dur:.6f}"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-i", in_wav,
        "-af", pass2_af,
        "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", out_wav
    ], check=True)


def process_audio_mix(
    work_dir: str,
    raw_voice_wav: str,
    target_dur: float,
    voice_enhance: bool,
    isolate_pct: float,
    denoise_engine: str,
    target_lufs: float,
    speed: float,
    bgm_path: str,
    bgm_vol_db: float,
    bgm_delay: float,
) -> str:
    """
    Two-stage broadcast voice pipeline + optional speed & sidechain-ducked BGM:
    - Stage 1: Apple Neural Engine AUSoundIsolation (macOS arm64) or FFmpeg afftdn fallback
    - Stage 2: Broadcast Mastering Chain (HPF 80Hz, warm 150Hz, de-mud 280Hz, presence 3.2kHz,
               de-ess 7kHz, air 10.5kHz, optical-style compressor, 2-pass linear EBU R128 loudnorm)
    - Stage 3: Optional auto-ducked BGM mix via sidechaincompress
    """
    if not voice_enhance and abs(speed - 1.0) < 1e-4 and not bgm_path:
        return raw_voice_wav

    is_apple_silicon = (platform.system() == "Darwin" and platform.machine() == "arm64")
    use_apple_iso = voice_enhance and isolate_pct > 0.5 and (
        denoise_engine == "apple" or (denoise_engine == "auto" and is_apple_silicon)
    )

    voice_src = raw_voice_wav
    if use_apple_iso:
        iso_wav = os.path.join(work_dir, "edited_voice_isolated.wav")
        try:
            iso_bin = ensure_voice_isolate_binary()
            subprocess.run([iso_bin, raw_voice_wav, iso_wav, f"{isolate_pct:.1f}"], check=True)
            voice_src = iso_wav
        except Exception as e:
            print(f"[WARNING] AUSoundIsolation failed ({e}); falling back to FFmpeg afftdn.")
            use_apple_iso = False

    voice_master_wav = os.path.join(work_dir, "edited_voice_mastered.wav")
    voice_chain = []
    if abs(speed - 1.0) >= 1e-4:
        voice_chain.append(f"atempo={speed:.5f}")
    if voice_enhance:
        voice_chain.append("highpass=f=80:poles=2")
        if not use_apple_iso and isolate_pct > 0.5:
            voice_chain.append("afftdn=nf=-25:tn=1")
        voice_chain += [
            "equalizer=f=150:t=q:w=1.0:g=1.5",
            "equalizer=f=280:t=q:w=1.4:g=-1.8",
            "equalizer=f=3200:t=q:w=1.2:g=2.2",
            "equalizer=f=7000:t=q:w=2.0:g=-1.5",
            "highshelf=f=10500:g=1.5",
            "acompressor=threshold=-20dB:ratio=2.8:attack=12:release=160:knee=4:makeup=2dB",
        ]
        run_two_pass_loudnorm(voice_src, voice_master_wav, ",".join(voice_chain), target_dur, target_lufs)
    else:
        v_filter = ",".join(voice_chain) if voice_chain else "anull"
        subprocess.run([
            "ffmpeg", "-y", "-v", "error",
            "-i", voice_src,
            "-af", f"{v_filter},apad,atrim=0:{target_dur:.6f}",
            "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", voice_master_wav
        ], check=True)

    if not bgm_path:
        return voice_master_wav

    # Stage 3: Sidechain-ducked BGM mix driven by the mastered voice track
    final_wav = os.path.join(work_dir, "edited_audio_final.wav")
    fade_out_st = max(0.0, target_dur - 2.2)
    bgm_gain = f"{bgm_vol_db:.1f}dB"
    delay_ms = int(round(max(0.0, bgm_delay) * 1000))
    bgm_chain = [
        f"atrim=0:{max(0.1, target_dur - bgm_delay):.6f}",
        "asetpts=PTS-STARTPTS",
        "afade=t=in:st=0:d=1.2",
        f"volume={bgm_gain}",
    ]
    if delay_ms > 0:
        bgm_chain.append(f"adelay={delay_ms}|{delay_ms}")
    bgm_chain += [
        f"apad,atrim=0:{target_dur:.6f}",
        f"afade=t=out:st={fade_out_st:.3f}:d=2.2",
    ]
    fc = (
        f"[0:a]asplit=2[v_mix][v_sc];"
        f"[1:a]{','.join(bgm_chain)}[bgm_base];"
        f"[bgm_base][v_sc]sidechaincompress=threshold=0.025:ratio=4.0:attack=30:release=380[bgm_duck];"
        f"[v_mix][bgm_duck]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[aout]"
    )
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-i", voice_master_wav,
        "-stream_loop", "-1", "-i", bgm_path,
        "-filter_complex", fc,
        "-map", "[aout]",
        "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", final_wav
    ], check=True)
    return final_wav


def ensure_subs_binary() -> str:
    bin_dir = os.path.join(SCRIPT_DIR, ".bin")
    bin_path = os.path.join(bin_dir, "render_subs")
    src_path = os.path.join(SCRIPT_DIR, "render_subs.swift")
    if not os.path.isfile(bin_path) or os.path.getmtime(src_path) > os.path.getmtime(bin_path):
        os.makedirs(bin_dir, exist_ok=True)
        print("Compiling native macOS subtitle renderer (one-time)...")
        subprocess.run(["swiftc", "-O", src_path, "-o", bin_path], check=True)
    return bin_path


def prepare_subtitles(captions_path: str, width: int, height: int, total_dur: float, work_dir: str, srt_out: str) -> dict:
    subs_dir = os.path.join(work_dir, "subs_png")
    if os.path.isdir(subs_dir):
        shutil.rmtree(subs_dir)
    bin_path = ensure_subs_binary()
    subprocess.run([
        bin_path, captions_path, str(width), str(height), f"{total_dur:.4f}", subs_dir, srt_out
    ], check=True)
    return json.load(open(os.path.join(subs_dir, "subs_meta.json"), encoding="utf-8"))


def split_monotonic_groups(segs: list[dict]) -> list[list[dict]]:
    """Groups segments into minimal strictly chronological runs (1 group unless Hook reordered)."""
    groups = []
    cur = []
    prev_ef = -1
    for s in segs:
        if cur and s["start_frame"] < prev_ef:
            groups.append(cur)
            cur = [s]
        else:
            cur.append(s)
        prev_ef = s["end_frame"]
    if cur:
        groups.append(cur)
    return groups


def build_zoom_filter(segs: list[dict], width: int, height: int) -> list[str]:
    """Builds per-output-frame dynamic punch-in zoom expression (supports head-safe zoom_y anchor for talking-head)."""
    zoom_ranges = []
    cur_f = 0
    for s in segs:
        nf = s["n_frames"]
        if s["zoom"] > 1.001:
            zoom_ranges.append((cur_f, cur_f + nf - 1, s["zoom"], s.get("zoom_y", 0.5)))
        cur_f += nf
    if not zoom_ranges:
        return []
    z_expr = "1"
    y_expr = "0.5"
    for a, b, z, zy in reversed(zoom_ranges):
        z_expr = f"if(between(n,{a},{b}),{z:.4f},{z_expr})"
        y_expr = f"if(between(n,{a},{b}),{zy:.3f},{y_expr})"
    return [
        f"scale=w='trunc({width}*({z_expr})/2)*2':h='trunc({height}*({z_expr})/2)*2':eval=frame",
        f"crop=w={width}:h={height}:x='(iw-{width})/2':y='(ih-{height})*({y_expr})'",
    ]


def auto_bitrate(meta: dict, target_sdr: bool) -> str:
    pixels = meta["width"] * meta["height"]
    fps = meta["fps"]
    if pixels >= 3840 * 2160 * 0.9:
        mbps = 45 if (fps >= 48 and not target_sdr) else (35 if fps >= 48 else 24)
    elif pixels >= 2560 * 1440 * 0.9:
        mbps = 26 if fps >= 48 else 16
    elif pixels >= 1920 * 1080 * 0.9:
        mbps = 16 if fps >= 48 else 10
    else:
        mbps = 8 if fps >= 48 else 5
    src_mbps = meta.get("video_bitrate", 0) / 1_000_000.0
    if src_mbps > 1.0:
        mbps = min(mbps, max(4, int(round(src_mbps * 1.15))))
    return f"{mbps}M"


def build_color_and_grade_filters(meta: dict, color_mode: str, grade: bool, is_mac: bool) -> tuple[list[str], list[str], list[str]]:
    """Returns (video_filters, encoder_args, color_tag_args)."""
    is_hdr = meta["is_hdr"]
    is_10bit = meta["is_10bit"]
    convert_sdr = (color_mode == "sdr") and is_hdr

    vfilters = []
    if convert_sdr:
        # Verified to match Apple native HLG -> Rec.709 SDR tone mapping without overexposure
        trc_in = "smpte2084" if meta.get("color_transfer") == "smpte2084" else "bt2020-10"
        vfilters.append(f"colorspace=all=bt709:iall=bt2020:itrc={trc_in}:fast=1")
    if grade:
        vfilters.append("eq=contrast=1.04:saturation=1.05")
        vfilters.append("unsharp=3:3:0.35:3:3:0.0")

    target_10bit = (is_hdr or is_10bit) and not convert_sdr
    bitrate = auto_bitrate(meta, target_sdr=convert_sdr)

    if target_10bit:
        vfilters.append("format=p010le" if is_mac else "format=yuv420p10le")
        enc = (["-c:v", "hevc_videotoolbox", "-profile:v", "main10", "-tag:v", "hvc1", "-b:v", bitrate] if is_mac
               else ["-c:v", "libx265", "-crf", "18", "-preset", "fast", "-tag:v", "hvc1"])
        tags = []
        if meta.get("color_primaries"): tags += ["-color_primaries", meta["color_primaries"]]
        if meta.get("color_transfer"): tags += ["-color_trc", meta["color_transfer"]]
        if meta.get("color_space"): tags += ["-colorspace", meta["color_space"]]
        if meta.get("color_range"): tags += ["-color_range", meta["color_range"]]
    else:
        vfilters.append("format=yuv420p")
        if is_mac:
            enc = (["-c:v", "h264_videotoolbox", "-profile:v", "high", "-b:v", bitrate] if convert_sdr or meta["video_codec"] != "hevc"
                   else ["-c:v", "hevc_videotoolbox", "-tag:v", "hvc1", "-b:v", bitrate])
        else:
            enc = ["-c:v", "libx264", "-crf", "18", "-preset", "fast"]
        tags = ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv"]

    return vfilters, enc, tags


def build_privacy_blur_filters(blur_regions: list[str], width: int, height: int, in_label: str, out_label: str) -> list[str]:
    """Applies Gaussian blur to normalized (x,y,w,h in 0..1) privacy regions (e.g. background monitors/labels)."""
    if not blur_regions:
        return []
    parts = []
    cur = in_label
    for idx, br in enumerate(blur_regions):
        fx, fy, fw, fh = map(float, br.split(","))
        bx = max(0, int(round(fx * width))) & ~1
        by = max(0, int(round(fy * height))) & ~1
        bw = max(2, min(width - bx, int(round(fw * width)))) & ~1
        bh = max(2, min(height - by, int(round(fh * height)))) & ~1
        nxt = out_label if idx == len(blur_regions) - 1 else f"[v_pblur_{idx}]"
        parts.append(
            f"{cur}split[pbg{idx}][pfg{idx}];"
            f"[pfg{idx}]crop={bw}:{bh}:{bx}:{by},gblur=sigma=28[pbl{idx}];"
            f"[pbg{idx}][pbl{idx}]overlay={bx}:{by}{nxt}"
        )
        cur = nxt
    return parts


def render_video(
    work_dir: str,
    meta: dict,
    segs: list[dict],
    audio_wav: str,
    total_frames: int,
    out_mp4: str,
    color_mode: str,
    grade: bool,
    speed: float,
    bitrate_opt: str,
    blur_regions: list[str],
    subs_meta: dict | None,
):
    fps = meta["fps"]
    fps_str = f"{fps:.6f}".rstrip("0").rstrip(".")
    is_mac = platform.system() == "Darwin"
    w, h = meta["width"], meta["height"]
    if abs(meta.get("rotation", 0)) in (90, 270):
        w, h = h, w

    groups = split_monotonic_groups(segs)
    color_filters, enc_args, color_tags = build_color_and_grade_filters(meta, color_mode, grade, is_mac)
    if bitrate_opt != "auto":
        if "-b:v" in enc_args:
            enc_args[enc_args.index("-b:v") + 1] = bitrate_opt

    zoom_filters = build_zoom_filter(segs, w, h)
    # Build filtergraph: supports single monotonic pass OR multi-group (Hook + Body) concat!
    cmd = ["ffmpeg", "-y", "-v", "warning", "-stats"]
    fc_parts = []
    if len(groups) == 1:
        if is_mac:
            cmd += ["-hwaccel", "videotoolbox"]
        cmd += ["-i", meta["input_path"], "-i", audio_wav]
        expr = "+".join(f"between(n,{s['start_frame']},{s['end_frame']-1})" for s in segs)
        chain = []
        if meta["is_vfr"]:
            chain.append(f"fps={fps_str}")
        chain += [f"select='{expr}'", f"setpts=N/{fps_str}/TB"]
        fc_parts.append(f"[0:v]{','.join(chain)}[v_sel]")
        sub_input_idx = 2
    else:
        # Out-of-order Hook + Body: add input per group with -to early stop so Hook doesn't decode the whole file
        for g_idx, grp in enumerate(groups):
            end_limit = grp[-1]["end_sec"] + 0.5
            if is_mac:
                cmd += ["-hwaccel", "videotoolbox"]
            cmd += ["-to", f"{end_limit:.3f}", "-i", meta["input_path"]]
        cmd += ["-i", audio_wav]
        audio_input_idx = len(groups)
        sub_input_idx = len(groups) + 1
        concat_ins = []
        for g_idx, grp in enumerate(groups):
            expr = "+".join(f"between(n,{s['start_frame']},{s['end_frame']-1})" for s in grp)
            chain = ([f"fps={fps_str}"] if meta["is_vfr"] else []) + [f"select='{expr}'", f"setpts=N/{fps_str}/TB"]
            fc_parts.append(f"[{g_idx}:v]{','.join(chain)}[vg{g_idx}]")
            concat_ins.append(f"[vg{g_idx}]")
        fc_parts.append(f"{''.join(concat_ins)}concat=n={len(groups)}:v=1:a=0[v_sel]")

    audio_map = "1:a:0" if len(groups) == 1 else f"{len(groups)}:a:0"

    # Optional privacy blur (before zoom/color/subs so blurred area scales naturally with zoom and never blurs subtitles!)
    cur_v = "[v_sel]"
    if blur_regions:
        fc_parts += build_privacy_blur_filters(blur_regions, w, h, cur_v, "[v_priv]")
        cur_v = "[v_priv]"

    # Optional punch-in zoom, speed, color/grade, and subtitle overlay
    post_chain = []
    post_chain += zoom_filters
    if abs(speed - 1.0) >= 1e-4:
        post_chain += [f"setpts=PTS/{speed:.5f}", f"fps={fps_str}"]
    # Apply color conversion & grading BEFORE subtitle overlay so subtitles stay crisp pure white/gold!
    pre_sub_color = [f for f in color_filters if not f.startswith("format=")]
    final_fmt = [f for f in color_filters if f.startswith("format=")]
    post_chain += pre_sub_color

    if subs_meta:
        cmd += ["-f", "concat", "-safe", "0", "-i", subs_meta["concat_path"]]
        if post_chain:
            fc_parts.append(f"{cur_v}{','.join(post_chain)}[v_pre]")
            v_base = "[v_pre]"
        else:
            v_base = cur_v
        # Note: overlay requires rgb/yuv alpha blending; format=auto handles 10-bit or 8-bit cleanly
        oy = subs_meta["overlay_y"]
        fmt_str = ("," + ",".join(final_fmt)) if final_fmt else ""
        fc_parts.append(f"{v_base}[{sub_input_idx}:v]overlay=0:{oy}:eof_action=pass:format=auto{fmt_str}[v_out]")
    else:
        post_chain += final_fmt
        if post_chain:
            fc_parts.append(f"{cur_v}{','.join(post_chain)}[v_out]")
        else:
            fc_parts.append(f"{cur_v}null[v_out]")

    cmd += [
        "-filter_complex", ";".join(fc_parts),
        "-map", "[v_out]", "-map", audio_map,
        "-fps_mode", "passthrough" if abs(speed - 1.0) < 1e-4 else "cfr",
    ]
    cmd += enc_args + color_tags + [
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart",
        out_mp4,
    ]

    expected_dur = (total_frames / fps) / speed
    expected_frames = int(round(expected_dur * fps))
    t0 = time.time()
    mode_desc = f"{'SDR Rec.709' if (color_mode == 'sdr' and meta['is_hdr']) else ('10-bit HDR' if meta['is_hdr'] else 'SDR')}"
    extras = [x for x in [
        f"speed={speed}x" if abs(speed - 1.0) >= 1e-4 else "",
        f"blur={len(blur_regions)}" if blur_regions else "",
        "zoom" if zoom_filters else "",
        "grade" if grade else "",
        "subs" if subs_meta else "",
        f"groups={len(groups)}" if len(groups) > 1 else "",
    ] if x]
    print(f"Rendering ~{expected_frames} frames ({expected_dur:.2f}s) -> {out_mp4} [{mode_desc}{', ' + ', '.join(extras) if extras else ''}]...")
    subprocess.run(cmd, check=True)
    elapsed = time.time() - t0

    # Automatic post-render verification
    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", out_mp4
    ]))
    vs = next(s for s in probe["streams"] if s["codec_type"] == "video")
    aus = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    v_frames = int(vs.get("nb_frames", 0))
    v_dur = float(vs.get("duration", 0))
    a_dur = float(aus.get("duration", 0))
    size_mb = os.path.getsize(out_mp4) / (1024 * 1024)

    print(f"\nRender complete in {elapsed:.1f}s ({size_mb:.1f} MB):")
    print(f"  Video: {vs['width']}x{vs['height']} {vs['codec_name']} ({vs.get('profile','')}) {vs.get('pix_fmt','')} {vs.get('color_primaries','')}/{vs.get('color_transfer','')} | frames={v_frames} (exp ~{expected_frames}) | dur={v_dur:.3f}s")
    print(f"  Audio: {aus['codec_name']} {aus['sample_rate']}Hz {aus['channels']}ch | dur={a_dur:.3f}s | sync_diff={abs(v_dur-a_dur)*1000:.1f}ms")
    if abs(speed - 1.0) < 1e-4 and v_frames != expected_frames:
        print(f"  [WARNING] Frame count mismatch: got {v_frames}, expected {expected_frames}")
    if abs(v_dur - a_dur) > 0.08:
        print(f"  [WARNING] A/V duration diff exceeds 80ms: {abs(v_dur - a_dur):.3f}s")

    # Export ending audio check & fast keyframe visual sheet
    end_mp3 = os.path.join(work_dir, "verify_ending.mp3")
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-sseof", "-5", "-i", out_mp4,
        "-c:a", "libmp3lame", "-b:a", "128k", end_mp3
    ], check=True)

    verify_jpg = os.path.join(work_dir, "verify_sheet.jpg")
    step = max(0.5, v_dur / 16.0)
    vw, vh = int(vs["width"]), int(vs["height"])
    tw = 180 if vh >= vw else 240
    th = int(round(tw * vh / vw)) // 2 * 2
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-skip_frame", "nokey",
        *(["-hwaccel", "videotoolbox"] if is_mac else []),
        "-i", out_mp4,
        "-vf", f"fps=1/{step:.3f},scale={tw}:{th},tile=8x2",
        "-frames:v", "1", "-q:v", "4", verify_jpg
    ], check=True)
    print(f"  Verify ending audio: {end_mp3}")
    print(f"  Verify visual sheet: {verify_jpg}")


def main():
    ap = argparse.ArgumentParser(description="Frame-locked jump-cut preview, video polish renderer, and FCPXML exporter.")
    ap.add_argument("work_dir", help="Working directory from analyze.py")
    ap.add_argument("cutlist", help="JSON keep-list file")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preview", action="store_true", help="Build frame-locked audio preview.mp3 (< 2s)")
    mode.add_argument("--render", metavar="OUT_MP4", help="Render final polished MP4 and verify")
    mode.add_argument("--fcpxml-only", metavar="OUT_FCPXML", help="Export 0-second Final Cut Pro .fcpxml only")

    ap.add_argument("--voice-enhance", action="store_true", default=True, help="Two-stage broadcast voice polish (DEFAULT ON; use --no-voice-enhance to disable)")
    ap.add_argument("--no-voice-enhance", dest="voice_enhance", action="store_false", help="Disable voice enhancement & neural denoising")
    ap.add_argument("--isolate", type=float, default=80.0, help="Neural voice isolation wet/dry mix 0-100 (default: 80; 75-85 for unboxing, 90-100 for noisy rooms, 0=mastering only)")
    ap.add_argument("--denoise-engine", choices=["auto", "apple", "ffmpeg"], default="auto", help="Stage-1 denoise engine (default: auto -> Apple AUSoundIsolation on Apple Silicon)")
    ap.add_argument("--lufs", type=float, default=-15.0, help="Target integrated loudness in LUFS (default: -15.0)")
    ap.add_argument("--speed", type=float, default=1.0, help="Global speed multiplier, e.g. 1.08 (default: 1.0)")
    ap.add_argument("--bgm", default="", help="Optional background music audio file (auto-ducked via sidechaincompress)")
    ap.add_argument("--bgm-vol", type=float, default=-23.0, help="BGM base volume in dB before ducking (default: -23.0)")
    ap.add_argument("--bgm-delay", type=float, default=0.0, help="Seconds to delay BGM entry, e.g. 3.0 after Hook (default: 0.0)")
    ap.add_argument("--color", choices=["sdr", "keep"], default="sdr", help="Color mode (DEFAULT: sdr -> converts HDR to platform-safe Rec.709 SDR; use keep for native HDR)")
    ap.add_argument("--grade", action="store_true", default=True, help="Apply subtle creator polish (DEFAULT ON; use --no-grade to disable)")
    ap.add_argument("--no-grade", dest="grade", action="store_false", help="Disable subtle color grade & unsharp")
    ap.add_argument("--blur-region", action="append", default=[], help='Normalized privacy blur box "x,y,w,h" in 0..1 (repeatable, e.g. "0,0,1.0,0.22" for background monitors)')
    ap.add_argument("--captions", default="", help="Optional captions.json for Retina PingFang SC burned-in subtitles + .srt")
    ap.add_argument("--fcpxml", default="", help="Also export Final Cut Pro .fcpxml alongside --render")
    ap.add_argument("--fade-ms", type=float, default=12.0, help="Internal micro-fade duration in ms (default: 12)")
    ap.add_argument("--end-fade-ms", type=float, default=100.0, help="Ending fade-out duration in ms (default: 100)")
    ap.add_argument("--bitrate", default="auto", help='Target video bitrate (default: "auto", e.g. "45M")')
    args = ap.parse_args()

    meta = json.load(open(os.path.join(args.work_dir, "meta.json"), encoding="utf-8"))
    fps = meta["fps"]
    segs = load_segments(args.cutlist, meta["duration"], fps)
    check_ending_safety(segs, args.work_dir, meta)

    if args.fcpxml_only:
        from export_fcpxml import export_fcpxml
        caps = json.load(open(args.captions, encoding="utf-8")) if args.captions else None
        export_fcpxml(meta, segs, args.fcpxml_only, caps)
        return

    raw_voice_wav, total_frames = build_locked_voice_wav(args.work_dir, segs, fps, args.fade_ms, args.end_fade_ms)
    edited_dur = (total_frames / fps) / args.speed

    cur = 0.0
    for idx, s in enumerate(segs, 1):
        d = (s["n_frames"] / fps) / args.speed
        ztag = f" [zoom {s['zoom']}x]" if s["zoom"] > 1.001 else ""
        print(f"[{idx:02d}] {cur:6.2f}s -> {cur+d:6.2f}s (src {s['start_sec']:6.2f}-{s['end_sec']:6.2f}, {d:4.2f}s){ztag} {s['label']}")
        cur += d
    saved = meta["duration"] - edited_dur
    print(f"\nOriginal: {meta['duration']:.2f}s -> Edited: {edited_dur:.2f}s (Cut {saved:.2f}s = {saved/meta['duration']*100:.1f}%, {len(segs)} segments)")

    final_audio_wav = process_audio_mix(
        args.work_dir, raw_voice_wav, edited_dur,
        args.voice_enhance, args.isolate, args.denoise_engine, args.lufs,
        args.speed, args.bgm, args.bgm_vol, args.bgm_delay
    )

    if args.preview:
        prev_mp3 = os.path.join(args.work_dir, "preview.mp3")
        subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-i", final_audio_wav,
            "-c:a", "libmp3lame", "-b:a", "128k", prev_mp3
        ], check=True)
        print(f"Preview ready: {prev_mp3}")
        return

    subs_meta = None
    if args.captions:
        w, h = meta["width"], meta["height"]
        if abs(meta.get("rotation", 0)) in (90, 270):
            w, h = h, w
        srt_out = os.path.splitext(args.render)[0] + ".srt"
        subs_meta = prepare_subtitles(args.captions, w, h, edited_dur, args.work_dir, srt_out)
        print(f"SRT sidecar written: {srt_out}")

    if args.fcpxml:
        from export_fcpxml import export_fcpxml
        caps = json.load(open(args.captions, encoding="utf-8")) if args.captions else None
        export_fcpxml(meta, segs, args.fcpxml, caps)

    render_video(
        args.work_dir, meta, segs, final_audio_wav, total_frames,
        args.render, args.color, args.grade, args.speed, args.bitrate,
        args.blur_region, subs_meta
    )


if __name__ == "__main__":
    main()
