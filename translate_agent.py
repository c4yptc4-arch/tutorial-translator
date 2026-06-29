#!/usr/bin/env python3
"""
Tutorial Video Translation Agent — Multilingual Edition
Any language tutorial → Any language dubbed + subtitled video

Usage:
  python translate_agent.py --url "https://youtube.com/watch?v=..." --lang mandarin
  python translate_agent.py --file my_tutorial.mp4 --lang japanese
  python translate_agent.py --list-langs

Requirements:
  pip install faster-whisper yt-dlp anthropic gtts
  ffmpeg must be installed
  Set env vars: ANTHROPIC_API_KEY
"""

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("agent")

OUTPUT_DIR = Path("output")
TMP_DIR    = OUTPUT_DIR / "tmp"
FINAL_DIR  = OUTPUT_DIR / "final"

LANG_CONFIG = {
    "mandarin":   {"label": "Mandarin Chinese (普通话)",     "flag": "🇨🇳", "gtts_lang": "zh-CN", "claude_lang": "Simplified Chinese Mandarin (普通话). Use clear, natural tutorial-style spoken Chinese.", "srt_suffix": "zh-cmn", "chars_per_sec": 4.5},
    "cantonese":  {"label": "Cantonese (廣東話)",            "flag": "🇭🇰", "gtts_lang": "zh-TW", "claude_lang": "Cantonese Chinese (廣東話). Use natural spoken Cantonese, NOT written Mandarin.", "srt_suffix": "zh-yue", "chars_per_sec": 4.5},
    "japanese":   {"label": "Japanese (日本語)",              "flag": "🇯🇵", "gtts_lang": "ja",    "claude_lang": "Japanese (日本語). Use polite tutorial-style speech (丁寧語).", "srt_suffix": "ja", "chars_per_sec": 7.0},
    "korean":     {"label": "Korean (한국어)",                "flag": "🇰🇷", "gtts_lang": "ko",    "claude_lang": "Korean (한국어). Use polite tutorial-style speech (존댓말).", "srt_suffix": "ko", "chars_per_sec": 6.0},
    "french":     {"label": "French (Français)",             "flag": "🇫🇷", "gtts_lang": "fr",    "claude_lang": "French (Français). Use clear tutorial-style speech.", "srt_suffix": "fr", "chars_per_sec": 14.0},
    "spanish":    {"label": "Spanish (Español)",             "flag": "🇪🇸", "gtts_lang": "es",    "claude_lang": "Spanish (Español). Use clear tutorial-style speech.", "srt_suffix": "es", "chars_per_sec": 14.0},
    "german":     {"label": "German (Deutsch)",              "flag": "🇩🇪", "gtts_lang": "de",    "claude_lang": "German (Deutsch). Use clear tutorial-style speech.", "srt_suffix": "de", "chars_per_sec": 13.0},
    "italian":    {"label": "Italian (Italiano)",            "flag": "🇮🇹", "gtts_lang": "it",    "claude_lang": "Italian (Italiano). Use clear tutorial-style speech.", "srt_suffix": "it", "chars_per_sec": 13.5},
    "portuguese": {"label": "Portuguese (Português)",        "flag": "🇧🇷", "gtts_lang": "pt",    "claude_lang": "Portuguese (Português, Brazilian). Use clear tutorial-style speech.", "srt_suffix": "pt", "chars_per_sec": 13.5},
    "dutch":      {"label": "Dutch (Nederlands)",            "flag": "🇳🇱", "gtts_lang": "nl",    "claude_lang": "Dutch (Nederlands). Use clear tutorial-style speech.", "srt_suffix": "nl", "chars_per_sec": 13.0},
    "malay":      {"label": "Malay (Bahasa Melayu)",         "flag": "🇲🇾", "gtts_lang": "ms",    "claude_lang": "Malay (Bahasa Melayu). Use clear tutorial-style speech.", "srt_suffix": "ms", "chars_per_sec": 12.0},
    "thai":       {"label": "Thai (ภาษาไทย)",                "flag": "🇹🇭", "gtts_lang": "th",    "claude_lang": "Thai (ภาษาไทย). Use clear tutorial-style speech.", "srt_suffix": "th", "chars_per_sec": 10.0},
    "indonesian": {"label": "Indonesian (Bahasa Indonesia)", "flag": "🇮🇩", "gtts_lang": "id",    "claude_lang": "Indonesian (Bahasa Indonesia). Use clear tutorial-style speech.", "srt_suffix": "id", "chars_per_sec": 12.0},
    "arabic":     {"label": "Arabic (العربية)",              "flag": "🇸🇦", "gtts_lang": "ar",    "claude_lang": "Modern Standard Arabic (العربية الفصحى). Use clear tutorial-style speech.", "srt_suffix": "ar", "chars_per_sec": 10.0},
    "hindi":      {"label": "Hindi (हिन्दी)",                "flag": "🇮🇳", "gtts_lang": "hi",    "claude_lang": "Hindi (हिन्दी). Use clear tutorial-style speech.", "srt_suffix": "hi", "chars_per_sec": 11.0},
    "english":    {"label": "English",                       "flag": "🇬🇧", "gtts_lang": "en",    "claude_lang": "English. Use clear tutorial-style speech.", "srt_suffix": "en", "chars_per_sec": 14.0},
}


