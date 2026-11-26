---
name: video-jumpcut-polish
description: >-
  End-to-end automated video editor and pre-publish packaging pipeline that turns
  a rough raw video — whether solo talking-head (口播/知识分享), video podcast
  (个人播客/视频播客/访谈), or product unboxing/review (开箱/测评) — into a
  complete, ready-to-publish delivery bundle. Automatically adapts pacing,
  neural voice isolation strength, loudness (-15/-16 LUFS), head-safe zoom
  framing, subtitles, and subject-faithful high-CTR covers (portrait OR product)
  to the detected video genre. Defaults ON: frame-accurate jump-cut removal of
  pauses/stutters/verbal tics (口癖/语气词/停顿/卡壳), Apple Neural Engine
  denoising (AUSoundIsolation) + 2-pass broadcast voice mastering, visual privacy
  blur, HDR-to-SDR platform-safe tone mapping + subtle grade, 3 platform covers
  via Google Flow MCP (with Dual-Insurance real-subject fidelity), compliance
  audit, and platform-tailored publishing copy/chapters/pinned comments. Use
  whenever the user shares a raw video and wants it cleaned, polished, or
  prepared for publishing (把视频剪掉停顿口癖、口播精剪、视频播客后期、处理视频准备发布).
---

# Video Jump-Cut Polish & Publish Kit

Drop in a raw camera video and deliver a complete, ready-to-publish folder
(`<input_stem>_成品发布包/` beside the input file; original never overwritten):

```text
<视频名>_成品发布包/
├── <视频名>_精剪成片.mp4        # Polished video (0.0ms A/V sync)
├── <视频名>_精剪成片.srt        # Standard sidecar subtitles (Bilibili/YouTube)
├── 封面_小红书_3x4.jpg          # 1080×1440 (3:4 waterfall safe zone)
├── 封面_抖音视频号_9x16.jpg     # 1080×1920 (clears right icons & bottom 22%)
├── 封面_B站YouTube_16x9.jpg    # 1920×1080 (clears bottom-right duration badge)
└── 发布文案与自查清单.md         # Compliance scan + platform titles/copy/tags/chapters/pinned comments
```

## Auto Content-Type Adaptation (Detect in Step 2)

After listening to `audio_full.mp3` and inspecting `contact_sheet.jpg`, classify
the video into one of 3 genres and automatically apply its tailored defaults
(never force an unboxing template onto a podcast or talking-head video!):

