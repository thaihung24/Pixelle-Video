"""
Generate Anime Storyboard — 3-stage pipeline

Stage 1: Generate Character & Scene Blueprint (anime_storyboard.py prompt)
Stage 2: Generate Narrations (topic_narration.py — Alibaba prompt)
Stage 3: Generate Video Prompts (video_generation.py — Alibaba prompt)

Outputs: blueprint.json + script.json (ready for resume_pipeline.py)

Usage:
    python generate_anime_storyboard.py --topic "朝の習慣" --scenes 60
    python generate_anime_storyboard.py --topic "朝の習慣" --scenes 60 --series-bible series_bible.json
    python generate_anime_storyboard.py --topic "test" --scenes 5 --skip-video-prompts
"""

import asyncio
import argparse
import json
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    for stream in [sys.stdout, sys.stderr]:
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

sys.path.append(str(Path(__file__).parent))

from loguru import logger


def build_series_context(bible: dict | None) -> str:
    """Create compact channel/project context from a series bible."""
    if not bible:
        return ""

    lines = []
    for key in ["series_title", "channel", "description", "brand", "language", "style"]:
        value = bible.get(key)
        if value:
            lines.append(f"{key}: {value}")

    locations = bible.get("recurring_locations") or []
    if locations:
        lines.append("recurring_locations: " + "; ".join(str(x) for x in locations[:6]))

    if not lines:
        return ""

    return "=== SERIES / CHANNEL CONTEXT ===\n" + "\n".join(lines)


