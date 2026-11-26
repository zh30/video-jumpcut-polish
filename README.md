# Video Jump-Cut Polish & Publish Kit

> **Built natively for macOS creators** (`macOS 14+ Sonoma` · Apple Silicon M1–M4+ recommended · Zero Python third-party dependencies · MIT License)

An end-to-end **Agent Skill** (compatible with Antigravity, Claude Code, Cursor, Codex, and other Agent Skills-compatible agents) that turns raw camera footage into a complete, ready-to-publish delivery bundle on macOS.

Drop in a single raw video — whether a **solo talking-head**, **video podcast**, or **product unboxing/review** — and get back a polished video, broadcast-mastered audio, subtitles, subject-faithful high-CTR covers, and SEO-audited publishing copy for **YouTube, Bilibili, Xiaohongshu, Douyin, and WeChat Channels**.

---

## Why This Skill?

Recording a video takes 10 minutes; the tedious post-production and pre-publish busywork takes 2 hours:
- Cutting dead air, stutters, restarts, and verbal tics without breaking A/V sync
- Removing room echo/fan hum and leveling voice loudness to platform broadcast targets
- Converting iPhone 10-bit HLG/PQ HDR to SDR so platforms don't blow out highlights
- Blurring accidentally visible monitors, addresses, or QR codes
- Designing click-worthy covers without AI hallucinating your face or product details
- Writing platform-specific titles, descriptions, chapters, hashtags, and pinned comments that pass compliance and truncation limits

`video-jumpcut-polish` automates the entire pipeline with **zero Python third-party packages** — powered by `ffmpeg`, Python standard library, and native macOS Swift helpers (`AVAudioEngine` / `AUSoundIsolation`, Apple Vision, CoreText, and VideoToolbox hardware encoding).

---

## Genre-Adaptive Pipeline

Instead of forcing one rigid template onto every video, the skill detects your content genre and adapts pacing, voice processing, framing, subtitles, covers, and copywriting automatically:

| Genre | Pacing & Cuts | Voice & Loudness | Punch-In Framing | Subtitles | Cover & Copy Style |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Solo Talking-Head** | Tight & punchy (`0.12–0.38s` beats); strips all fillers & stutters | `AUSoundIsolation` 90% + `-15 LUFS` | `1.12×` zoom with head-safe `zoom_y=0.35` anchor | Retina highlighted burn-in + `.srt` + chapter pills | Portrait-faithful cover + PAS takeaways copy |
| **Video Podcast** | Human breathing room (`0.22–0.65s` beats); removes only dead air & major stumbles | `AUSoundIsolation` 88% + `-16 LUFS` | Subtle `1.06×` on chapter shifts only | `.srt` sidecar + subtle chapter badges | Editorial podcast cover + Show Notes, `00:00` chapters & golden quotes |
| **Product Unboxing / Review** | Tight speech while preserving tactile reveals & clicks | `AUSoundIsolation` 78% + `-15 LUFS` | `1.12×` centered on product specs | Retina highlighted burn-in + `.srt` + chapter pills | Dual-Insurance hardware-faithful cover + honest KOC pros/cons copy |

---

## Feature Matrix