| Genre | Pacing & Cut Style | Voice & Loudness | Framing / Zoom | Subtitles | Cover Strategy (Dual-Insurance Subject Fidelity) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Solo Talking-Head (单人口播 / 观点 / 干货)** | Crisp & punchy: `0.12–0.22s` clause gaps, `0.28–0.38s` topic breaks; cut all `嗯/呃/然后` & stutters | `--isolate 90` (ultra-clean studio vocal), `--lufs -15` | `"zoom": 1.12`, **`"zoom_y": 0.35`** (head-safe upper anchor so punch-in never clips speaker's head!) | Full Retina PingFang SC highlighted burn-in + `.srt` + chapter badges | **Portrait Fidelity**: pick sharpest expressive non-blinking frame (eyes open, natural smile/emphasis); Track A (`nano-pro` studio relight preserving exact face likeness, or `@Character` if saved in Flow) / Track B (Apple Vision real portrait cutout + AI studio backdrop & bold thesis headline) |
| **2. Video Podcast / Monologue (个人播客 / 视频播客 / 深度访谈)** | **Relaxed, human breathing room**: keep natural `0.22–0.35s` clause pauses & `0.45–0.65s` thoughtful beats; cut only dead air (`>0.8s`), major stumbles, and distracting tics; keep natural laughs/emotion | `--isolate 88`, **`--lufs -16`** (Apple Podcasts / Bilibili long-form comfort standard, zero listener fatigue) | Subtle `"zoom": 1.06`, `"zoom_y": 0.35` on major chapter shifts only (avoid jumpy cuts) | Default **`.srt` sidecar + subtle chapter badges** (or highlight quotes only; avoid dense Douyin-style full-screen text unless requested) | **Podcast Editorial Look**: sharpest authentic speaker frame (or guest split) + warm mic/study bokeh lighting + clean magazine-style `EP` tag & core provocative question; never alter speaker's face |
| **3. Product Unboxing / Review (开箱 / 实物测评)** | Tight speech + preserve tactile unboxing reveals & case clicks; trim idle waiting / arms crossing lens | `--isolate 78` (tames room hum while preserving crisp tactile clicks), `--lufs -15` | `"zoom": 1.12`, `"zoom_y": 0.50` on key specs/verdicts | Full Retina PingFang SC highlighted burn-in + `.srt` + chapter badges | **Hardware Fidelity**: sharpest 70%-fill tight product crop(s) (+ static photo if given); Track A (`nano-pro` strict industrial-design preservation) / Track B (Apple Vision real product cutout + contact shadow composite) |

## Feature Matrix: Default ON vs Optional

### Default ON (Run Automatically on Every Raw Video)

| Feature | Implementation / Default | Notes |
| :--- | :--- | :--- |
| **1. Fast 2s media analysis** | `analyze.py` (`-skip_frame nokey`) | Probes specs/HDR/VFR, extracts 48k WAV + compact MP3(s), 10ms pause timeline, keyframe overview sheet |
| **2. Semantic jump-cuts + intentional pause preservation** | `inspect_regions.py` + `cutlist.json` | Multimodal audio + visual classification: cuts mid-clause stumbles, restarts, fillers (`嗯/啊/呃/哎`, sentence-initial `然后/就是/那个`), and dead air while **preserving intentional rhetorical/emotional pauses** (`0.45–0.70s` after punchlines, rhetorical questions, twists, or visual reveals) with 12ms cosine micro-fades |
| **3. Apple Neural Engine denoise + 2-pass broadcast voice** | `render.py` default ON (`--isolate 80 --lufs -15`) | Stage-1 macOS `AUSoundIsolation` (0ms latency-compensated, FCP-grade ML denoise & dereverb; use `75–85` for unboxing, `90–100` for noisy rooms) + Stage-2 6-band broadcast EQ + optical compressor + 2-pass linear `-15 LUFS / -1.5 dBTP` loudnorm (`--no-voice-enhance` to disable) |
| **4. Visual privacy scan & local Gaussian blur** | Inspect `contact_sheet.jpg` → `--blur-region "x,y,w,h"` | Automatically check for readable computer monitors, courier address labels, phone popups, or QR codes; if spotted, apply normalized `--blur-region` (e.g. `"0,0,1.0,0.22"`) cleanly in the same render pass |
| **5. Platform-safe SDR color + subtle grade** | `render.py` default ON (`--color sdr`, `--grade`) | Converts iPhone 10-bit HLG/PQ HDR to Apple-matched Rec.709 SDR so Douyin/Xiaohongshu/Bilibili never blow out, plus subtle +4% contrast / +5% saturation / crisp unsharp (use `--color keep` for native HDR, `--no-grade` to disable) |
| **6. Semantic punch-in zoom** | `"zoom": 1.12` on key topic-change segments | Applied on narrative shifts/emphasis points (never on a mechanical timer) to break fixed-camera fatigue |
| **7. Retina PingFang SC subtitles + chapter badges + `.srt`** | `--captions captions.json` (`.bin/render_subs`) | Two-pass solid white PingFang SC + `*keyword*` gold highlights + top-left chapter pill `"badge"`, UI safe-zone positioned, plus `.srt` sidecar |
| **8. High-CTR AI Covers via Google Flow MCP (3 ratios)** | `gflow_generate_image` (`nano2` + real video reference frames); fallback `.bin/make_covers` | **Primary default when `gflow-cli` MCP is authenticated**: extracts 1–2 real product reference frames (`publish_kit.py --extract-refs`) and generates studio-lit, high-CTR covers in exact platform ratios (`3:4` XiaoHongShu, `9:16` Douyin, `16:9` Bilibili/YouTube) while preserving real product likeness. Falls back automatically to instant local `.bin/make_covers` if offline |
| **9. High-Exposure Copywriting + SEO/CTR Linter + Compliance Kit** | [copywriting_playbook.md](./references/copywriting_playbook.md) + `publish_kit.py` → `发布文案与自查清单.md` | Extracts 3-tier SEO keywords (`core / long_tail / question`), drafts **3 distinct title angles per platform** (Pain/Contrast, Number/Value, Search-Intent) strictly complementary to the cover, writes tailored copy/Show Notes/Golden Quotes/pinned comments for **小红书、抖音、微信视频号、B站、YouTube**, and automatically lints truncation limits, cover-title overlap, SEO coverage, and Advertising Law / 引流 compliance |

### Optional (Enable When Requested)

| Feature | How to Enable |
| :--- | :--- |
| **Custom BGM with auto-ducking** | Pass `--bgm <track> --bgm-vol -22 --bgm-delay 0.0` (if the user wants new music and `ace-music` MCP is connected, generate a custom vocal-free instrumental track first!) |
| **Golden 3-Second Hook reordering** | Place the highlight segment first in `cutlist.json` (out-of-order segments supported natively with `-to` early stop) |
| **Subtle global speed-up** | `--speed 1.06` (default `1.0`; keeps pitch natural) |
| **Native 10-bit HDR export** | `--color keep` (for YouTube HDR / Apple devices) |
| **0-second Final Cut Pro timeline** | `--fcpxml <out.fcpxml>` or `--fcpxml-only <out.fcpxml>` via [export_fcpxml.py](./scripts/export_fcpxml.py) |

## Prerequisites

- `ffmpeg` and `ffprobe` on `PATH` (if missing on macOS: `NONINTERACTIVE=1 brew install ffmpeg`).
- Python 3 standard library only (`swiftc` compiles and caches native helpers once in `scripts/.bin/`: `voice_isolate`, `render_subs`, `make_covers`).

## Standard Automated Workflow

Let `$SKILL_DIR` be the directory containing this `SKILL.md`. Keep scratch files
inside `<artifact_dir>/scratch/edit_<basename>`. Create the delivery folder
`<input_dir>/<input_stem>_成品发布包/`.

### Step 1: Analyze Video (`~2–3s`)

```bash
python3 "$SKILL_DIR/scripts/analyze.py" \
  "<INPUT_VIDEO>" --work-dir "$WORK_DIR"
```

### Step 2: Listen, Privacy-Check & Plan

Call `read_file` in parallel on `$WORK_DIR/audio_full.mp3` (or parts),
`$WORK_DIR/contact_sheet.jpg`, and `$WORK_DIR/timeline.txt`.

1. **Privacy check**: Examine `contact_sheet.jpg` for readable monitors, address
   labels, chat windows, or QR codes. If present, record normalized
   `--blur-region "x,y,w,h"` boxes (e.g., `"0,0,1.0,0.22"` for top monitors).
2. **Speech cleanup & intentional pause preservation (never cut blindly by volume!)**:
   - **Cut (accidental dead air / stumbles)**: mid-clause hesitations, trailing word drags (`就是——`), fillers (`嗯/啊/呃/哎`, sentence-initial `然后`), false starts/restarts, heavy breaths, or pauses where the speaker glances away at notes/teleprompter.
   - **Preserve & sculpt (intentional pauses / beats)**: pauses occurring after a **complete sentence** — especially rhetorical questions, punchlines, plot twists, or emotional takeaways — where prosody ends decisively (rising question or firm drop, no filler) and/or visual frames show direct eye contact, expressive reaction (smile, brow raise, shrug), or meaningful physical action (unboxing clicks, product reveals). Keep `0.45–0.70s` of breathing room rather than crushing them to `0.15s` (only gently trim extreme `> 1.5s` gaps).
3. **Hero frame & structure**: Pick the cleanest hero timestamp (edited timeline)
   for covers, topic-shift segments for `"zoom": 1.12`, and logical chapters.

### Step 3: Pinpoint Tight Splices (`< 1s`)

```bash
python3 "$SKILL_DIR/scripts/inspect_regions.py" \
  "$WORK_DIR" "intro:10.0-18.5,stutter:75.8-78.6" --sheet "102-141"
```

Listen to sliced `.mp3` clips via `read_file` alongside the 50ms ASCII waveforms
to lock exact boundaries.

### Step 4: Write `cutlist.json` & Audit Audio Preview (`~4s`)

Write `$WORK_DIR/cutlist.json` (include `"zoom": 1.12` on 3–6 narrative shift
segments; sculpt pause lengths by intent rather than flat-cutting: `0.10–0.16s`
mid-sentence, `0.18–0.28s` clause, `0.30–0.42s` topic break, **`0.45–0.70s`
intentional rhetorical/dramatic pause**, `>= 0.25s` tail safety after final
syllable):

```bash
python3 "$SKILL_DIR/scripts/render.py" \
  "$WORK_DIR" "$WORK_DIR/cutlist.json" --preview
```

(`--voice-enhance`, `--isolate 80`, `--lufs -15` are ON by default.)
**Mandatory audit**: Call `read_file` on `$WORK_DIR/preview.mp3` to verify every
splice, vocal quality, and the final word before rendering video.

### Step 5: Write `captions.json` & Render Final Video

Using the exact edited timestamps printed by `--preview`, write
`$WORK_DIR/captions.json` (wrap core numbers/selling points in `*...*` for gold
highlight; add `"badge"` on chapter starts), then run one single hardware render:

```bash
python3 "$SKILL_DIR/scripts/render.py" \
  "$WORK_DIR" "$WORK_DIR/cutlist.json" \
  --render "$DELIVERY_DIR/<STEM>_精剪成片.mp4" \
  --captions "$WORK_DIR/captions.json" \
  [--blur-region "0,0,1.0,0.22"] [--bgm "<BGM_PATH>"]
```

### Step 6: Dual-Insurance High-CTR Covers (Subject-Fidelity Guaranteed) & Publishing Kit

Whether the hero subject is **the speaker's own face (talking-head / podcast)**
or **a real physical product (unboxing / review)**, never let AI hallucinate an
unrecognizable face or wrong hardware details. Run the **Dual-Insurance Subject
Fidelity** pipeline when `gflow-cli` MCP is authenticated:

#### 6.1 Extract Sharpest Tight Subject Crop(s) + Apple Vision Cutout (`~1s`)
Run `publish_kit.py --extract-refs` (samples 7 frames around each timestamp,
auto-selects the sharpest zero-blur frame, tight-crops the subject, and generates
transparent Apple Vision PNG cutouts via `.bin/product_tools`):

- **Talking-head / Video podcast**: pick a timestamp where the speaker's eyes are
  open, expression is engaged/natural, and hands aren't blocking the face; omit
  the crop box (uses automatic Vision subject crop) or crop tightly around head &
  shoulders (`--make-cutout` cleanly lifts the real person!).
- **Product unboxing / review**: pass tight crop box(es) around the product so it
  fills ~70% of the reference image (or use a static product photo if supplied).

```bash
python3 "$SKILL_DIR/scripts/publish_kit.py" \
  "<INPUT_VIDEO>" "" "$WORK_DIR/refs" \
  --work-dir "$WORK_DIR" \
  --extract-refs "12.5" \
  --make-cutout
```

#### 6.2 Generate High-CTR Covers (Insurance Track A + Track B)
Probe `gflow_auth_status(profile="default")` first, and ALWAYS call
`gflow_generate_image` **sequentially** (per-profile browser lease — never in parallel!):

- **Insurance Track A — High-Fidelity Studio Relighting (`model="nano-pro"`)**:
  - Pass the tight subject crop(s) (`ref_01_crop.jpg`, …) to
    `gflow_generate_image(model="nano-pro", ...)` (for returning solo hosts who
    saved a Flow character asset, you may also reference `@Name`). Explicitly
    instruct the model to **preserve exact facial identity / real hardware shape,
    logo placement, and proportions without distortion**.
  - **Mandatory Visual Fidelity Audit**: Call `read_file` side-by-side on the
    generated cover AND `ref_01_crop.jpg`. Verify zero garbled Chinese glyphs AND
    authentic facial likeness / hardware accuracy!
- **Insurance Track B — 100% Pixel-Authentic Real Cutout Composite (Zero AI Subject Distortion)**:
  - Use Track B directly whenever strict pixel-for-pixel face or hardware
    fidelity is required (or automatically whenever Track A shows drift!).
  - Call `gflow_generate_image(model="nano2", ...)` to generate **ONLY the
    cinematic backdrop/studio desk/podcast atmosphere and bold high-CTR Chinese
    typography**, leaving an **empty clean illuminated zone** for the real subject.
  - Composite the **100% real Apple Vision cutout** (real person OR real product)
    onto the AI cover with natural contact/drop shadow:
    ```bash
    "$SKILL_DIR/scripts/.bin/product_tools" composite \
      "<ai_empty_stage.jpg>" "$WORK_DIR/refs/cutout_01.png" \
      "$DELIVERY_DIR/封面_B站YouTube_16x9.jpg" \
      0.74 0.52 0.42 0.80
    ```
  - *(Typical placement presets: 16:9 Bilibili `cx=0.74 cy=0.52 maxW=0.42 maxH=0.78`;
    3:4 XiaoHongShu `cx=0.50 cy=0.56 maxW=0.68 maxH=0.52`;
    9:16 Douyin `cx=0.50 cy=0.55 maxW=0.75 maxH=0.44`.)*

#### 6.3 High-Exposure Copywriting, SEO/CTR Linter & Publishing Bundle
Read [copywriting_playbook.md](./references/copywriting_playbook.md) and write
`$WORK_DIR/publish_spec.json` directly from the edited video's actual content
(including `genre`, `seo_keywords` `{core, long_tail, question}`, `golden_quotes`,
`chapters`, and tailored blocks for `xiaohongshu`, `douyin`, `wechat`, `bilibili`,
`youtube` — each with **3 distinct title angles** that complement rather than
repeat `cover.headline`). Then run `publish_kit.py --skip-covers`:

```bash
python3 "$SKILL_DIR/scripts/publish_kit.py" \
  "$DELIVERY_DIR/<STEM>_精剪成片.mp4" \
  "$WORK_DIR/publish_spec.json" \
  "$DELIVERY_DIR" \
  --work-dir "$WORK_DIR" \
  --captions "$WORK_DIR/captions.json" \
  --skip-covers
```

Inspect any `compliance` or `ctr_seo_notes` printed by `publish_kit.py`
(truncation overflows, cover-title duplication, missing core SEO keywords, or
flagged Advertising Law / 引流 words), fix `publish_spec.json`, and re-run until
both compliance alerts and truncation warnings are `0`.

#### Offline Fallback (`0.5s`, Zero Credits)
If `gflow-cli` is unavailable/unauthenticated, omit `--skip-covers` so
`publish_kit.py` renders all 3 platform covers locally via `.bin/make_covers`.

Finally, call `read_file` in parallel on `$WORK_DIR/verify_ending.mp3`,
`$WORK_DIR/verify_sheet.jpg`, and the final cover JPGs to verify zero clipped
endings, crisp subtitles/privacy blur, accurate Chinese characters, and
authentic product appearance.

## Pitfalls to Avoid

- **Always use `.mp3` for `read_file` audio listening** (never raw `ffmpeg` `.m4a`).
- **Always audit `preview.mp3` before `--render`** so you never waste a 4K encode.
- **Check compliance alerts** printed by `publish_kit.py` and rewrite any flagged extreme/引流 words before delivering.
- **Single-pass VideoToolbox on Apple Silicon**: do not split into parallel VideoToolbox workers.
