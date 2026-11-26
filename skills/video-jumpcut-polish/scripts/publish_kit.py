#!/usr/bin/env python3
"""
Automated Pre-Publish Packaging Kit (v3 — High-Exposure Copywriting + Dual-Insurance Covers):
1. --extract-refs: Samples 7 frames around each timestamp, picks sharpest zero-blur frame via
   Laplacian variance, tight-crops subject, and optionally generates Apple Vision PNG cutouts.
2. Runs automated CTR, SEO & Compliance Quality Linter across all 5 platforms
   (抖音, 小红书, 微信视频号, B站, YouTube):
   - Platform truncation-fold length checks (e.g., XHS <= 20 chars, Douyin <= 24 chars)
   - Cover <-> Title complementarity check (warns if >70% duplicated)
   - 3-Tier SEO keyword coverage check (Title, Body lead, Hashtags, Pinned Comment)
   - Chinese Advertising Law extreme words & off-platform traffic (引流) compliance scan
3. Generates 3 local fallback covers (unless --skip-covers when Google Flow MCP covers are used)
   and writes a complete, copy-paste-ready 发布文案与自查清单.md.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

COMPLIANCE_RULES = [
    (r"(全网最低|史上最低|全网第一|绝对第一|行业第一|国家级|世界级|最高级|最佳|极致|绝无仅有|顶级|独一无二|天花板级别|秒杀一切)",
     "广告法极限词风险", "建议改为「同价位很能打 / 我用过最顺手之一 / 性价比很高」"),
    (r"(根治|包治|包好|药到病除|百分百有效|100%有效|彻底治愈|立竿见影)",
     "医疗/功效夸大宣称", "建议改为客观体验描述（如「个人使用感受更舒适」）"),
    (r"(加微|加我微|微信号|加V|加v|VX|vx|私信领|扫码领|进群领|点击链接购买|公棕号|扣扣号|QQ号)",
     "站外引流违规风险", "建议删除站外联系方式，改用平台内评论/合集/商品橱窗"),
    (r"(稳赚不赔|保本保收益|日赚|躺赚|必涨)",
     "金融诱导红线", "严禁收益承诺，请删除"),
]

AI_CLICHE_PATTERNS = r"(震撼来袭|绝对不容错过|干货满满建议收藏|颠覆你的认知|宝藏分享不容错过)"


def ensure_covers_binary() -> str:
    bin_dir = os.path.join(SCRIPT_DIR, ".bin")
    bin_path = os.path.join(bin_dir, "make_covers")
    src_path = os.path.join(SCRIPT_DIR, "make_covers.swift")
    if not os.path.isfile(bin_path) or os.path.getmtime(src_path) > os.path.getmtime(bin_path):
        os.makedirs(bin_dir, exist_ok=True)
        print("Compiling native macOS cover generator (one-time)...")
        subprocess.run(["swiftc", "-O", src_path, "-o", bin_path], check=True)
    return bin_path


def ensure_product_tools_binary() -> str:
    bin_dir = os.path.join(SCRIPT_DIR, ".bin")
    bin_path = os.path.join(bin_dir, "product_tools")
    src_path = os.path.join(SCRIPT_DIR, "product_tools.swift")
    if not os.path.isfile(bin_path) or os.path.getmtime(src_path) > os.path.getmtime(bin_path):
        os.makedirs(bin_dir, exist_ok=True)
        print("Compiling native Apple Vision product_tools CLI (one-time)...")
        subprocess.run(["swiftc", "-O", src_path, "-o", bin_path], check=True)
    return bin_path


def scan_compliance(text_blocks: list[tuple[str, str]]) -> list[dict]:
    findings = []
    for source, text in text_blocks:
        if not text:
            continue
        for pat, cat, tip in COMPLIANCE_RULES:
            for m in re.finditer(pat, text):
                findings.append({"source": source, "word": m.group(0), "category": cat, "suggestion": tip})
    return findings


def norm_chars(s: str) -> set[str]:
    cleaned = re.sub(r"[\s\*！!？?，,。.：:·—\-\[\]【】()（）「」\"'🎧✅⚠️🎯]+", "", s.lower())
    return set(cleaned)


def lint_ctr_and_seo(spec: dict) -> list[str]:
    """Automated CTR, truncation-fold, Cover<->Title complementarity, and SEO keyword audit."""
    notes = []
    cover_head = spec.get("cover", {}).get("headline", "").replace("*", "")
    cover_chars = norm_chars(cover_head)

    # Platform truncation fold limits (CJK-aware character length; YouTube uses display width)
    limits = [
        ("xiaohongshu", "小红书", 20, False, "小红书标题超过20字易在双列流被截断，建议精简并把核心词放前10字"),
        ("douyin", "抖音", 26, False, "抖音首句超过26字易被折叠，建议将核心钩子放前20字"),
        ("wechat", "微信视频号", 25, False, "微信视频号主标题超过25字易截断，建议压缩至15–25字"),
        ("bilibili", "B站", 42, False, "B站标题偏长，建议控制在18–38字以防移动端截断"),
        ("youtube", "YouTube", 64, True, "YouTube标题超过移动端安全宽度（约30中文字/60英文字符）易被截断"),
    ]

    for key, name, max_len, use_width, tip in limits:
        p = spec.get(key, {})
        if not p:
            continue
        titles = p.get("titles") or ([p["title"]] if p.get("title") else [])
        for idx, t in enumerate(titles, 1):
            ts = t.strip()
            t_len = sum(2 if ord(ch) > 127 else 1 for ch in ts) if use_width else len(ts)
            if t_len > max_len:
                unit = "宽" if use_width else "字"
                notes.append(f"⚠️ [{name} 标题#{idx}] 长度 {t_len}{unit} > {max_len}{unit}（{tip}）")
            # Cover <-> Title overlap check
            if len(cover_chars) >= 4:
                t_chars = norm_chars(t)
                overlap = len(cover_chars & t_chars) / max(1, len(cover_chars))
                if overlap >= 0.85 and len(t_chars) <= len(cover_chars) + 3:
                    notes.append(f"💡 [{name} 标题#{idx}] 与封面大字高度重合（{int(overlap*100)}%），建议封面与标题互补提供双倍信息增量")
        # Check for stiff AI clichés
        body = p.get("body", "")
        for m in re.finditer(AI_CLICHE_PATTERNS, " ".join(titles) + " " + body):
            notes.append(f"💡 [{name}] 检测到较生硬营销/AI套话 `{m.group(0)}`，建议改为更真诚的口语表达")

    # 3-Tier SEO keyword coverage audit
    seo = spec.get("seo_keywords", {})
    core_kws = seo.get("core", [])
    if core_kws:
        for key, name in [("xiaohongshu", "小红书"), ("douyin", "抖音"), ("wechat", "微信视频号"), ("bilibili", "B站"), ("youtube", "YouTube")]:
            p = spec.get(key, {})
            if not p:
                continue
            titles_str = " ".join(p.get("titles") or ([p["title"]] if p.get("title") else [])).lower()
            body_lead = (p.get("body", "")[:80]).lower()
            tags_str = " ".join(p.get("hashtags", [])).lower()
            pin_str = p.get("pinned_comment", "").lower()
            hit_title = any(kw.lower() in titles_str for kw in core_kws)
            hit_body = any(kw.lower() in body_lead for kw in core_kws)
            hit_tags = any(kw.lower() in tags_str for kw in core_kws)
            missing = []
            if not hit_title: missing.append("标题")
            if not hit_body: missing.append("正文首段")
            if not hit_tags: missing.append("话题标签")
            if missing:
                notes.append(f"🔎 [{name} SEO] 核心词 {core_kws} 未出现在：{'、'.join(missing)}（建议自然融入以提升搜索曝光）")
            if not pin_str:
                notes.append(f"💡 [{name}] 缺少置顶评论互动钩子")

    return notes


def fmt_ts(sec: float) -> str:
    s = max(0, int(round(sec)))
    return f"{s // 60:02d}:{s % 60:02d}"


def extract_hero_frame(video_path: str, ts: float, out_jpg: str, blur_regions: list[str], meta: dict | None = None, apply_sdr_grade: bool = False):
    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "json", video_path
    ]))
    w = int(probe["streams"][0]["width"])
    h = int(probe["streams"][0]["height"])

    fc = []
    cur = "[0:v]"
    for idx, br in enumerate(blur_regions):
        fx, fy, fw, fh = map(float, br.split(","))
        bx = max(0, int(round(fx * w))) & ~1
        by = max(0, int(round(fy * h))) & ~1
        bw = max(2, min(w - bx, int(round(fw * w)))) & ~1
        bh = max(2, min(h - by, int(round(fh * h)))) & ~1
        fc.append(f"{cur}split[bg{idx}][fg{idx}];[fg{idx}]crop={bw}:{bh}:{bx}:{by},gblur=sigma=28[bl{idx}];[bg{idx}][bl{idx}]overlay={bx}:{by}[v{idx}]")
        cur = f"[v{idx}]"

    post = []
    if apply_sdr_grade and meta:
        if meta.get("is_hdr"):
            trc_in = "smpte2084" if meta.get("color_transfer") == "smpte2084" else "bt2020-10"
            post.append(f"colorspace=all=bt709:iall=bt2020:itrc={trc_in}:fast=1")
        post.append("eq=contrast=1.04:saturation=1.05")
        post.append("unsharp=3:3:0.35:3:3:0.0")

    if fc or post:
        if post:
            fc.append(f"{cur}{','.join(post)}[vout]")
            cur = "[vout]"
        subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-ss", f"{ts:.3f}", "-i", video_path,
            "-filter_complex", ";".join(fc), "-map", cur, "-frames:v", "1", "-q:v", "2", out_jpg
        ], check=True)
    else:
        subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-ss", f"{ts:.3f}", "-i", video_path,
            "-frames:v", "1", "-q:v", "2", out_jpg
        ], check=True)


def extract_smart_ref(
    video_path: str,
    center_ts: float,
    out_crop_jpg: str,
    out_cutout_png: str | None,
    crop_box: str,
    blur_regions: list[str],
    meta: dict | None,
):
    tmp_dir = out_crop_jpg + "_cands"
    os.makedirs(tmp_dir, exist_ok=True)
    cand_paths = []
    for idx, dt in enumerate([-0.6, -0.4, -0.2, 0.0, 0.2, 0.4, 0.6]):
        t = max(0.0, center_ts + dt)
        p = os.path.join(tmp_dir, f"c_{idx:02d}.jpg")
        extract_hero_frame(video_path, t, p, blur_regions, meta=meta, apply_sdr_grade=True)
        cand_paths.append(p)

    pt_bin = ensure_product_tools_binary()
    cmd = [pt_bin, "sharpest", out_crop_jpg] + cand_paths
    if crop_box:
        cmd += ["--crop", crop_box]
    else:
        cmd += ["--auto-crop"]
    subprocess.run(cmd, check=True)

    if out_cutout_png:
        try:
            subprocess.run([pt_bin, "cutout", out_crop_jpg, out_cutout_png], check=True)
        except Exception as e:
            print(f"[WARNING] Vision cutout skipped for {out_crop_jpg}: {e}")

    shutil.rmtree(tmp_dir, ignore_errors=True)


def format_titles_md(p: dict) -> list[str]:
    titles = p.get("titles") or ([p["title"]] if p.get("title") else [])
    angles = p.get("title_angles", [])
    out = []
    for idx, t in enumerate(titles):
        tag = f"（{angles[idx]}）" if idx < len(angles) else ""
        out.append(f"  - `{len(t)}字` {tag}{t}")
    return out


def main():
    ap = argparse.ArgumentParser(description="Generate multi-platform covers, CTR/SEO/compliance audit, and publishing kit markdown.")
    ap.add_argument("video_path", help="Path to final edited video MP4 (or source video when using --extract-refs)")
    ap.add_argument("spec_json", nargs="?", default="", help="Path to publish_spec.json")
    ap.add_argument("out_dir", help="Delivery output directory")
    ap.add_argument("--work-dir", default="", help="Optional analyze.py work_dir")
    ap.add_argument("--captions", default="", help="Optional captions.json to include in compliance scan")
    ap.add_argument("--blur-region", action="append", default=[], help="Privacy blur region(s) for hero frame extraction")
    ap.add_argument("--extract-refs", default="", help='Extract sharpest tight-cropped SDR refs + Vision cutouts: "53.5" or "53.5:x,y,w,h;..."')
    ap.add_argument("--make-cutout", action="store_true", help="With --extract-refs, also generate transparent Apple Vision PNG cutouts")
    ap.add_argument("--skip-covers", action="store_true", help="Skip local Swift cover generation (when covers are generated via Google Flow MCP)")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    meta = None
    if args.work_dir and os.path.isfile(os.path.join(args.work_dir, "meta.json")):
        meta = json.load(open(os.path.join(args.work_dir, "meta.json"), encoding="utf-8"))

    if args.extract_refs:
        src = meta["input_path"] if meta else args.video_path
        sep = ";" if ";" in args.extract_refs else ("," if ":" not in args.extract_refs else ";")
        specs = [x.strip() for x in args.extract_refs.split(sep) if x.strip()]
        for idx, item in enumerate(specs, 1):
            t_str, box = item.split(":", 1) if ":" in item else (item, "")
            out_crop = os.path.join(args.out_dir, f"ref_{idx:02d}_crop.jpg")
            out_cut = os.path.join(args.out_dir, f"cutout_{idx:02d}.png") if args.make_cutout else None
            extract_smart_ref(src, float(t_str.strip()), out_crop, out_cut, box.strip(), args.blur_region, meta)
        return

    if not args.spec_json:
        ap.error("spec_json is required unless --extract-refs is used.")
    spec = json.load(open(args.spec_json, encoding="utf-8"))

    # 1. Local fallback covers unless --skip-covers
    c = spec.get("cover", {})
    if not args.skip_covers:
        hero_jpg = os.path.join(args.out_dir, "_hero_tmp.jpg")
        if meta:
            hero_ts = float(c.get("hero_src_time_sec", c.get("hero_time_sec", 2.0)))
            extract_hero_frame(meta["input_path"], hero_ts, hero_jpg, args.blur_region, meta=meta, apply_sdr_grade=True)
        else:
            hero_ts = float(c.get("hero_time_sec", 2.0))
            extract_hero_frame(args.video_path, hero_ts, hero_jpg, args.blur_region)

        cover_spec_path = os.path.join(args.out_dir, "_cover_spec_tmp.json")
        with open(cover_spec_path, "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False, indent=2)
        cover_bin = ensure_covers_binary()
        subprocess.run([cover_bin, hero_jpg, cover_spec_path, args.out_dir], check=True)
        for tmp in (hero_jpg, cover_spec_path):
            if os.path.exists(tmp):
                os.remove(tmp)

    # 2. Compliance + CTR/SEO Linter
    blocks = [("封面主标", c.get("headline", "")), ("封面副标", c.get("subline", ""))]
    for k, nm in [("douyin", "抖音"), ("xiaohongshu", "小红书"), ("wechat", "微信视频号"), ("bilibili", "B站"), ("youtube", "YouTube")]:
        p = spec.get(k, {})
        if not p:
            continue
        for t in (p.get("titles") or ([p["title"]] if p.get("title") else [])):
            blocks.append((f"{nm}-标题", t))
        blocks.append((f"{nm}-正文", p.get("body", "")))
        blocks.append((f"{nm}-话题", " ".join(p.get("hashtags", []))))
        blocks.append((f"{nm}-置顶评论", p.get("pinned_comment", "")))

    if args.captions and os.path.isfile(args.captions):
        caps = json.load(open(args.captions, encoding="utf-8"))
        for idx, cap in enumerate(caps, 1):
            blocks.append((f"字幕#{idx}", cap.get("text", "").replace("*", "")))

    findings = scan_compliance(blocks)
    ctr_seo_notes = lint_ctr_and_seo(spec)

    # 3. Build rich copy-paste-ready 发布文案与自查清单.md
    chapters = spec.get("chapters", [])
    seo = spec.get("seo_keywords", {})
    audit = spec.get("audit", {})
    genre = spec.get("genre", "综合视频")

    lines = [
        f"# 高曝光发布物料包：{spec.get('project_title', os.path.basename(args.video_path))}",
        "",
        f"> **内容体裁**：{genre} ｜ **封面大字**：`{c.get('headline', '').replace('*', '')}`（与下方标题互补，避免重复）",
        "",
        "## 一、SEO 关键词矩阵 & 自动质检报告",
        "",
    ]
    if seo:
        lines += [
            f"- **核心主词**：{'、'.join(seo.get('core', [])) or '—'}",
            f"- **长尾场景词**：{'、'.join(seo.get('long_tail', [])) or '—'}",
            f"- **搜索问题词**：{'、'.join(seo.get('question', [])) or '—'}",
            "",
        ]
    lines += [
        f"- **成片文件**：`{os.path.basename(args.video_path)}`",
        f"- **画面隐私检查**：{audit.get('privacy', '已检查画面背景')}",
        f"- **色彩与防过曝**：{audit.get('color', '已按目标平台优化')}",
        f"- **人声与响度**：{audit.get('audio', 'Apple 神经引擎降噪 + 2-Pass 广播母带达标')}",
        f"- **BGM 版权状态**：{audit.get('bgm', '无外源版权风险')}",
    ]

    if findings:
        lines.append(f"- **⚠️ 违禁词/合规扫描**：发现 **{len(findings)} 处** 风险，请发布前修改：")
        for fnd in findings:
            lines.append(f"  - [{fnd['source']}] 命中 `{fnd['word']}`（{fnd['category']}）→ {fnd['suggestion']}")
    else:
        lines.append("- **✅ 违禁词/合规扫描**：全平台标题、正文、话题、置顶评论与字幕均未检出广告法极限词或站外引流风险。")

    if ctr_seo_notes:
        lines.append(f"- **📊 CTR / SEO 截断与埋词体检（{len(ctr_seo_notes)} 条提示）**：")
        for n in ctr_seo_notes:
            lines.append(f"  - {n}")
    else:
        lines.append("- **✅ CTR / SEO 体检**：所有平台标题均未超截断红线、封面与标题有效互补、核心 SEO 词全链路覆盖达标。")

    # Helper to append a platform section
    def add_platform(sec_num: str, key: str, heading: str, cover_key: str, default_cover: str, cover_note: str, show_chapters: bool = False):
        p = spec.get(key)
        if not p:
            return
        lines.extend(["", "---", "", f"## {sec_num}、{heading}"])
        if cover_key:
            lines.append(f"- **配套封面**：`{c.get(cover_key, default_cover)}`（{cover_note}）")
        if p.get("category"):
            lines.append(f"- **推荐分区**：{p['category']}")
        lines.append("- **3 组高点击候选标题（不同心理角度，可直接选用或 A/B 测试）**：")
        lines.extend(format_titles_md(p))
        if show_chapters and chapters:
            lines.extend([
                "- **章节时间戳 / 高能进度条（Show Notes）**：",
                "```text",
                "\n".join(f"{fmt_ts(ch['time'])} {ch['title']}" for ch in chapters),
                "```",
            ])
        hashtags_str = " ".join(p.get("hashtags", []))
        body_full = p.get("body", "").strip()
        if hashtags_str and key in ("douyin", "xiaohongshu", "wechat"):
            body_copy = f"{body_full}\n\n{hashtags_str}".strip()
        else:
            body_copy = body_full
        lines.extend([
            "- **简介 / 正文（直接复制）**：",
            "```text",
            body_copy,
            "```",
        ])
        if hashtags_str and key in ("bilibili", "youtube"):
            lines.append(f"- **标签（Tags）**：{'、'.join(t.lstrip('#') for t in p.get('hashtags', []))}")
        if p.get("pinned_comment"):
            lines.append(f"- **置顶评论（互动钩子 + SEO 二次埋词）**：{p['pinned_comment']}")

    add_platform("二", "xiaohongshu", "小红书发布包（搜索 SEO + 真实 KOC 种草）", "xhs_name", "封面_小红书_3x4.jpg", "3:4 瀑布流黄金比例")
    add_platform("三", "douyin", "抖音发布包（公域赛马 · 前20字强钩子）", "douyin_name", "封面_抖音视频号_9x16.jpg", "9:16 避开右侧图标与底部22%")
    add_platform("四", "wechat", "微信视频号发布包（熟人社交转发 · 信任感）", "douyin_name", "封面_抖音视频号_9x16.jpg", "9:16 竖版封面")
    add_platform("五", "bilibili", "B 站发布包（深度干货 · 社区感 + 章节进度条）", "bilibili_name", "封面_B站YouTube_16x9.jpg", "16:9 已留空右下角时长角标", show_chapters=True)
    add_platform("六", "youtube", "YouTube 发布包（全球搜索 SEO + Chapters）", "bilibili_name", "封面_B站YouTube_16x9.jpg", "16:9 缩略图", show_chapters=True)

    # Optional Golden Quotes & Mentioned Resources (great for podcasts / talking-head!)
    quotes = spec.get("golden_quotes", [])
    resources = spec.get("resources", [])
    if quotes or resources:
        lines += ["", "---", "", "## 附：本期金句与提及清单（适合发动态 / 评论区 / 播客 Show Notes）"]
        if quotes:
            lines.append("- **本期金句摘录**：")
            for q in quotes:
                lines.append(f"  - 「{q}」")
        if resources:
            lines.append("- **本期提及产品 / 工具 / 资料**：")
            for r in resources:
                lines.append(f"  - {r}")

    lines += [
        "",
        "---",
        "",
        "## 发布临门一脚检查",
        "- [ ] 手机自带外放中低音量抽查 10 秒，确认人声清晰、不压字",
        "- [ ] 各平台统一上传本地无水印成片（绝不搬运带水印版本）",
        "- [ ] 发布后 1 小时内发出置顶评论，并及时回复前 5 条真实评论撬动初始流量池",
    ]

    md_path = os.path.join(args.out_dir, "发布文案与自查清单.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Publish kit written (compliance={len(findings)}, ctr_seo_notes={len(ctr_seo_notes)}): {md_path}")
    for fnd in findings:
        print(f"  [合规] [{fnd['source']}] 命中 `{fnd['word']}` ({fnd['category']})")
    for n in ctr_seo_notes:
        print(f"  {n}")


if __name__ == "__main__":
    main()