### Default ON (Runs Automatically)
1. **2-Second Media Analysis (`analyze.py`)** — Keyframe-only overview contact sheet (`-skip_frame nokey`), 10 ms RMS pause/energy timeline, HDR/VFR probe, and compact MP3 extraction.
2. **Frame-Accurate Jump-Cut Cleanup (`inspect_regions.py` + `render.py`)** — Strips pauses, fillers, stutters, restarts, and heavy breaths with 12 ms cosine micro-fades and verified **0.0 ms A/V sync**.
3. **Apple Neural Engine Voice Isolation + 2-Pass Broadcast Mastering (`voice_isolate.swift`)** — Native macOS `AUSoundIsolation` (same ML denoise/dereverb engine used in Final Cut Pro, with automatic 76.4 ms lookahead latency compensation) followed by 6-band broadcast EQ, optical compression, and 2-pass linear loudness normalization (`-15 / -16 LUFS`, `-1.5 dBTP`).
4. **Visual Privacy Blur** — Scans the contact sheet for readable monitors, shipping labels, chat windows, or QR codes and applies local Gaussian blur (`--blur-region`) in the same render pass.
5. **Platform-Safe HDR → SDR Color Mapping & Subtle Grade** — Converts 10-bit BT.2020 HLG/PQ footage to Apple-accurate Rec.709 SDR with subtle contrast/saturation/unsharp polish (pass `--color keep` for native HDR).
6. **Head-Safe Semantic Punch-In Zoom** — Applies `1.06×–1.12×` punch-ins on narrative shifts (never on a mechanical timer) with configurable `zoom_y` so heads are never clipped.
7. **Retina Subtitles, Chapter Pills & `.srt` (`render_subs.swift`)** — Native CoreText crisp Retina subtitles with `*keyword*` gold highlights, top-left chapter badges, and standard `.srt` sidecar output.
8. **Dual-Insurance Subject-Faithful Covers (`product_tools.swift` + `make_covers.swift`)** — Samples 7 frames per timestamp to pick the sharpest zero-blur frame via Laplacian variance, tight-crops the subject, and generates Apple Vision transparent PNG cutouts. Pairs seamlessly with **Google Flow MCP** (Track A: high-fidelity studio relighting; Track B: 100% pixel-authentic real cutout composited onto AI studio backdrops) with an instant offline Swift cover generator fallback.
9. **5-Platform High-Exposure Copywriting & Automated CTR/SEO/Compliance Linter (`publish_kit.py` + `copywriting_playbook.md`)** — Generates 3 distinct title angles per platform (Pain/Contrast, Quantified Number/Value, Search-Intent) strictly complementary to the cover headline, builds a 3-tier SEO keyword matrix (`core / long_tail / question`), and automatically lints platform truncation folds, cover-title duplication, AI clichés, SEO keyword coverage, and compliance/off-platform risks.

### Optional Enhancements
- **Custom Royalty-Free BGM with Auto-Ducking** (`--bgm`, works seamlessly with **ACE Music MCP** or any local audio track)
- **Golden 3-Second Hook Reordering** (out-of-order cutlist segments supported natively)
- **Global Speed-Up** (`--speed 1.06` with natural pitch preservation)
- **0-Second Final Cut Pro Timeline Export** (`export_fcpxml.py` → `.fcpxml`)

---

## Output Bundle Structure

Every run produces a clean delivery folder alongside your source video without ever modifying the original file:

```text
<video_name>_成品发布包/
├── <video_name>_精剪成片.mp4        # Polished video (0.0ms A/V sync, hardware-encoded)
├── <video_name>_精剪成片.srt        # Sidecar subtitles (YouTube / Bilibili)
├── 封面_小红书_3x4.jpg              # 1080×1440 (3:4 feed safe zone)
├── 封面_抖音视频号_9x16.jpg         # 1080×1920 (clears right icons & bottom 22%)
├── 封面_B站YouTube_16x9.jpg        # 1920×1080 (clears bottom-right duration badge)
└── 发布文案与自查清单.md             # 5-platform titles, copy, chapters, tags, pinned comments & audit report
```

---

## Requirements & Device Compatibility

### Supported Devices

| Platform | Support Level | Notes |
| :--- | :--- | :--- |
| **Apple Silicon Mac (M1–M4+) + macOS 14+ (Sonoma/Sequoia)** | **Full (Recommended)** | Full hardware pipeline: Apple Neural Engine `AUSoundIsolation`, Apple Vision subject cutout, CoreText Retina subtitles, and VideoToolbox 4K encoding. |
| **Intel Mac + macOS 14+** | **Supported (CPU/FFmpeg denoise fallback)** | Video editing, subtitles, Vision cutout, covers, and copywriting work normally; `AUSoundIsolation` automatically falls back to FFmpeg denoising if unavailable. |
| **macOS < 14.0** | **Partial** | Apple Vision foreground cutout (`VNGenerateForegroundInstanceMaskRequest`) requires macOS 14+ and is skipped automatically on older releases. |
| **Windows / Linux** | **Not currently supported** | Core video, audio isolation, subtitle rendering, and cutout helpers rely directly on native Apple macOS frameworks (`AVAudioEngine`, `Vision`, `CoreText`, `VideoToolbox`) for zero-install speed. |

