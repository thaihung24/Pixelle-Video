"""
Resume Pipeline - Ti岷縫 t峄 ch岷 d峄?谩n b峄?gi谩n 膽o岷

Script n脿y 膽峄峜 l岷 script.json t峄?d峄?谩n c农, ki峄僲 tra nh峄痭g c岷h n脿o 膽茫 ho脿n th脿nh
(c贸 膽峄?audio + video + composed + segment), v脿 ch峄?ch岷 l岷 c谩c c岷h ch瓢a ho脿n th脿nh.

C谩ch d霉ng:
    python resume_pipeline.py --task-dir output/20260510_022626_d0be

T霉y ch峄峮:
    --task-dir       膼瓢峄漬g d岷玭 t峄沬 th瓢 m峄 d峄?谩n (b岷痶 bu峄檆)
    --style          Phong c谩ch h矛nh 岷h (vd: 'Studio Ghibli style')
    --voice          Gi峄峮g TTS (m岷穋 膽峄媙h: ja-JP-NanamiNeural)
    --tts-mode       Ch岷?膽峄?TTS: local, omnivoice, comfyui (m岷穋 膽峄媙h: local)
    --ref-audio      膼瓢峄漬g d岷玭 file audio m岷玼 cho voice cloning (OmniVoice)
    --ref-text       膼o岷 text t瓢啤ng 峄﹏g v峄沬 file audio m岷玼 (OmniVoice)
    --bgm            膼瓢峄漬g d岷玭 nh岷 n峄乶
    --bgm-volume     脗m l瓢峄g nh岷 n峄乶 (m岷穋 膽峄媙h: 0.2)
    --template       Template frame (m岷穋 膽峄媙h: 膽峄峜 t峄?config.yaml)
    --skip-concat    Ch峄?ch岷 c谩c c岷h thi岷縰, KH脭NG gh茅p video cu峄慽
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

# Th锚m 膽瓢峄漬g d岷玭 project v脿o sys.path
sys.path.append(str(Path(__file__).parent))

from loguru import logger


def scan_completed_frames(frames_dir: str, total_scenes: int) -> dict:
    """
    Qu茅t th瓢 m峄 frames 膽峄?x谩c 膽峄媙h tr岷g th谩i ho脿n th脿nh c峄 t峄玭g c岷h.
    
    Returns:
        dict v峄沬 key l脿 frame_index (0-based), value l脿 dict tr岷g th谩i
    """
    status = {}
    for i in range(total_scenes):
        frame_num = i + 1  # 1-based filename
        prefix = f"{frame_num:02d}"

        # Audio: check both .wav (OmniVoice) and .mp3 (Edge TTS)
        audio_path_wav = os.path.join(frames_dir, f"{prefix}_audio.wav")
        audio_path_mp3 = os.path.join(frames_dir, f"{prefix}_audio.mp3")
        if os.path.exists(audio_path_wav) and os.path.getsize(audio_path_wav) > 0:
            audio_path = audio_path_wav
            has_audio = True
        elif os.path.exists(audio_path_mp3) and os.path.getsize(audio_path_mp3) > 0:
            audio_path = audio_path_mp3
            has_audio = True
        else:
            audio_path = audio_path_mp3  # default fallback path for new generation
            has_audio = False

        video_path = os.path.join(frames_dir, f"{prefix}_video.mp4")
        composed_path = os.path.join(frames_dir, f"{prefix}_composed.png")
        segment_path = os.path.join(frames_dir, f"{prefix}_segment.mp4")
        image_path = os.path.join(frames_dir, f"{prefix}_image.png")

        has_video = os.path.exists(video_path) and os.path.getsize(video_path) > 0
        has_composed = os.path.exists(composed_path) and os.path.getsize(composed_path) > 0
        has_segment = os.path.exists(segment_path) and os.path.getsize(segment_path) > 0
        has_image = os.path.exists(image_path) and os.path.getsize(image_path) > 0

        is_complete = has_audio and has_composed and has_segment and (has_video or has_image)

        status[i] = {
            "frame_num": frame_num,
            "audio": has_audio,
            "video": has_video,
            "image": has_image,
            "composed": has_composed,
            "segment": has_segment,
            "complete": is_complete,
            "audio_path": audio_path if has_audio else None,
            "video_path": video_path if has_video else None,
            "image_path": image_path if has_image else None,
            "composed_path": composed_path if has_composed else None,
            "segment_path": segment_path if has_segment else None,
        }
    
    return status


def _load_project_runtime_config(project_config_path: str | None, script_data: dict) -> dict:
    """Load optional project profile data without making it mandatory."""
    profile_path = project_config_path or script_data.get("project", {}).get("profile_path")
    if not profile_path:
        return {}

    try:
        from project_profiles import load_project_profile

        profile = load_project_profile(profile_path)
        logger.info(f"Loaded project profile: {profile.project_id} ({profile.path})")
        return profile.data | {
            "_profile_path": str(profile.path),
            "_template_params": profile.template_params,
            "_channel": profile.channel,
        }
    except Exception as exc:
        logger.warning(f"Could not load project profile '{profile_path}': {exc}")
        return {}


def _build_template_params(script_data: dict, project_config: dict, youtube_title: str) -> dict:
    project_params = project_config.get("_template_params") or project_config.get("template_params") or {}
    script_project_params = script_data.get("project", {}).get("template_params", {})

    params = {
        "title": youtube_title,
        "author": script_data.get("author") or project_config.get("author") or project_params.get("author") or "@Pixelle.AI",
        "describe": script_data.get("description") or project_config.get("description") or project_params.get("describe") or "",
        "brand": script_data.get("brand") or project_config.get("brand") or project_params.get("brand") or "",
    }
    params.update(project_params)
    params.update(script_project_params)
    params["title"] = youtube_title
    return params


def _thumbnail_prompt_text(item) -> str:
    """Support both legacy string prompts and new structured thumbnail objects."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        image_prompt = item.get("image_prompt", "")
        text = item.get("thumbnail_text") or {}
        if isinstance(text, dict):
            line1 = text.get("line1", "")
            line2 = text.get("line2", "")
            overlay = " ".join(x for x in [line1, line2] if x).strip()
            if overlay:
                return f"{image_prompt}. Leave clean space for external text overlay: {overlay}"
        return image_prompt or json.dumps(item, ensure_ascii=False)
    return str(item)


