"""
Generate Series — Orchestrator tạo toàn bộ series anime dài tập

Đọc series_bible.json → Tạo kịch bản cho từng tập → Render pipeline

Usage:
    # Tạo kịch bản toàn bộ 12 tập (chưa render video)
    python generate_series.py --bible series_bible.json --storyboard-only

    # Tạo kịch bản + render 1 tập cụ thể
    python generate_series.py --bible series_bible.json --episode 1

    # Render toàn bộ (tạo kịch bản + render video)
    python generate_series.py --bible series_bible.json --all

    # Resume render tập bị gián đoạn
    python generate_series.py --bible series_bible.json --episode 3 --render-only
"""

import asyncio
import argparse
import json
import os
import sys
import subprocess
import shutil
from pathlib import Path
from datetime import datetime

if sys.platform == "win32":
    for stream in [sys.stdout, sys.stderr]:
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

from loguru import logger

# Use uv to run python scripts (ensures correct virtualenv with all deps)
UV_CMD = shutil.which("uv")
if not UV_CMD:
    # Fallback: check common location
    _uv_local = Path.home() / ".local" / "bin" / "uv.exe"
    if _uv_local.exists():
        UV_CMD = str(_uv_local)
    else:
        UV_CMD = "uv"  # Hope it's on PATH

def _python_cmd() -> list[str]:
    """Return the command prefix to run python scripts via uv."""
    return [UV_CMD, "run", "python"]


def get_series_output_dir(bible: dict) -> Path:
    """Get output directory for the series."""
    channel = bible.get("channel", "anime_series")
    return Path("output") / f"series_{channel}"


def get_episode_dir(series_dir: Path, ep_num: int) -> Path:
    """Get output directory for a specific episode."""
    return series_dir / f"ep{ep_num:02d}"


def episode_has_script(ep_dir: Path) -> bool:
    """Check if episode already has a generated script."""
    return (ep_dir / "script.json").exists()


def episode_has_video(ep_dir: Path) -> bool:
    """Check if episode already has a final video."""
    return (ep_dir / "final.mp4").exists()