def list_languages():
    print("\nSupported languages:\n")
    for key, cfg in LANG_CONFIG.items():
        print(f"  --lang {key:<14}  {cfg['flag']}  {cfg['label']}")
    print()


# ── Phase 1: Ingest ──────────────────────────────────────────────────────────

def download_video(url: str, out_dir: Path) -> tuple[Path, Path]:
    log.info("📥  Downloading: %s", url)
    video_path = out_dir / "source_video.mp4"
    audio_path = out_dir / "source_audio.wav"
    cmd = [
        "yt-dlp", "-f",
        "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", str(video_path), "--no-playlist", url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("yt-dlp failed:\n%s", result.stderr)
        sys.exit(1)
    log.info("✅  Downloaded: %s", video_path)
    extract_audio(video_path, audio_path)
    return video_path, audio_path


def use_local_file(file_path: str, out_dir: Path) -> tuple[Path, Path]:
    src = Path(file_path)
    if not src.exists():
        log.error("File not found: %s", file_path)
        sys.exit(1)
    video_path = out_dir / "source_video.mp4"
    audio_path = out_dir / "source_audio.wav"
    shutil.copy(src, video_path)
    extract_audio(video_path, audio_path)
    return video_path, audio_path


def extract_audio(video_path: Path, audio_path: Path):
    log.info("🎙️  Extracting audio...")
    subprocess.run([
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        str(audio_path),
    ], capture_output=True, check=True)
    log.info("✅  Audio extracted")


# ── Phase 2: Transcribe ──────────────────────────────────────────────────────

def transcribe(audio_path: Path, out_dir: Path) -> tuple[list[dict], str]:
    from faster_whisper import WhisperModel
    log.info("📝  Transcribing with faster-whisper (auto language detect)...")
    log.info("    First run downloads model (~1.5 GB) — subsequent runs are instant.")

    model = WhisperModel("large-v3", device="cpu", compute_type="int8")
    raw_segments, info = model.transcribe(
        str(audio_path), beam_size=5, vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )
    detected   = info.language
    confidence = info.language_probability * 100
    log.info("    Detected: %s (%.0f%% confidence)", detected, confidence)

    segments = [{"id": s.id, "start": s.start, "end": s.end, "text": s.text.strip()} for s in raw_segments]

    meta_path = out_dir / "transcript_source.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({"detected_language": detected, "confidence": confidence, "segments": segments}, f, ensure_ascii=False, indent=2)

    log.info("✅  Transcribed %d segments (source: %s)", len(segments), detected)
    return segments, detected


def save_srt(segments: list[dict], path: Path, text_key: str = "text"):
    lines = []
    for i, seg in enumerate(segments, 1):
        lines.append(f"{i}\n{fmt_time(seg['start'])} --> {fmt_time(seg['end'])}\n{seg.get(text_key, seg.get('text',''))}\n")
    path.write_text("\n".join(lines), encoding="utf-8")
    log.info("💾  SRT: %s", path)


def fmt_time(s: float) -> str:
    h, rem = divmod(int(s), 3600)
    m, sec = divmod(rem, 60)
    ms = int((s - int(s)) * 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


# ── Phase 3: Translate ───────────────────────────────────────────────────────

def translate_segments(segments: list[dict], lang_cfg: dict, out_dir: Path, source_lang: str = "unknown") -> list[dict]:
    import anthropic
    log.info("🌐  Translating %d segments → %s ...", len(segments), lang_cfg["label"])
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    cps    = lang_cfg["chars_per_sec"]

    system_prompt = f"""You are an expert translator specializing in tutorial video localization.
Source language: {source_lang}
Target language: {lang_cfg['claude_lang']}

Rules:
1. Preserve each segment ID exactly.
2. Fit translation within the TIME BUDGET shown in parentheses (seconds).
   - Target TTS speaks ~{cps} characters/words per second.
   - Shorten/simplify if tight — never drop key meaning.
3. Use natural spoken tutorial language, NOT formal written style.
4. Keep technical terms (UI labels, code, filenames, software names) in English.
5. Respond ONLY with valid JSON array: [{{"id": 0, "tr": "..."}}]
6. No markdown fences, no extra text."""

    translated = {}
    for batch_start in range(0, len(segments), 30):
        batch = segments[batch_start: batch_start + 30]
        batch_text = "\n".join(f"[{s['id']}] ({s['end']-s['start']:.1f}s) {s['text']}" for s in batch)
        log.info("  Batch %d–%d ...", batch_start, batch_start + len(batch) - 1)

        for attempt in range(3):
            try:
                msg = client.messages.create(
                    model="claude-sonnet-4-6", max_tokens=4096,
                    system=system_prompt,
                    messages=[{"role": "user", "content": batch_text}],
                )
                raw = re.sub(r"^```[a-z]*\n?", "", msg.content[0].text.strip())
                raw = re.sub(r"\n?```$", "", raw)
                for item in json.loads(raw):
                    translated[int(item["id"])] = item["tr"]
                break
            except Exception as e:
                log.warning("  Attempt %d failed: %s", attempt + 1, e)
                time.sleep(2)
        else:
            for s in batch:
                translated[s["id"]] = s["text"]

    result = [{**s, "tr": translated.get(s["id"], s["text"])} for s in segments]
    out_path = out_dir / "transcript_translated.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    log.info("✅  Translation saved")
    return result


# ── Phase 4: TTS (gTTS — works on Linux + Mac) ───────────────────────────────

def synthesize_voiceover(segments: list[dict], lang_cfg: dict, out_dir: Path) -> list[dict]:
    from gtts import gTTS
    gtts_lang = lang_cfg["gtts_lang"]
    log.info("🔊  Synthesizing TTS (gTTS, lang=%s) ...", gtts_lang)

    tts_dir = out_dir / "tts_segments"
    tts_dir.mkdir(exist_ok=True)

    result = []
    for seg in segments:
        tr_text       = seg["tr"]
        slot_duration = seg["end"] - seg["start"]
        seg_id        = seg["id"]

        mp3_path = tts_dir / f"seg_{seg_id:04d}_raw.mp3"
        raw_path = tts_dir / f"seg_{seg_id:04d}_raw.wav"
        fit_path = tts_dir / f"seg_{seg_id:04d}_fit.wav"

        # Generate TTS mp3
        tts = gTTS(text=tr_text, lang=gtts_lang, slow=False)
        tts.save(str(mp3_path))

        # Convert to WAV
        subprocess.run([
            "ffmpeg", "-y", "-i", str(mp3_path),
            "-ar", "24000", "-ac", "1", str(raw_path),
        ], capture_output=True, check=True)

        # Speed-fit to slot
        tts_dur = get_audio_duration(raw_path)
        if tts_dur > 0:
            ratio = tts_dur / slot_duration
            ratio = max(0.5, min(4.0, ratio))
            if ratio > 0.95:
                speed_fit_audio(raw_path, fit_path, ratio)
                log.info("  seg %d: tts=%.2fs slot=%.2fs → ×%.2f", seg_id, tts_dur, slot_duration, ratio)
            else:
                shutil.copy(raw_path, fit_path)
        else:
            shutil.copy(raw_path, fit_path)

        result.append({**seg, "tts_path": str(fit_path)})

    log.info("✅  TTS complete (%d segments)", len(result))
    return result


def get_audio_duration(path: Path) -> float:
    out = subprocess.run([
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "csv=p=0", str(path),
    ], capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def speed_fit_audio(src: Path, dst: Path, ratio: float):
    if ratio <= 2.0:
        atempo = f"atempo={ratio:.4f}"
    else:
        r1 = min(2.0, ratio ** 0.5)
        atempo = f"atempo={r1:.4f},atempo={ratio/r1:.4f}"
    subprocess.run(["ffmpeg", "-y", "-i", str(src), "-af", atempo, str(dst)], capture_output=True, check=True)


# ── Phase 5: Audio Mix ───────────────────────────────────────────────────────

def build_mixed_audio(segments: list[dict], video_path: Path, out_dir: Path) -> Path:
    log.info("🎚️  Mixing audio...")
    inputs = ["-i", str(video_path)]
    for seg in segments:
        inputs += ["-i", seg["tts_path"]]

    n = len(segments)
    filters = ["[0:a]volume=0.08[orig_duck]"]
    for i, seg in enumerate(segments):
        delay_ms = int(seg["start"] * 1000)
        filters.append(f"[{i+1}:a]adelay={delay_ms}|{delay_ms}[tts{i}]")
    tts_ins = "".join(f"[tts{i}]" for i in range(n))
    filters.append(f"[orig_duck]{tts_ins}amix=inputs={n+1}:duration=first:dropout_transition=0[mixed]")

    mixed_audio = out_dir / "mixed_audio.aac"
    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", ";".join(filters),
        "-map", "[mixed]", "-c:a", "aac", "-b:a", "192k", str(mixed_audio),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("Mix failed:\n%s", result.stderr[-2000:])
        sys.exit(1)
    log.info("✅  Mix complete")
    return mixed_audio


# ── Phase 6: Render ──────────────────────────────────────────────────────────

def burn_and_render(video_path: Path, mixed_audio: Path, srt_path: Path, final_path: Path):
    log.info("🖼️  Burning subtitles + rendering...")
    sub_filter = (
        f"subtitles={srt_path}:force_style='"
        "FontName=Arial,FontSize=22,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=1,Outline=2,"
        "Shadow=1,Alignment=2,MarginV=40'"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path), "-i", str(mixed_audio),
        "-map", "0:v", "-map", "1:a",
        "-vf", sub_filter,
        "-c:v", "libx264", "-crf", "20", "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(final_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("Render failed:\n%s", result.stderr[-2000:])
        sys.exit(1)
    log.info("✅  Rendered: %s", final_path)


def polish(path: Path, out_path: Path):
    log.info("✨  Polishing audio (EBU R128)...")
    cmd = [
        "ffmpeg", "-y", "-i", str(path),
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        shutil.copy(path, out_path)
    else:
        log.info("✅  Polished: %s", out_path)


# ── Main ─────────────────────────────────────────────────────────────────────

def check_env():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        log.error("Missing ANTHROPIC_API_KEY")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Tutorial Video Translation Agent")
    parser.add_argument("--list-langs", action="store_true")
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--url",  help="YouTube URL")
    src.add_argument("--file", help="Local video file path")
    parser.add_argument("--lang", default="mandarin", choices=list(LANG_CONFIG.keys()))
    parser.add_argument("--skip-download",   action="store_true")
    parser.add_argument("--skip-transcribe", action="store_true")
    parser.add_argument("--skip-translate",  action="store_true")
    parser.add_argument("--skip-tts",        action="store_true")
    args = parser.parse_args()

    if args.list_langs:
        list_languages(); sys.exit(0)
    if not args.url and not args.file:
        parser.error("Provide --url or --file")

    check_env()
    lang_cfg = LANG_CONFIG[args.lang]
    log.info("🎬  Tutorial Translation Agent → %s", lang_cfg["label"])

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    FINAL_DIR.mkdir(parents=True, exist_ok=True)

    # Phase 1
    video_path = TMP_DIR / "source_video.mp4"
    audio_path = TMP_DIR / "source_audio.wav"
    if args.skip_download and video_path.exists():
        log.info("⏭️  Skipping download")
        if not audio_path.exists(): extract_audio(video_path, audio_path)
    elif args.url:
        video_path, audio_path = download_video(args.url, TMP_DIR)
    else:
        video_path, audio_path = use_local_file(args.file, TMP_DIR)

    # Phase 2
    source_meta = TMP_DIR / "transcript_source.json"
    if args.skip_transcribe and source_meta.exists():
        log.info("⏭️  Skipping transcription")
        with open(source_meta, encoding="utf-8") as f:
            data = json.load(f)
        segments, detected_lang = data["segments"], data.get("detected_language", "unknown")
    else:
        segments, detected_lang = transcribe(audio_path, TMP_DIR)
    save_srt(segments, TMP_DIR / "subtitles_source.srt")

    # Phase 3
    translated_path = TMP_DIR / "transcript_translated.json"
    if args.skip_translate and translated_path.exists():
        log.info("⏭️  Skipping translation")
        with open(translated_path, encoding="utf-8") as f:
            segments = json.load(f)
    else:
        segments = translate_segments(segments, lang_cfg, TMP_DIR, source_lang=detected_lang)
    out_srt = TMP_DIR / f"subtitles_{lang_cfg['srt_suffix']}.srt"
    save_srt(segments, out_srt, text_key="tr")

    # Phase 4
    tts_dir  = TMP_DIR / "tts_segments"
    tts_meta = TMP_DIR / "transcript_tts.json"
    if args.skip_tts and tts_dir.exists() and tts_meta.exists():
        log.info("⏭️  Skipping TTS")
        with open(tts_meta, encoding="utf-8") as f:
            segments = json.load(f)
    else:
        segments = synthesize_voiceover(segments, lang_cfg, TMP_DIR)
        with open(tts_meta, "w", encoding="utf-8") as f:
            json.dump(segments, f, ensure_ascii=False, indent=2)

    # Phase 5
    mixed_audio = build_mixed_audio(segments, video_path, TMP_DIR)

    # Phase 6
    raw_final    = TMP_DIR / "final_raw.mp4"
    final_output = FINAL_DIR / f"translated_{lang_cfg['srt_suffix']}.mp4"
    burn_and_render(video_path, mixed_audio, out_srt, raw_final)
    polish(raw_final, final_output)

    size_mb = final_output.stat().st_size / 1_048_576
    log.info("")
    log.info("═" * 60)
    log.info("🎉  DONE!")
    log.info("   Output  : %s", final_output)
    log.info("   Size    : %.1f MB", size_mb)
    log.info("   Source  : %s", detected_lang)
    log.info("   Target  : %s", lang_cfg["label"])
    log.info("   Segments: %d", len(segments))
    log.info("═" * 60)


if __name__ == "__main__":
    main()