### Required Tools (macOS)
- **macOS 14.0+** (Apple Silicon strongly recommended)
- **Xcode Command Line Tools** (`swiftc`):
  ```bash
  xcode-select --install
  ```
- **FFmpeg & FFprobe**:
  ```bash
  brew install ffmpeg
  ```
- **Python 3.9+** (standard library only — zero `pip install` needed)

> **Note:** On first run, the Python scripts automatically compile the four Swift helpers into `scripts/.bin/` (`swiftc -O`, ~2 seconds one-time). Precompiled binaries are intentionally excluded from this repository.

### Optional MCP Servers (Auto-Detected)
- **Google Flow MCP (`gflow-cli`)** — Generates studio-lit commercial covers with Dual-Insurance real-subject fidelity. If not installed, the skill automatically falls back to the local Swift cover generator (`make_covers.swift`).
- **ACE Music MCP (`ace-music`)** — Generates custom vocal-free instrumental background music matched to your video's mood.

---

## Installation

### Option 1: Universal Agent Skills CLI (Recommended)
Works with Antigravity, Claude Code, Cursor, Codex, and other skills-compatible agents:

```bash
npx skills add zh30/video-jumpcut-polish
```

### Option 2: Antigravity Global Skill (Manual / Symlink)
```bash
git clone https://github.com/zh30/video-jumpcut-polish.git ~/Code/video-jumpcut-polish
ln -s ~/Code/video-jumpcut-polish/skills/video-jumpcut-polish ~/.gemini/config/skills/video-jumpcut-polish
```

### Option 3: Project-Level Workspace Skill
Copy `skills/video-jumpcut-polish/` into your project's `.agents/skills/video-jumpcut-polish/` directory.

---

## Usage Examples

Once installed, simply share a raw video path with your AI agent and describe what you want:

- *"Clean up `/path/to/raw_talk.mp4` — remove pauses, stutters, and filler words, enhance my voice, add subtitles, and build the full publishing kit."*
- *"Edit this video podcast `/path/to/ep12.mp4` with natural breathing pauses, -16 LUFS loudness, Show Notes chapters, and covers."*
- *"Polish `/path/to/unboxing.mp4`, blur the monitor behind me, add subtle lo-fi BGM, and generate high-CTR covers and copy for YouTube, Bilibili, and Xiaohongshu."*

---

## Repository Structure

```text
video-jumpcut-polish/
├── README.md
├── LICENSE
├── plugin.json                              # Antigravity plugin manifest
└── skills/
    └── video-jumpcut-polish/
        ├── SKILL.md                         # Main workflow & genre adaptation rules
        ├── references/
        │   └── copywriting_playbook.md      # 5-platform CTR, SEO & genre copywriting guide
        └── scripts/
            ├── analyze.py                   # Fast media probe, MP3 extract, 10ms RMS & keyframe sheet
            ├── inspect_regions.py           # Micro-slicing & 50ms ASCII waveform inspection
            ├── render.py                    # Preview audio, voice mastering, HDR->SDR, zoom, render
            ├── export_fcpxml.py             # 0-second Final Cut Pro FCPXML exporter
            ├── publish_kit.py               # Sharpest-frame extractor, CTR/SEO/compliance linter & kit builder
            ├── voice_isolate.swift          # Apple Neural Engine AUSoundIsolation (0ms latency-compensated)
            ├── render_subs.swift            # Native CoreText Retina subtitle & chapter badge renderer
            ├── make_covers.swift            # Instant local 3-ratio cover renderer (offline fallback)
            └── product_tools.swift          # Laplacian sharpness picker, Vision cutout & shadow compositor
```

---

## License

[MIT](./LICENSE) © 2026 Henry Zhang
