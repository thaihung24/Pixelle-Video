import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from project_profiles import (
    episode_number,
    load_project_profile,
    load_series_bible,
    normalize_episode_id,
)


def _python_cmd() -> list[str]:
    uv = shutil.which("uv")
    if uv:
        return [uv, "run", "python"]
    return [sys.executable]


def _find_episode(bible: dict, episode_id: str) -> dict:
    ep_num = episode_number(episode_id)
    for episode in bible.get("episodes", []):
        if episode.get("ep") == ep_num:
            return episode
    raise ValueError(f"Episode {episode_id} not found in series bible")


def _run(cmd: list[str], dry_run: bool = False) -> int:
    print("Command:", " ".join(str(part) for part in cmd))
    if dry_run:
        return 0
    result = subprocess.run(cmd)
    return result.returncode


def _build_render_cmd(profile, output_dir: Path, template: str, voice: dict | None = None) -> list[str]:
    voice = voice or profile.voice
    render = profile.data.get("render", {})
    cmd = _python_cmd() + [
        "resume_pipeline.py",
        "--task-dir",
        str(output_dir),
        "--template",
        template,
        "--project-config",
        str(profile.path),
        "--tts-mode",
        voice.get("tts_mode", "local"),
        "--tts-speed",
        str(voice.get("speed", 1.0)),
    ]

    if voice.get("tts_mode") == "omnivoice":
        if voice.get("ref_audio"):
            cmd += ["--ref-audio", voice["ref_audio"]]
        if voice.get("ref_text"):
            cmd += ["--ref-text", voice["ref_text"]]
    else:
        cmd += ["--voice", voice.get("voice", "ja-JP-NanamiNeural")]

    if render.get("audio_layer") is False:
        cmd.append("--no-audio-layer")
    if "audio_bgm_volume" in render:
        cmd += ["--audio-bgm-volume", str(render["audio_bgm_volume"])]
    if "audio_sfx_volume" in render:
        cmd += ["--audio-sfx-volume", str(render["audio_sfx_volume"])]
    if render.get("bgm"):
        cmd += ["--bgm", render["bgm"]]
    if "bgm_volume" in render:
        cmd += ["--bgm-volume", str(render["bgm_volume"])]

    return cmd


def main():
    parser = argparse.ArgumentParser(description="Generate and render one episode from a project profile.")
    parser.add_argument("--episode", type=str, required=True, help="Episode id, e.g. ep03 or 3")
    parser.add_argument("--project", type=str, default="sukoyaka_life", help="Project id or path to project.json")
    parser.add_argument("--storyboard-only", action="store_true", help="Only generate script.json")
    parser.add_argument("--render-only", action="store_true", help="Only render an existing script.json")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them")
    parser.add_argument("--force-storyboard", action="store_true", help="Regenerate script.json even if it already exists")
    parser.add_argument("--template", type=str, default=None, help="Override project template")
    parser.add_argument("--render-metadata", action="store_true", help="Allow resume render step to call LLM for title/SEO metadata")
    args = parser.parse_args()

    profile = load_project_profile(args.project)
    bible = load_series_bible(profile)
    episode_id = normalize_episode_id(args.episode)
    episode = _find_episode(bible, episode_id)

    topic = episode.get("topic") or episode.get("topic_vi") or ""
    if not topic:
        print(f"ERROR: Episode {episode_id} has no topic")
        sys.exit(1)

    output_dir = profile.episode_dir(episode_id)
    script_file = output_dir / "script.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "frames").mkdir(exist_ok=True)

    template = args.template or bible.get("template") or profile.template
    language = profile.language or bible.get("language", "Japanese")
    scenes = int(episode.get("scenes", 60))
    episode_chars = episode.get("characters", [])

    print("=" * 70)
    print(f"Project: {profile.project_id}")
    print(f"Episode: {episode_id}")
    print(f"Topic: {topic}")
    print(f"Scenes: {scenes}")
    print(f"Output: {output_dir}")
    print("=" * 70)

    if not args.render_only:
        if script_file.exists() and not args.force_storyboard:
            print(f"[1/2] Script exists, skipping storyboard: {script_file}")
        else:
            print("[1/2] Generating storyboard/script...")
            cmd = _python_cmd() + [
                "generate_anime_storyboard.py",
                "--topic",
                topic,
                "--scenes",
                str(scenes),
                "--language",
                language,
                "--output",
                str(output_dir),
                "--series-bible",
                str(profile.bible_path),
            ]
            if episode_chars:
                cmd += ["--episode-chars"] + list(episode_chars)

            code = _run(cmd, dry_run=args.dry_run)
            if code != 0:
                print("ERROR: Storyboard generation failed")
                sys.exit(code)

    if args.storyboard_only:
        print("Done: storyboard-only mode")
        return

    if not script_file.exists() and not args.dry_run:
        print(f"ERROR: Missing script.json: {script_file}")
        sys.exit(1)

    # Store project metadata in script.json so resume_pipeline can reuse it.
    if script_file.exists() and not args.dry_run:
        with open(script_file, "r", encoding="utf-8") as f:
            script_data = json.load(f)
        script_data.setdefault("project", {})
        script_data["project"].update(
            {
                "id": profile.project_id,
                "channel": profile.channel,
                "profile_path": str(profile.path),
                "template_params": profile.template_params,
            }
        )
        script_data.setdefault("topic", topic)
        script_data.setdefault("language", language)
        script_data.setdefault("channel", bible.get("channel", profile.channel))
        script_data.setdefault("author", bible.get("author", profile.template_params.get("author", "")))
        script_data.setdefault("brand", bible.get("brand", profile.template_params.get("brand", "")))
        script_data.setdefault("youtube_title", script_data.get("title") or topic)
        with open(script_file, "w", encoding="utf-8") as f:
            json.dump(script_data, f, ensure_ascii=False, indent=2)

    print("[2/2] Rendering/resuming pipeline...")
    voice_config = {**bible.get("voice", {}), **profile.voice}
    render_cmd = _build_render_cmd(profile, output_dir, template, voice=voice_config)
    if args.render_only and not args.render_metadata:
        render_cmd += ["--skip-title-generation", "--skip-seo-generation", "--skip-thumbnail-generation"]
    code = _run(render_cmd, dry_run=args.dry_run)
    if code != 0:
        print("ERROR: Render pipeline failed")
        sys.exit(code)

    print("=" * 70)
    print("Done")
    print(f"Expected final file: {output_dir / 'final_audio.mp4'}")
    print("=" * 70)


if __name__ == "__main__":
    main()