async def main():
    parser = argparse.ArgumentParser(description="Resume Pixelle-Video Pipeline t峄?d峄?谩n b峄?gi谩n 膽o岷")
    parser.add_argument("--task-dir", type=str, required=True,
                        help="膼瓢峄漬g d岷玭 t峄沬 th瓢 m峄 d峄?谩n (vd: output/20260510_022626_d0be)")
    parser.add_argument("--style", type=str, default="",
                        help="Phong c谩ch h矛nh 岷h (vd: 'Studio Ghibli style')")
    parser.add_argument("--voice", type=str, default="ja-JP-NanamiNeural",
                        help="Gi峄峮g TTS (m岷穋 膽峄媙h: ja-JP-NanamiNeural)")
    parser.add_argument("--tts-mode", type=str, default="local",
                        choices=["local", "omnivoice", "comfyui"],
                        help="Ch岷?膽峄?TTS: local (Edge TTS), omnivoice (clone gi峄峮g), comfyui (m岷穋 膽峄媙h: local)")
    parser.add_argument("--ref-audio", type=str, default=None,
                        help="膼瓢峄漬g d岷玭 file audio m岷玼 cho voice cloning (d霉ng v峄沬 --tts-mode omnivoice)")
    parser.add_argument("--ref-text", type=str, default=None,
                        help="膼o岷 text t瓢啤ng 峄﹏g v峄沬 file audio m岷玼 (d霉ng v峄沬 --tts-mode omnivoice)")
    parser.add_argument("--bgm", type=str, default=None,
                        help="膼瓢峄漬g d岷玭 nh岷 n峄乶 (optional, override audio-layer)")
    parser.add_argument("--bgm-volume", type=float, default=0.2,
                        help="脗m l瓢峄g nh岷 n峄乶 (m岷穋 膽峄媙h: 0.2)")
    parser.add_argument("--template", type=str, default=None,
                        help="Template frame (m岷穋 膽峄媙h: 膽峄峜 t峄?config.yaml)")
    parser.add_argument("--project-config", type=str, default=None,
                        help="Path to project.json for channel metadata and defaults")
    parser.add_argument("--skip-title-generation", action="store_true",
                        help="Do not call LLM to generate a YouTube title; use script title/topic instead")
    parser.add_argument("--skip-seo-generation", action="store_true",
                        help="Do not call LLM to generate YouTube SEO metadata")
    parser.add_argument("--skip-thumbnail-generation", action="store_true",
                        help="Do not generate thumbnails after rendering")
    parser.add_argument("--skip-concat", action="store_true",
                        help="Ch峄?ch岷 c谩c c岷h thi岷縰, KH脭NG gh茅p video cu峄慽")
    parser.add_argument("--tts-speed", type=float, default=1.0,
                        help="T峄慶 膽峄?gi峄峮g 膽峄峜 TTS (m岷穋 膽峄媙h: 1.0)")
    parser.add_argument("--audio-layer", action="store_true", default=True,
                        help="T峄?膽峄檔g th锚m BGM + SFX t峄?audio manifest (m岷穋 膽峄媙h: b岷璽)")
    parser.add_argument("--no-audio-layer", dest="audio_layer", action="store_false",
                        help="T岷痶 auto audio layering")
    parser.add_argument("--audio-manifest", type=str, default=None,
                        help="膼瓢峄漬g d岷玭 audio_manifest.json (m岷穋 膽峄媙h: assets/audio/audio_manifest.json)")
    parser.add_argument("--audio-bgm-volume", type=float, default=0.15,
                        help="脗m l瓢峄g BGM trong mix (m岷穋 膽峄媙h: 0.15)")
    parser.add_argument("--audio-sfx-volume", type=float, default=0.08,
                        help="脗m l瓢峄g SFX ambient trong mix (m岷穋 膽峄媙h: 0.08)")
    
    args = parser.parse_args()
    
    # === 1. X谩c 膽峄媙h 膽瓢峄漬g d岷玭 d峄?谩n ===
    # Validate OmniVoice params
    if args.tts_mode == "omnivoice":
        if not args.ref_audio:
            logger.error("鉂?Ch岷?膽峄?omnivoice y锚u c岷 --ref-audio (file audio m岷玼)")
            sys.exit(1)
        if not os.path.exists(args.ref_audio):
            logger.error(f"鉂?File ref-audio kh么ng t峄搉 t岷: {args.ref_audio}")
            sys.exit(1)
        logger.info(f"馃帳 Voice Cloning mode: ref_audio={args.ref_audio}")
        if args.ref_text:
            logger.info(f"   ref_text: {args.ref_text[:60]}...")
    
    task_dir = Path(args.task_dir)
    if not task_dir.is_absolute():
        task_dir = Path(__file__).parent / task_dir
    
    task_dir = task_dir.resolve()
    
    if not task_dir.exists():
        logger.error(f"鉂?Th瓢 m峄 d峄?谩n kh么ng t峄搉 t岷: {task_dir}")
        sys.exit(1)
    
    script_json_path = task_dir / "script.json"
    if not script_json_path.exists():
        logger.error(f"鉂?Kh么ng t矛m th岷 script.json trong: {task_dir}")
        sys.exit(1)
    
    frames_dir = task_dir / "frames"
    frames_dir.mkdir(exist_ok=True)
    
    # Task ID = relative path from output dir (handles nested dirs like series_sukoyaka_life/ep01)
    output_root = Path(__file__).parent / "output"
    try:
        task_id = str(task_dir.relative_to(output_root.resolve()))
    except ValueError:
        # Fallback: just use dir name if task_dir is not under output/
        task_id = task_dir.name
    
    # === 2. 膼峄峜 k峄媍h b岷 ===
    with open(script_json_path, "r", encoding="utf-8") as f:
        script_data = json.load(f)

    project_config = _load_project_runtime_config(args.project_config, script_data)
    
    narrations = script_data.get("narrations", [])
    topic = script_data.get("topic", "Untitled")
    total_scenes = len(narrations)
    
    if total_scenes == 0:
        logger.error("鉂?K峄媍h b岷 r峄梟g (0 narrations)")
        sys.exit(1)
    
    logger.info(f"馃摉 膼峄峜 k峄媍h b岷: '{topic}' 鈥?{total_scenes} c岷h")
    
    # === 3. Qu茅t tr岷g th谩i ho脿n th脿nh ===
    frame_status = scan_completed_frames(str(frames_dir), total_scenes)
    
    completed = [i for i, s in frame_status.items() if s["complete"]]
    incomplete = [i for i, s in frame_status.items() if not s["complete"]]
    
    logger.info(f"鉁?膼茫 ho脿n th脿nh: {len(completed)}/{total_scenes} c岷h")
    if completed:
        completed_nums = [frame_status[i]["frame_num"] for i in completed]
        logger.info(f"   C岷h 膽茫 xong: {completed_nums}")
    
    if not incomplete:
        logger.success(f"馃帀 T岷 c岷?{total_scenes} c岷h 膽峄乽 膽茫 ho脿n th脿nh!")
        if not args.skip_concat:
            logger.info("鈴?Ti岷縩 h脿nh gh茅p video cu峄慽 c霉ng...")
        else:
            logger.info("鉁?Kh么ng c岷 l脿m g矛 th锚m.")
            return
    else:
        incomplete_nums = [frame_status[i]["frame_num"] for i in incomplete]
        logger.warning(f"鈿狅笍  C岷 ch岷 l岷: {len(incomplete)} c岷h: {incomplete_nums}")
    
    # === 4. Kh峄焛 t岷 Pixelle-Video Core ===
    logger.info("馃敡 Kh峄焛 t岷 Pixelle-Video Core...")
    from pixelle_video.service import PixelleVideoCore
    core = PixelleVideoCore()
    await core.initialize()
    
    # === 5. 膼峄峜 c岷 h矛nh ===
    from pixelle_video.config import config_manager
    config_yaml = config_manager.config
    
    frame_template = (
        args.template
        or script_data.get("template")
        or project_config.get("template")
        or config_yaml.template.default_template
    )
    
    # X谩c 膽峄媙h workflow
    from pixelle_video.utils.template_util import get_template_type
    template_name = Path(frame_template).name
    template_type = get_template_type(template_name)
    
    if template_type == "video":
        media_workflow = "flowkit/google-veo"
    elif template_type == "image":
        media_workflow = "flowkit/google-imagen-3"
    else:
        media_workflow = None
    
    logger.info(f"馃帹 Template: {frame_template} (type: {template_type})")
    logger.info(f"馃帴 Media workflow: {media_workflow}")
    
    # === 5b. Generate YouTube title (if not already saved) ===
    youtube_title = script_data.get("youtube_title", "")
    if not youtube_title:
        if args.skip_title_generation:
            youtube_title = script_data.get("title") or topic
            script_data["youtube_title"] = youtube_title
            with open(script_json_path, "w", encoding="utf-8") as f:
                json.dump(script_data, f, ensure_ascii=False, indent=2)
            logger.info(f"📵 Skipped LLM title generation; using: {youtube_title}")
        else:
            try:
                from pixelle_video.prompts.title_generation import build_title_generation_prompt
                # Build content summary from topic + first few narrations
                content_for_title = f"{topic}\n\n" + "\n".join(narrations[:5])
                title_prompt = build_title_generation_prompt(content_for_title, max_length=40)
                
                llm = core.llm
                youtube_title = await llm(title_prompt)
                youtube_title = youtube_title.strip().strip('"').strip("'")
                
                # Save to script.json for reuse
                script_data["youtube_title"] = youtube_title
                with open(script_json_path, "w", encoding="utf-8") as f:
                    json.dump(script_data, f, ensure_ascii=False, indent=2)
                
                logger.success(f"馃摵 YouTube title generated: {youtube_title}")
            except Exception as e:
                logger.warning(f"鈿狅笍 Failed to generate YouTube title: {e}")
                youtube_title = script_data.get("title", topic)
    else:
        logger.info(f"馃摵 YouTube title (cached): {youtube_title}")
    
    # === 6. T岷 c岷 h矛nh Storyboard ===
    from pixelle_video.models.storyboard import (
        Storyboard, StoryboardFrame, StoryboardConfig
    )
    from pixelle_video.services.frame_html import HTMLFrameGenerator
    from pixelle_video.utils.template_util import resolve_template_path
    
    template_path = resolve_template_path(frame_template)
    generator = HTMLFrameGenerator(template_path)
    media_width, media_height = generator.get_media_size()
    
    template_params = _build_template_params(script_data, project_config, youtube_title)

    storyboard_config = StoryboardConfig(
        task_id=task_id,
        n_storyboard=total_scenes,
        min_narration_words=5,
        max_narration_words=20,
        min_image_prompt_words=30,
        max_image_prompt_words=60,
        video_fps=30,
        tts_inference_mode=args.tts_mode,
        voice_id=args.voice,
        tts_speed=args.tts_speed,
        ref_audio=args.ref_audio,
        ref_text=args.ref_text,
        media_width=media_width,
        media_height=media_height,
        media_workflow=media_workflow,
        frame_template=frame_template,
        template_params=template_params
    )
    
    logger.info(f"馃攳 StoryboardConfig check:")
    logger.info(f"   tts_inference_mode={storyboard_config.tts_inference_mode!r}")
    logger.info(f"   ref_audio={storyboard_config.ref_audio!r}")
    logger.info(f"   ref_text={storyboard_config.ref_text!r}")
    logger.info(f"   voice_id={storyboard_config.voice_id!r}")
    logger.info(f"   tts_speed={storyboard_config.tts_speed!r}")
    
    # === 7. T岷 image prompts cho c谩c c岷h ch瓢a ho脿n th脿nh ===
    # Ch峄?t岷 prompts n岷縰 template c岷 media
    image_prompts = [None] * total_scenes  # Actually stores video_prompts
    seed_image_prompts = [None] * total_scenes  # Stores static image_prompts for seed
    
    # Check if script.json contains pre-generated video_prompts (from generate_anime_storyboard.py)
    pre_generated_prompts = script_data.get("video_prompts", [])
    pre_generated_seed_prompts = script_data.get("image_prompts", [])
    
    if pre_generated_prompts and len(pre_generated_prompts) == total_scenes:
        logger.info(f"馃搵 Found {len(pre_generated_prompts)} pre-generated video prompts in script.json (anime storyboard mode)")
        if pre_generated_seed_prompts and len(pre_generated_seed_prompts) == total_scenes:
            logger.info(f"馃搵 Found {len(pre_generated_seed_prompts)} pre-generated image prompts for seed images!")
        
        scenes = script_data.get("scenes", [])
        project_style_prefix = project_config.get("style_prompt_prefix", "")
        project_audio_style = (project_config.get("style_prompt_audio") or "").strip()
        if not project_style_prefix:
            from pixelle_video.prompts.style_registry import build_scene_style, get_debug_layers

        # Use pre-generated prompts with scene-specific style layers
        # Character visuals are NOT in text prompt (already passed via ref image media_ids)
        for i in range(total_scenes):
            if not (frame_status[i].get("video_path") or frame_status[i].get("image_path")):
                base_prompt = pre_generated_prompts[i]
                
                # Get scene metadata
                scene = scenes[i] if i < len(scenes) else {}
                act = scene.get("act", 1)
                setting_text = scene.get("setting", "")
                scene_brief = scene.get("scene_brief", "")
                
                if project_style_prefix:
                    style_block = project_style_prefix
                else:
                    # Build dynamic scene style (lighting + mood + camera + palette)
                    style_block = build_scene_style(
                        act=act,
                        setting=setting_text,
                        scene_brief=scene_brief,
                    )
                    
                    # Log detected layers for debugging
                    layers = get_debug_layers(act, setting_text, scene_brief)
                    logger.debug(
                        f"  Scene {i+1} (act={act}): "
                        f"lighting={layers['lighting']}, mood={layers['mood']}, "
                        f"camera={layers['camera']}, palette={layers['palette']}"
                    )
                
                # Inject setting context into the actual scene description
                setting_ctx = f"Setting: {setting_text}. " if setting_text else ""
                
                # Final prompt: Style Layers + Setting Context + Base Prompt + optional audio behavior
                audio_ctx = f" {project_audio_style}" if template_type == "video" and project_audio_style else ""
                image_prompts[i] = f"{style_block} {setting_ctx}{base_prompt}{audio_ctx}"
                
                # Seed image prompt (same structure, but uses image_prompts base if available)
                if pre_generated_seed_prompts and i < len(pre_generated_seed_prompts):
                    seed_base = pre_generated_seed_prompts[i]
                    seed_image_prompts[i] = f"{style_block} {setting_ctx}{seed_base}"
                else:
                    seed_image_prompts[i] = f"{style_block} {setting_ctx}{base_prompt}"
                
        assigned = sum(1 for p in image_prompts if p is not None)
        logger.info(f"   Assigned {assigned} prompts (scene-specific style layers + setting + base prompt)")
    else:
        # Fallback: generate prompts via LLM (original behavior)
        needs_prompt = [i for i in incomplete if not (frame_status[i]["video_path"] or frame_status[i]["image_path"])]
        
        if template_type in ["image", "video"] and needs_prompt:
            logger.info(f"馃柤锔? T岷 image prompts cho {len(needs_prompt)} c岷h ch瓢a c贸 media...")
            
            from pixelle_video.utils.content_generators import generate_image_prompts
            from pixelle_video.utils.prompt_helper import build_image_prompt
            
            # Ch峄?g峄璱 narrations c峄 c谩c c岷h ch瓢a xong 膽峄?ti岷縯 ki峄噈 API calls
            incomplete_narrations = [narrations[i] for i in needs_prompt]
            
            llm = core.llm
            base_prompts = await generate_image_prompts(
                llm,
                narrations=incomplete_narrations,
                min_words=30,
                max_words=60,
            )
            
            # 脕p d峄g style prefix
            image_config = core.config.get("comfyui", {}).get("image", {})
            prompt_prefix = args.style if args.style else image_config.get("prompt_prefix", "")
            project_audio_style = (project_config.get("style_prompt_audio") or "").strip()
            
            for idx, base_prompt in enumerate(base_prompts):
                frame_idx = needs_prompt[idx]
                final_prompt = build_image_prompt(base_prompt, prompt_prefix)
                seed_image_prompts[frame_idx] = final_prompt
                if template_type == "video" and project_audio_style:
                    final_prompt = f"{final_prompt} {project_audio_style}"
                image_prompts[frame_idx] = final_prompt
    
    # === 8. Build per-scene character_media_ids mapping ===
    from datetime import datetime
    
    # Load character_refs.json for char_id 鈫?media_id mapping
    char_id_to_media_id = {}
    char_refs_path = task_dir.parent / "character_refs.json"
    if char_refs_path.exists():
        with open(char_refs_path, "r", encoding="utf-8") as f:
            char_refs = json.load(f)
        for cr in char_refs:
            char_id_to_media_id[cr["id"]] = cr["media_id"]
        logger.info(f"馃搸 Loaded {len(char_id_to_media_id)} character ref mappings from {char_refs_path.name}")
    else:
        # Fallback: Qu茅t th瓢 m峄 characters/ + 膽峄峜 UUID t峄?.media_id_cache.json
        char_dir = Path("characters")
        char_cache_path = char_dir / ".media_id_cache.json"
        char_uuid_cache = {}
        if char_cache_path.exists():
            try:
                with open(char_cache_path, "r", encoding="utf-8") as f:
                    char_uuid_cache = json.load(f)
            except Exception:
                pass

        if char_dir.exists():
            for c_id in ["grandpa_kenji", "grandma_hanako", "ryu_grandson", "sakura_sensei"]:
                for ext in [".png", ".jpg"]:
                    p = char_dir / f"{c_id}{ext}"
                    if p.exists():
                        # 漂u ti锚n UUID t峄?cache (Google Flow media_id)
                        cache_key = f"{c_id}{ext}"
                        if cache_key in char_uuid_cache:
                            char_id_to_media_id[c_id] = char_uuid_cache[cache_key]
                            logger.debug(f"   {c_id} 鈫?UUID: {char_uuid_cache[cache_key][:12]}...")
                        else:
                            # Fallback: d霉ng file path (s岷?trigger upload trong flowkit_media)
                            char_id_to_media_id[c_id] = str(p).replace("\\", "/")
                            logger.debug(f"   {c_id} 鈫?file path (no UUID cache)")
                        break
            logger.info(f"馃搸 Auto-discovered {len(char_id_to_media_id)} character refs from characters/ folder")
    
    # Build per-scene character_media_ids from scenes data
    scenes_data = script_data.get("scenes", [])
    per_scene_char_media_ids = [None] * total_scenes
    for i in range(total_scenes):
        if i < len(scenes_data):
            # 1. Map Characters
            scene_chars = scenes_data[i].get("characters", [])
            scene_media_ids = [char_id_to_media_id[cid] for cid in scene_chars if cid in char_id_to_media_id]
            if scene_media_ids:
                per_scene_char_media_ids[i] = scene_media_ids
                
            # 2. Map Locations (exact match from location_id, auto-generate if missing)
            location_id = scenes_data[i].get("location_id")
            setting_str = scenes_data[i].get("setting", "")
            
            if location_id:
                loc_found = False
                loc_dir = Path("locations")
                loc_dir.mkdir(exist_ok=True)
                
                for ext in [".png", ".jpg", ".jpeg"]:
                    p = loc_dir / f"{location_id}{ext}"
                    if p.exists():
                        if per_scene_char_media_ids[i] is None:
                            per_scene_char_media_ids[i] = []
                        per_scene_char_media_ids[i].append(str(p).replace("\\", "/"))
                        loc_found = True
                        break
                
                # Auto-generate location image if not found
                if not loc_found and setting_str:
                    logger.info(f"馃實 V峄?tr铆 m峄沬 '{location_id}' ch瓢a c贸 岷h. T峄?膽峄檔g g峄峣 API v岷?岷h...")
                    try:
                        from pixelle_video.services.flowkit_media import FlowKitMediaService
                        media_svc = FlowKitMediaService(core.config)
                        
                        final_path = loc_dir / f"{location_id}.png"
                        
                        # V么 hi峄噓 h贸a vi峄嘽 t峄?膽峄檔g ch猫n nh芒n v岷璽 v脿o b峄慽 c岷h (v矛 膽芒y l脿 岷h phong c岷h tr峄憂g)
                        media_svc.default_character_media_ids = []
                        
                        # S峄?d峄g village.png l脿m 岷h tham chi岷縰 (Style Reference) 膽峄?茅p style gi峄憂g h峄噒
                        style_refs = []
                        village_path = loc_dir / "village.png"
                        if village_path.exists():
                            style_refs.append(str(village_path).replace("\\", "/"))
                            
                        project_location_prefix = project_config.get("location_prompt_prefix", "")
                        project_style_prefix = project_config.get("style_prompt_prefix", "")
                        if project_location_prefix or project_style_prefix:
                            loc_scene_style = project_location_prefix or project_style_prefix
                            loc_prompt = (
                                f"{loc_scene_style}. Empty reusable background or clean infographic scene, "
                                f"NO CHARACTERS, no readable text, no logos, no ticker symbols. "
                                f"Match the project visual identity and vertical short-video composition. "
                                f"Setting: {setting_str}"
                            )
                        else:
                            from pixelle_video.prompts.style_registry import build_scene_style
                            loc_scene_style = build_scene_style(
                                act=scenes_data[i].get("act", 1),
                                setting=setting_str,
                                scene_brief=scenes_data[i].get("scene_brief", ""),
                            )
                            loc_prompt = (
                                f"{loc_scene_style} Empty landscape background, highly detailed scenery, NO CHARACTERS. "
                                f"Traditional Japanese countryside village style, matching the exact art style, color grading, "
                                f"and line art of the reference image. Setting: {setting_str}"
                            )
                        
                        result = await media_svc(
                            prompt=loc_prompt, 
                            width=1920, 
                            height=1080,
                            output_path=str(final_path),
                            character_media_ids=style_refs if style_refs else None
                        )
                        
                        if result and result.url and os.path.exists(result.url):
                            logger.success(f"鉁?膼茫 t峄?膽峄檔g v岷?v脿 l瓢u b峄慽 c岷h: {final_path}")
                            
                            if per_scene_char_media_ids[i] is None:
                                per_scene_char_media_ids[i] = []
                            per_scene_char_media_ids[i].append(str(final_path).replace("\\", "/"))
                    except Exception as e:
                        logger.error(f"鉂?L峄梚 khi t峄?膽峄檔g v岷?location '{location_id}': {e}")
    
    assigned_refs = sum(1 for x in per_scene_char_media_ids if x)
    logger.info(f"   {assigned_refs}/{total_scenes} scenes have per-scene character/location refs")
    
    storyboard = Storyboard(
        title=topic,
        config=storyboard_config,
        created_at=datetime.now()
    )
    
    for i in range(total_scenes):
        status = frame_status[i]
        
        frame = StoryboardFrame(
            index=i,
            narration=narrations[i],
            image_prompt=image_prompts[i],
            seed_image_prompt=seed_image_prompts[i],
            character_media_ids=per_scene_char_media_ids[i],
            created_at=datetime.now()
        )
        
        # B峄?qua image_prompt n岷縰 膽茫 c贸 media s岷祅 膽峄?tr谩nh generate l岷
        if status["video_path"] or status["image_path"]:
            frame.image_prompt = None
            frame.seed_image_prompt = None
        
        # G谩n l岷 膽瓢峄漬g d岷玭 膽茫 c贸 s岷祅 (k峄?c岷?c岷h ch瓢a complete)
        if status["audio_path"]:
            frame.audio_path = status["audio_path"]
            # 膼峄峜 duration t峄?audio file
            try:
                import ffmpeg
                probe = ffmpeg.probe(status["audio_path"])
                frame.duration = float(probe['format']['duration'])
            except Exception:
                frame.duration = 5.0  # Fallback
                
        if status["video_path"]:
            frame.video_path = status["video_path"]
            frame.media_type = "video"
        elif status["image_path"]:
            frame.image_path = status["image_path"]
            frame.media_type = "image"
            
        if status["composed_path"]:
            frame.composed_image_path = status["composed_path"]
            
        if status["segment_path"]:
            frame.video_segment_path = status["segment_path"]
        
        storyboard.frames.append(frame)
    
    # === 9. X峄?l媒 c谩c c岷h ch瓢a ho脿n th脿nh ===
    if incomplete:
        logger.info(f"馃殌 B岷痶 膽岷 x峄?l媒 {len(incomplete)} c岷h ch瓢a ho脿n th脿nh...")
        
        for count, frame_idx in enumerate(incomplete, 1):
            frame = storyboard.frames[frame_idx]
            frame_num = frame_idx + 1
            
            logger.info(f"")
            logger.info(f"{'='*50}")
            logger.info(f"馃幀 C岷h {frame_num}/{total_scenes} (ti岷縩 膽峄?resume: {count}/{len(incomplete)})")
            logger.info(f"{'='*50}")
            logger.info(f"馃摑 N峄檌 dung: {frame.narration[:60]}...")
            
            try:
                processed_frame = await core.frame_processor(
                    frame=frame,
                    storyboard=storyboard,
                    config=storyboard_config,
                    total_frames=total_scenes,
                )
                
                storyboard.frames[frame_idx] = processed_frame
                storyboard.total_duration += processed_frame.duration
                
                logger.success(f"鉁?C岷h {frame_num} ho脿n th脿nh! ({processed_frame.duration:.2f}s)")
                
            except Exception as e:
                logger.error(f"鉂?C岷h {frame_num} th岷 b岷: {e}")
                logger.warning(f"鈿狅笍  B峄?qua c岷h {frame_num}, ti岷縫 t峄 x峄?l媒 c谩c c岷h c貌n l岷...")
                continue
    
    # C峄檔g duration c峄 c谩c c岷h 膽茫 ho脿n th脿nh tr瓢峄沜 膽贸
    for i in completed:
        frame = storyboard.frames[i]
        storyboard.total_duration += frame.duration
    
    # === 10. Gh茅p video cu峄慽 c霉ng ===
    if not args.skip_concat:
        logger.info(f"")
        logger.info(f"{'='*50}")
        logger.info(f"馃幀 Gh茅p {total_scenes} 膽o岷 video th脿nh video cu峄慽 c霉ng...")
        logger.info(f"{'='*50}")
        
        segment_paths = []
        missing_segments = []
        
        for i in range(total_scenes):
            frame = storyboard.frames[i]
            seg_path = frame.video_segment_path
            
            if seg_path and os.path.exists(seg_path):
                segment_paths.append(seg_path)
            else:
                # Th峄?t矛m segment file d峄盿 tr锚n naming convention
                from pixelle_video.utils.os_util import get_task_frame_path
                fallback_path = get_task_frame_path(task_id, i, "segment")
                if os.path.exists(fallback_path):
                    segment_paths.append(fallback_path)
                else:
                    missing_segments.append(i + 1)
        
        if missing_segments:
            logger.error(f"鉂?Thi岷縰 segment cho c谩c c岷h: {missing_segments}")
            logger.error(f"   Video cu峄慽 c霉ng s岷?kh么ng 膽岷 膽峄?")
            if len(missing_segments) > total_scenes // 2:
                logger.error(f"   Qu谩 nhi峄乽 c岷h thi岷縰. H峄 gh茅p video.")
                return
        
        from pixelle_video.services.video import VideoService
        from pixelle_video.utils.os_util import get_task_final_video_path
        
        video_service = VideoService()
        final_video_path = get_task_final_video_path(task_id)
        
        final_path = video_service.concat_videos(
            videos=segment_paths,
            output=final_video_path,
            bgm_path=args.bgm,  # manual override, None if using audio-layer
            bgm_volume=args.bgm_volume,
            bgm_mode="loop"
        )
        
        # === 10b. Smart Audio Layer: per-scene BGM + SFX t峄?audio manifest ===
        if args.audio_layer and not args.bgm:
            logger.info(f"")
            logger.info(f"{'='*50}")
            logger.info(f"馃幍 Smart Audio Mixer: gh茅p nh岷 theo t峄玭g c岷h...")
            logger.info(f"{'='*50}")
            try:
                from pixelle_video.services.smart_audio_mixer import mix_smart_audio

                audio_dir = str(Path(__file__).parent / "assets" / "audio")
                audio_layered_path = str(final_video_path).replace(".mp4", "_audio.mp4")

                result = mix_smart_audio(
                    final_video_path=final_path,
                    output_path=audio_layered_path,
                    frames_dir=str(task_dir / "frames"),
                    script_data=script_data,
                    audio_dir=audio_dir,
                    bgm_volume=args.audio_bgm_volume,
                    sfx_volume=args.audio_sfx_volume,
                    transition_sfx_path=str((template_params or {}).get("transition_sfx_path") or ""),
                    transition_sfx_volume=float((template_params or {}).get("transition_sfx_volume") or 0.18),
                    transition_duck_factor=float((template_params or {}).get("transition_duck_factor") or 0.20),
                    transition_duck_window_s=float((template_params or {}).get("transition_duck_window_s") or 0.50),
                    total_scenes=total_scenes,
                )

                if result:
                    final_path = result
                    logger.success(f"   BGM + SFX theo t峄玭g c岷h 膽茫 膽瓢峄 mix v脿o video!")
                else:
                    logger.warning(f"   Smart audio mix th岷 b岷, gi峄?nguy锚n video g峄慶")
            except Exception as e:
                logger.warning(f"鈿狅笍 Smart audio layer th岷 b岷 (b峄?qua): {e}")

        # === 10c. Series Avatar Overlay (optional) ===
        try:
            avatar_path = (template_params or {}).get("avatar_path") or ""
            if isinstance(avatar_path, str) and avatar_path.strip():
                from pathlib import Path as _Path

                avatar_size = int((template_params or {}).get("avatar_size_px") or 40)
                avatar_margin = int((template_params or {}).get("avatar_margin_px") or 24)
                avatar_pos = (template_params or {}).get("avatar_position") or "bottom_right"

                avatar_file = _Path(avatar_path)
                if not avatar_file.is_absolute():
                    avatar_file = _Path(os.getcwd()) / avatar_file

                if avatar_file.exists():
                    avatar_out = str(final_path).replace(".mp4", "_avt.mp4")
                    avatar_video_crf = int((template_params or {}).get("video_crf") or 23)
                    avatar_video_preset = str((template_params or {}).get("video_preset") or "medium")
                    final_path = video_service.overlay_avatar(
                        video=str(final_path),
                        avatar_image=str(avatar_file),
                        output=avatar_out,
                        size_px=avatar_size,
                        margin_px=avatar_margin,
                        position=avatar_pos,
                        video_crf=avatar_video_crf,
                        video_preset=avatar_video_preset,
                    )
                else:
                    logger.warning(f"⚠️ Avatar image not found, skipping: {avatar_file}")
        except Exception as e:
            logger.warning(f"⚠️ Avatar overlay failed (skipped): {e}")
        
        logger.success(f"")
        logger.success(f"{'='*50}")
        logger.success(f"馃帀 VIDEO HO脌N TH脌NH!")
        logger.success(f"馃搧 膼瓢峄漬g d岷玭: {final_path}")
        logger.success(f"鈴憋笍  T峄昻g th峄漣 l瓢峄g: {storyboard.total_duration:.2f}s")
        logger.success(f"馃幀 S峄?c岷h: {total_scenes}")
        logger.success(f"{'='*50}")
        
        # === 11. Generate YouTube SEO metadata ===
        if args.skip_seo_generation:
            logger.info("📵 Skipped LLM SEO generation")
        elif not script_data.get("youtube_seo"):
            logger.info("")
            logger.info(f"{'='*50}")
            logger.info(f"馃搳 Generating YouTube SEO metadata...")
            logger.info(f"{'='*50}")
            try:
                from pixelle_video.prompts.youtube_seo import build_youtube_seo_prompt
                
                seo_prompt = build_youtube_seo_prompt(
                    title=script_data.get("title", topic),
                    youtube_title=youtube_title,
                    narrations=narrations,
                    language=script_data.get("language") or project_config.get("language") or "Japanese",
                    channel=script_data.get("channel") or project_config.get("channel") or project_config.get("_channel", "sukoyaka_life"),
                    author=script_data.get("author") or template_params.get("author") or "@Pixelle.AI",
                    brand=script_data.get("brand") or template_params.get("brand") or "Pixelle Video",
                    n_scenes=total_scenes,
                )
                
                llm = core.llm
                seo_response = await llm(seo_prompt)
                
                # Parse JSON from LLM response
                import re
                json_match = re.search(r'\{[\s\S]*\}', seo_response)
                if json_match:
                    seo_data = json.loads(json_match.group())
                    script_data["youtube_seo"] = seo_data
                    
                    # Save to script.json
                    with open(script_json_path, "w", encoding="utf-8") as f:
                        json.dump(script_data, f, ensure_ascii=False, indent=2)
                    
                    # Also save readable SEO file
                    seo_file = task_dir / "youtube_seo.md"
                    with open(seo_file, "w", encoding="utf-8") as f:
                        f.write(f"# YouTube SEO 鈥?{youtube_title}\n\n")
                        f.write(f"## Description\n```\n{seo_data.get('description', '')}\n```\n\n")
                        f.write(f"## Hashtags\n{' '.join(seo_data.get('hashtags', []))}\n\n")
                        f.write(f"## Tags\n{', '.join(seo_data.get('tags', []))}\n\n")
                        if seo_data.get('thumbnail_prompts'):
                            f.write(f"## Thumbnail Prompts\n")
                            for i, p in enumerate(seo_data['thumbnail_prompts']):
                                f.write(f"### V{i+1}\n{_thumbnail_prompt_text(p)}\n\n")
                    
                    logger.success(f"馃搳 SEO metadata saved to {seo_file}")
                    logger.info(f"   Description: {len(seo_data.get('description', ''))} chars")
                    logger.info(f"   Hashtags: {len(seo_data.get('hashtags', []))}")
                    logger.info(f"   Tags: {len(seo_data.get('tags', []))}")
                else:
                    logger.warning("鈿狅笍 Could not parse SEO JSON from LLM response")
            except Exception as e:
                logger.warning(f"鈿狅笍 SEO generation failed: {e}")
        else:
            logger.info(f"馃搳 YouTube SEO metadata already exists (cached)")
        
        # === 12. Generate Thumbnails ===
        thumbnail_dir = task_dir / "thumbnails"
        existing_thumbs = list(thumbnail_dir.glob("thumbnail_v*.png")) if thumbnail_dir.exists() else []
        
        if args.skip_thumbnail_generation:
            logger.info("📵 Skipped thumbnail generation")
        elif not existing_thumbs and script_data.get("youtube_seo", {}).get("thumbnail_prompts"):
            logger.info("")
            logger.info(f"{'='*50}")
            logger.info(f"馃柤锔? Generating thumbnails...")
            logger.info(f"{'='*50}")
            try:
                thumbnail_dir.mkdir(parents=True, exist_ok=True)
                thumb_prompts = script_data["youtube_seo"]["thumbnail_prompts"]
                
                # Load character refs for thumbnail
                char_refs_path = task_dir / "character_refs.json"
                char_media_ids = []
                if char_refs_path.exists():
                    with open(char_refs_path, "r", encoding="utf-8") as f:
                        char_refs = json.load(f)
                    if isinstance(char_refs, dict):
                        char_media_ids = list(char_refs.values())[:2]
                    elif isinstance(char_refs, list):
                        char_media_ids = [r.get("media_id") for r in char_refs if isinstance(r, dict) and r.get("media_id")][:2]
                
                for i, prompt in enumerate(thumb_prompts[:2]):
                    logger.info(f"   Generating thumbnail V{i+1}...")
                    try:
                        prompt_text = _thumbnail_prompt_text(prompt)
                        channel_style = project_config.get("thumbnail_style", "cinematic editorial thumbnail")
                        # Use FlowKit/Imagen to generate thumbnail
                        result = await core.media(
                            prompt=f"{channel_style}. {prompt_text}",
                            media_type="image",
                            width=1280,
                            height=720,
                            character_media_ids=char_media_ids if char_media_ids else None,
                        )
                        
                        local_result_path = getattr(result, "path", None) or getattr(result, "url", None)
                        if result and local_result_path:
                            import shutil
                            thumb_path = thumbnail_dir / f"thumbnail_v{i+1}.png"
                            shutil.copy2(local_result_path, thumb_path)
                            logger.success(f"   鉁?Thumbnail V{i+1}: {thumb_path}")
                        else:
                            logger.warning(f"   鈿狅笍 Thumbnail V{i+1} generation returned no result")
                    except Exception as e:
                        logger.warning(f"   鈿狅笍 Thumbnail V{i+1} failed: {e}")
                    
                    # Cooldown between generations
                    import asyncio as _asyncio
                    await _asyncio.sleep(5)
                    
            except Exception as e:
                logger.warning(f"鈿狅笍 Thumbnail generation failed: {e}")
        elif existing_thumbs:
            logger.info(f"馃柤锔? Thumbnails already exist: {len(existing_thumbs)} files")
        
    else:
        logger.info(f"鈴笍  B峄?qua gh茅p video (--skip-concat)")
        logger.success(f"鉁?膼茫 x峄?l媒 xong {len(incomplete)} c岷h c貌n thi岷縰!")


if __name__ == "__main__":
    asyncio.run(main())