async def punctuate_narrations(llm_service, narrations: list[str], language: str) -> list[str]:
    """Restore punctuation for subtitle-friendly narrations (no rewriting)."""
    if not narrations:
        return narrations

    # Quick heuristic: if most lines already contain sentence punctuation, keep as-is.
    has_punct = sum(1 for n in narrations if any(p in (n or "") for p in [".", "!", "?", "…", ",", ";", ":"]))
    if has_punct >= max(1, len(narrations) // 2):
        return narrations

    payload = json.dumps({"narrations": narrations}, ensure_ascii=False, indent=2)
    prompt = f"""# Role
You are a punctuation restorer for short-video narration text.

# Task
Add natural punctuation to each narration in {language}.

# Rules
1. Keep the original words and word order for each narration.
2. Do not summarize, rewrite, translate, or add new ideas.
3. Add only punctuation and capitalization if needed.
4. Make phrases subtitle-friendly: prefer commas and periods to break long runs.
5. Output strictly valid JSON only.

# Input
{payload}

# Output
Return exactly:
{{
  "narrations": ["...", "..."]
}}
"""

    try:
        resp = await llm_service(prompt)
        from pixelle_video.utils.content_generators import _parse_json
        data = _parse_json(resp)
        out = data.get("narrations")
        if isinstance(out, list) and len(out) == len(narrations):
            return [(" ".join((x or "").split())).strip() for x in out]
    except Exception as exc:
        logger.warning(f"Failed to punctuate narrations via LLM; keeping original: {exc}")

    return narrations


# ===========================================================================
# Stage 1: Generate Blueprint (characters + scene outline)
# ===========================================================================
async def stage1_blueprint(
    llm_service,
    topic: str,
    n_scenes: int,
    language: str,
    fixed_characters: list = None,
) -> dict:
    """Generate character definitions and scene outline."""
    from pixelle_video.prompts.anime_storyboard import build_anime_blueprint_prompt

    prompt = build_anime_blueprint_prompt(
        topic=topic,
        n_scenes=n_scenes,
        language=language,
        fixed_characters=fixed_characters,
    )

    logger.info(f"[Stage 1] Generating blueprint: {n_scenes} scenes, topic={topic[:30]}...")
    logger.debug(f"[Stage 1] Full prompt ({len(prompt)} chars):")
    logger.debug(prompt)

    response = await llm_service(prompt)

    # Parse JSON from response
    from pixelle_video.utils.content_generators import _parse_json
    try:
        blueprint = _parse_json(response)
    except Exception:
        blueprint = None

    if not blueprint:
        logger.error("[Stage 1] Failed to parse blueprint JSON from LLM response")
        logger.debug(f"Raw response: {response[:500]}")
        return None

    # If fixed_characters were provided, override LLM output
    if fixed_characters:
        blueprint["characters"] = fixed_characters
        logger.info(f"[Stage 1] Overrode LLM characters with {len(fixed_characters)} fixed characters from bible")

    # Filter out non-dict items in scenes (LLM sometimes adds "... (total N scenes)" strings)
    raw_scenes = blueprint.get("scenes", [])
    valid_scenes = [s for s in raw_scenes if isinstance(s, dict) and "scene_number" in s]
    blueprint["scenes"] = valid_scenes
    
    n_chars = len(blueprint.get("characters", []))
    n_scns = len(valid_scenes)
    logger.info(f"[Stage 1] Blueprint: {n_chars} characters, {n_scns}/{n_scenes} scenes")

    # If LLM truncated scenes, retry with stronger instruction
    if n_scns < n_scenes:
        logger.warning(f"[Stage 1] ⚠️ LLM only generated {n_scns}/{n_scenes} scenes — retrying...")
        
        retry_prompt = prompt + f"""

⚠️ CRITICAL: You MUST generate ALL {n_scenes} scenes (scene_number 1 to {n_scenes}).
Do NOT truncate or abbreviate with "..." — output every single scene object.
The JSON must contain exactly {n_scenes} scene objects in the "scenes" array.
"""
        response2 = await llm_service(retry_prompt)
        try:
            blueprint2 = _parse_json(response2)
            if blueprint2:
                valid_scenes2 = [s for s in blueprint2.get("scenes", []) if isinstance(s, dict) and "scene_number" in s]
                if len(valid_scenes2) > n_scns:
                    blueprint["scenes"] = valid_scenes2
                    if fixed_characters:
                        blueprint["characters"] = fixed_characters
                    n_scns = len(valid_scenes2)
                    logger.success(f"[Stage 1] Retry got {n_scns}/{n_scenes} scenes")
        except Exception:
            logger.warning("[Stage 1] Retry parse failed, using original")
    
    logger.success(f"[Stage 1] ✅ Done: {n_chars} characters, {n_scns} scenes")
    
    for c in blueprint.get("characters", []):
        logger.info(f"   [{c['id']}] {c.get('name', '?')} ({c.get('role', '?')})")

    return blueprint


# ===========================================================================
# Stage 2: Generate Narrations (using Alibaba's topic_narration.py)
# ===========================================================================
async def stage2_narrations(
    llm_service,
    topic: str,
    blueprint: dict,
    n_scenes: int,
    language: str,
) -> list:
    """Generate narrations using Alibaba's topic_narration prompts."""
    from pixelle_video.utils.content_generators import generate_narrations_from_topic

    logger.info(f"[Stage 2] Generating {n_scenes} narrations...")

    # Build context from blueprint
    char_context = ""
    for c in blueprint.get("characters", []):
        char_context += f"- {c.get('name', c['id'])}: {c.get('visual', '')[:60]}...\n"

    enhanced_topic = f"{topic}\n\nCharacters:\n{char_context}"

    narrations = await generate_narrations_from_topic(
        llm_service=llm_service,
        topic=enhanced_topic,
        n_scenes=n_scenes,
        target_duration_seconds=8.0,
    )

    if narrations:
        logger.success(f"[Stage 2] ✅ Done: {len(narrations)} narrations generated")
        logger.info(f"   Narration 1: {narrations[0][:80]}...")
        logger.info(f"   Narration {len(narrations)}: {narrations[-1][:80]}...")
    else:
        logger.error("[Stage 2] ❌ Failed to generate narrations")

    return narrations


# ===========================================================================
# Stage 3: Generate Video Prompts (using Alibaba's video_generation.py)
# ===========================================================================
async def stage3_video_prompts(
    llm_service,
    narrations: list,
    blueprint: dict,
    visual_style: str = "",
) -> list:
    """Generate video prompts using Alibaba's video_generation prompts."""
    from pixelle_video.utils.content_generators import generate_video_prompts
    from pixelle_video.prompts.anime_storyboard import inject_character_visuals_into_narrations

    logger.info(f"[Stage 3] Generating video prompts for {len(narrations)} scenes...")
    visual_inputs = inject_character_visuals_into_narrations(
        narrations=narrations,
        characters=blueprint.get("characters", []),
        scenes=blueprint.get("scenes", []),
        visual_style=visual_style,
    )

    video_prompts = await generate_video_prompts(
        llm_service=llm_service,
        narrations=visual_inputs,
    )

    if video_prompts:
        logger.success(f"[Stage 3] ✅ Done: {len(video_prompts)} video prompts generated")
        logger.info(f"   Video prompt 1: {video_prompts[0][:80]}...")
        logger.info(f"   ... and {len(video_prompts) - 2} more")
    else:
        logger.error("[Stage 3] ❌ Failed to generate video prompts")

    return video_prompts


# ===========================================================================
# Stage 4: Generate Image Prompts (using Alibaba's image_generation.py)
# ===========================================================================
async def stage4_image_prompts(
    llm_service,
    narrations: list,
    blueprint: dict,
    visual_style: str = "",
) -> list:
    """Generate image prompts using Alibaba's image_generation prompts for static seed images."""
    from pixelle_video.utils.content_generators import generate_image_prompts
    from pixelle_video.prompts.anime_storyboard import inject_character_visuals_into_narrations

    logger.info(f"[Stage 4] Generating image prompts for {len(narrations)} static seed scenes...")
    visual_inputs = inject_character_visuals_into_narrations(
        narrations=narrations,
        characters=blueprint.get("characters", []),
        scenes=blueprint.get("scenes", []),
        visual_style=visual_style,
    )

    image_prompts = await generate_image_prompts(
        llm_service=llm_service,
        narrations=visual_inputs,
    )

    if image_prompts:
        logger.success(f"[Stage 4] ✅ Done: {len(image_prompts)} image prompts generated")
        logger.info(f"   Image prompt 1: {image_prompts[0][:80]}...")
    else:
        logger.error("[Stage 4] ❌ Failed to generate image prompts")

    return image_prompts


# ===========================================================================
# Main
# ===========================================================================
async def main():
    parser = argparse.ArgumentParser(description="Generate Anime Storyboard")
    parser.add_argument("--topic", type=str, required=True, help="Topic/title")
    parser.add_argument("--scenes", type=int, default=60, help="Number of scenes")
    parser.add_argument("--language", type=str, default="Japanese", help="Language")
    parser.add_argument("--output", type=str, default=None, help="Output directory")
    parser.add_argument("--series-bible", type=str, default=None, help="Path to series_bible.json")
    parser.add_argument("--episode-chars", nargs="*", default=None, help="Character IDs for this episode")
    parser.add_argument("--skip-video-prompts", action="store_true", help="Skip Stage 3 and 4")

    args = parser.parse_args()

    # Output directory
    if args.output:
        output_dir = Path(args.output)
    else:
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path("output") / f"{timestamp}_anime"

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "frames").mkdir(exist_ok=True)

    # Setup audit log
    log_path = output_dir / "storyboard_audit.log"
    logger.add(str(log_path), level="DEBUG", encoding="utf-8")

    logger.info("Initializing Pixelle-Video Core...")

    from pixelle_video.service import PixelleVideoCore
    core = PixelleVideoCore()
    await core.initialize()

    llm_service = core.llm

    # Load series bible if provided
    fixed_characters = None
    bible = None
    if args.series_bible:
        bible_path = Path(args.series_bible)
        if bible_path.exists():
            with open(bible_path, "r", encoding="utf-8") as f:
                bible = json.load(f)
            all_chars = bible.get("characters", [])

            if args.episode_chars:
                # Filter to only episode-specific characters
                fixed_characters = [c for c in all_chars if c["id"] in args.episode_chars]
                logger.info(f"📖 Series Bible: {len(fixed_characters)} characters for this episode")
            else:
                fixed_characters = all_chars
                logger.info(f"📖 Series Bible: Using all {len(fixed_characters)} characters")
        else:
            logger.warning(f"Series bible not found: {bible_path}")

    series_context = build_series_context(bible)
    visual_style = bible.get("style", "") if bible else ""
    effective_topic = args.topic
    if series_context:
        effective_topic = f"{args.topic}\n\n{series_context}"

    # ===== Stage 1: Blueprint =====
    blueprint = await stage1_blueprint(
        llm_service=llm_service,
        topic=effective_topic,
        n_scenes=args.scenes,
        language=args.language,
        fixed_characters=fixed_characters,
    )

    if not blueprint:
        logger.error("Blueprint generation failed!")
        sys.exit(1)

    # Save blueprint
    blueprint_path = output_dir / "blueprint.json"
    with open(blueprint_path, "w", encoding="utf-8") as f:
        json.dump(blueprint, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved: {blueprint_path}")

    # ===== Stage 2: Narrations =====
    narrations = await stage2_narrations(
        llm_service=llm_service,
        topic=effective_topic,
        blueprint=blueprint,
        n_scenes=args.scenes,
        language=args.language,
    )

    if not narrations:
        logger.error("Narration generation failed!")
        sys.exit(1)

    # Optional: restore punctuation for subtitle friendliness (especially Vietnamese/Thai/etc.)
    narrations = await punctuate_narrations(llm_service, narrations, args.language)

    # ===== Stage 3 & 4: Video Prompts and Image Prompts =====
    video_prompts = []
    image_prompts = []
    if not args.skip_video_prompts:
        # Stage 3: Video
        video_prompts = await stage3_video_prompts(
            llm_service=llm_service,
            narrations=narrations,
            blueprint=blueprint,
            visual_style=visual_style,
        )
        if not video_prompts:
            logger.warning("Video prompt generation failed, continuing without them")
            video_prompts = ["" for _ in narrations]
            
        # Stage 4: Image
        image_prompts = await stage4_image_prompts(
            llm_service=llm_service,
            narrations=narrations,
            blueprint=blueprint,
            visual_style=visual_style,
        )
        if not image_prompts:
            logger.warning("Image prompt generation failed, continuing without them")
            image_prompts = ["" for _ in narrations]
    else:
        logger.info("[Stage 3/4] Skipped (--skip-video-prompts)")
        video_prompts = ["" for _ in narrations]
        image_prompts = ["" for _ in narrations]

    # ===== Save script.json (final output for resume_pipeline.py) =====
    script = {
        "title": blueprint.get("title", args.topic),
        "topic": args.topic,
        "language": args.language,
        "characters": blueprint.get("characters", []),
        "scenes": blueprint.get("scenes", []),
        "narrations": narrations,
        "video_prompts": video_prompts,
        "image_prompts": image_prompts,
    }

    script_path = output_dir / "script.json"
    with open(script_path, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    # ===== Summary =====
    logger.info("=" * 60)
    logger.success("Storyboard generated successfully!")
    logger.info(f"  Title: {script['title']}")
    logger.info(f"  Characters: {len(script['characters'])}")
    logger.info(f"  Narrations: {len(narrations)} (via Alibaba topic_narration.py)")
    logger.info(f"  Video prompts: {len(video_prompts)} (via Alibaba video_generation.py)")
    logger.info(f"  Output: {output_dir}")
    logger.info("=" * 60)

    logger.info("")
    logger.info("=== CHARACTER VISUALS (paste to FlowKit Dashboard) ===")
    for c in script["characters"]:
        logger.info(f"  [{c['id']}] {c.get('name', '?')}")
        logger.info(f"  Visual: {c.get('visual', 'N/A')}")
        logger.info("")

    logger.info("Next: run pipeline to render video:")
    logger.info(f"  python resume_pipeline.py \\")
    logger.info(f"    --task-dir {output_dir} \\")
    logger.info(f"    --template 1920x1080/video_youtube.html")
    logger.info(f"  (Or use generate_series.py which reads voice config from series_bible.json)")


if __name__ == "__main__":
    asyncio.run(main())