def run_storyboard(bible_path: str, episode: dict, ep_dir: Path, language: str):
    """Run generate_anime_storyboard.py for one episode."""
    ep_num = episode["ep"]
    topic = episode["topic"]
    n_scenes = episode.get("scenes", 60)
    ep_chars = episode.get("characters", [])

    cmd = _python_cmd() + [
        "generate_anime_storyboard.py",
        "--topic", topic,
        "--scenes", str(n_scenes),
        "--language", language,
        "--output", str(ep_dir),
        "--series-bible", bible_path,
    ]
    if ep_chars:
        cmd += ["--episode-chars"] + ep_chars

    logger.info(f"  Command: {' '.join(cmd[:8])}...")

    # Stream output to both console and log file
    log_path = ep_dir / "storyboard_audit.log"
    with open(log_path, "w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            cmd,
            cwd=str(Path(__file__).parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        for line in process.stdout:
            sys.stdout.write(line)
            log_file.write(line)

        process.wait()

    if process.returncode != 0:
        logger.warning(f"  ⚠️ Storyboard exited with code {process.returncode}")

    if episode_has_script(ep_dir):
        # Load and verify
        with open(ep_dir / "script.json", "r", encoding="utf-8") as f:
            script = json.load(f)
        n_narr = len(script.get("narrations", []))
        n_vprompts = len(script.get("video_prompts", []))
        logger.success(f"  ✅ Script: {n_narr} narrations, {n_vprompts} video prompts")
        return True
    else:
        logger.error(f"  ❌ No script.json generated! Check: {log_path}")
        return False


def run_pipeline(ep_dir: Path, voice_config: dict, template: str):
    """Run resume_pipeline.py for one episode.
    
    Args:
        ep_dir: Episode output directory
        voice_config: Dict with tts_mode, voice/ref_audio/ref_text, speed
        template: Video template path
    """
    tts_mode = voice_config.get("tts_mode", "local")
    speed = voice_config.get("speed", 1.0)

    cmd = _python_cmd() + [
        "resume_pipeline.py",
        "--task-dir", str(ep_dir),
        "--template", template,
        "--tts-speed", str(speed),
        "--tts-mode", tts_mode,
    ]

    if tts_mode == "omnivoice":
        ref_audio = voice_config.get("ref_audio", "")
        ref_text = voice_config.get("ref_text", "")
        if ref_audio:
            cmd += ["--ref-audio", ref_audio]
        if ref_text:
            cmd += ["--ref-text", ref_text]
    else:
        voice = voice_config.get("voice", "ja-JP-NanamiNeural")
        cmd += ["--voice", voice]

    logger.info(f"  Command: {' '.join(cmd[:6])}...")

    # Run with output streaming to both console and log file
    log_path = ep_dir / "pipeline.log"
    with open(log_path, "w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            cmd,
            cwd=str(Path(__file__).parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        for line in process.stdout:
            sys.stdout.write(line)
            log_file.write(line)

        process.wait()

    if episode_has_video(ep_dir):
        logger.success(f"  ✅ Video: {ep_dir / 'final.mp4'}")
        return True
    else:
        logger.error(f"  ❌ No final.mp4 generated!")
        return False


def print_series_status(bible: dict, series_dir: Path):
    """Print current status of all episodes."""
    logger.info("")
    logger.info("=" * 70)
    logger.info(f"📊 SERIES STATUS: {bible.get('series_title', '?')}")
    logger.info("=" * 70)

    total_eps = len(bible["episodes"])
    scripts_done = 0
    videos_done = 0

    for episode in bible["episodes"]:
        ep_num = episode["ep"]
        ep_dir = get_episode_dir(series_dir, ep_num)
        has_script = episode_has_script(ep_dir)
        has_video = episode_has_video(ep_dir)

        if has_script:
            scripts_done += 1
        if has_video:
            videos_done += 1

        status = ""
        if has_video:
            status = "✅ VIDEO"
        elif has_script:
            status = "📝 SCRIPT"
        else:
            status = "⬜ PENDING"

        topic_short = episode["topic"][:30]
        chars = ", ".join(episode.get("characters", [])[:2])
        logger.info(f"  EP{ep_num:02d} [{status}] {topic_short}... ({chars})")

    logger.info("")
    logger.info(f"  Scripts: {scripts_done}/{total_eps}")
    logger.info(f"  Videos:  {videos_done}/{total_eps}")
    logger.info("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Generate Anime Series")
    parser.add_argument("--bible", type=str, required=True,
                        help="Path to series_bible.json")
    parser.add_argument("--episode", type=int, default=None,
                        help="Generate specific episode number")
    parser.add_argument("--episodes", type=str, default=None,
                        help="Episode range, e.g. '1-3' or '1,3,5'")
    parser.add_argument("--all", action="store_true",
                        help="Generate all episodes")
    parser.add_argument("--storyboard-only", action="store_true",
                        help="Only generate storyboards (no video rendering)")
    parser.add_argument("--render-only", action="store_true",
                        help="Only render videos (scripts must exist)")
    parser.add_argument("--status", action="store_true",
                        help="Show series status and exit")
    parser.add_argument("--template", type=str, default="1920x1080/video_youtube.html",
                        help="Video template")

    args = parser.parse_args()

    # Load bible
    bible_path = Path(args.bible)
    if not bible_path.exists():
        logger.error(f"Series bible not found: {bible_path}")
        sys.exit(1)

    with open(bible_path, "r", encoding="utf-8") as f:
        bible = json.load(f)

    series_dir = get_series_output_dir(bible)
    series_dir.mkdir(parents=True, exist_ok=True)

    # Copy bible to series output
    shutil.copy2(bible_path, series_dir / "series_bible.json")

    language = bible.get("language", "Japanese")
    episodes = bible.get("episodes", [])
    voice_config = bible.get("voice", {"tts_mode": "local", "voice": "ja-JP-NanamiNeural", "speed": 1.0})
    
    # Template: bible > CLI arg > default
    if bible.get("template"):
        args.template = bible["template"]

    logger.info("")
    logger.info("🎬" * 35)
    logger.info(f"  SERIES: {bible.get('series_title', '?')}")
    logger.info(f"  Channel: {bible.get('channel', '?')}")
    logger.info(f"  Author: {bible.get('author', '?')}")
    logger.info(f"  Brand: {bible.get('brand', '?')}")
    logger.info(f"  Description: {bible.get('description', '?')}")
    logger.info(f"  Language: {language}")
    logger.info(f"  Episodes: {len(episodes)}")
    logger.info(f"  Characters: {len(bible.get('characters', []))}")
    logger.info(f"  Template: {args.template}")
    logger.info(f"  Voice: {voice_config.get('tts_mode', 'local')} | speed={voice_config.get('speed', 1.0)}")
    if voice_config.get('tts_mode') == 'omnivoice':
        logger.info(f"  Ref audio: {voice_config.get('ref_audio', '?')}")
        logger.info(f"  Ref text: {voice_config.get('ref_text', '?')}")
    logger.info(f"  Output: {series_dir}")
    logger.info("🎬" * 35)

    # Status only
    if args.status:
        print_series_status(bible, series_dir)
        return

    # Determine which episodes to process
    target_eps = []
    if args.episode:
        target_eps = [args.episode]
    elif args.episodes:
        if "-" in args.episodes:
            start, end = args.episodes.split("-")
            target_eps = list(range(int(start), int(end) + 1))
        else:
            target_eps = [int(x) for x in args.episodes.split(",")]
    elif args.all:
        target_eps = [ep["ep"] for ep in episodes]
    else:
        logger.info("No episodes specified. Use --episode, --episodes, --all, or --status")
        print_series_status(bible, series_dir)
        return

    # Filter to valid episodes
    valid_ep_nums = {ep["ep"] for ep in episodes}
    target_eps = [ep for ep in target_eps if ep in valid_ep_nums]

    if not target_eps:
        logger.error("No valid episodes to process!")
        sys.exit(1)

    logger.info(f"\n📋 Processing episodes: {target_eps}")

    # =================================================================
    # Step 0: Create character references (if not already done)
    # This generates ref images on FlowKit/Imagen 3 and saves media_ids
    # to config.yaml so every scene uses them for character consistency
    # =================================================================
    refs_path = series_dir / "character_refs.json"
    if refs_path.exists():
        with open(refs_path, "r", encoding="utf-8") as f:
            existing_refs = json.load(f)
        logger.info("")
        logger.info("=" * 70)
        logger.info("🎨 CHARACTER REFERENCES — Already exist, skipping generation")
        logger.info(f"   Refs: {refs_path}")
        for r in existing_refs:
            logger.info(f"   [{r['id']}] {r.get('name', '?')}: media_id={r['media_id'][:20]}...")
        logger.info("=" * 70)
    else:
        logger.info("")
        logger.info("=" * 70)
        logger.info("🎨 STEP 0: Creating character reference images on FlowKit")
        logger.info("   This is REQUIRED for character consistency across all episodes")
        logger.info("   Flow: Ref image → media_id → config.yaml → Imagen 3 uses as reference")
        logger.info("=" * 70)

        ref_cmd = _python_cmd() + [
            "create_character_refs.py",
            "--series-bible", str(bible_path),
            "--output-dir", str(series_dir),
        ]
        logger.info(f"  Command: {' '.join(ref_cmd)}")

        result = subprocess.run(
            ref_cmd,
            cwd=str(Path(__file__).parent),
            capture_output=False,
            text=True,
        )

        if refs_path.exists():
            logger.success("  ✅ Character references created!")
        else:
            logger.error("  ❌ Failed to create character references!")
            logger.error("  Check: Is FlowKit Chrome Extension running?")
            sys.exit(1)

    # Process each episode
    results = {"storyboard_ok": [], "storyboard_fail": [], "video_ok": [], "video_fail": []}

    for ep_num in target_eps:
        episode = next(ep for ep in episodes if ep["ep"] == ep_num)
        ep_dir = get_episode_dir(series_dir, ep_num)
        ep_dir.mkdir(parents=True, exist_ok=True)
        (ep_dir / "frames").mkdir(exist_ok=True)

        logger.info("")
        logger.info("=" * 70)
        logger.info(f"🎬 EPISODE {ep_num:02d}: {episode['topic']}")
        logger.info(f"   Characters: {episode.get('characters', [])}")
        logger.info(f"   Scenes: {episode.get('scenes', 60)}")
        logger.info(f"   Output: {ep_dir}")
        logger.info("=" * 70)

        # Step 1: Storyboard
        if not args.render_only:
            if episode_has_script(ep_dir):
                logger.info(f"  📝 Script already exists, skipping storyboard")
                results["storyboard_ok"].append(ep_num)
            else:
                logger.info(f"  📝 Generating storyboard...")
                ok = run_storyboard(str(bible_path), episode, ep_dir, language)
                if ok:
                    results["storyboard_ok"].append(ep_num)
                else:
                    results["storyboard_fail"].append(ep_num)
                    continue  # Skip render if storyboard failed

        # Step 2: Render video
        if not args.storyboard_only:
            if episode_has_video(ep_dir):
                logger.info(f"  🎥 Video already exists, skipping render")
                results["video_ok"].append(ep_num)
            elif not episode_has_script(ep_dir):
                logger.error(f"  ❌ No script.json — cannot render")
                results["video_fail"].append(ep_num)
            else:
                logger.info(f"  🎥 Rendering video...")
                ok = run_pipeline(ep_dir, voice_config, args.template)
                if ok:
                    results["video_ok"].append(ep_num)
                else:
                    results["video_fail"].append(ep_num)

    # Final summary
    logger.info("")
    logger.info("=" * 70)
    logger.success("🎬 SERIES GENERATION COMPLETE")
    logger.info("=" * 70)
    if results["storyboard_ok"]:
        logger.info(f"  📝 Scripts OK: EP {results['storyboard_ok']}")
    if results["storyboard_fail"]:
        logger.warning(f"  ❌ Scripts FAILED: EP {results['storyboard_fail']}")
    if results["video_ok"]:
        logger.info(f"  🎥 Videos OK: EP {results['video_ok']}")
    if results["video_fail"]:
        logger.warning(f"  ❌ Videos FAILED: EP {results['video_fail']}")

    print_series_status(bible, series_dir)


if __name__ == "__main__":
    main()
