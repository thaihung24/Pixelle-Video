"""
Resume Pipeline - Tiếp tục chạy dự án bị gián đoạn

Script này đọc lại script.json từ dự án cũ, kiểm tra những cảnh nào đã hoàn thành
(có đủ audio + video + composed + segment), và chỉ chạy lại các cảnh chưa hoàn thành.

Cách dùng:
    python resume_pipeline.py --task-dir output/20260510_022626_d0be

Tùy chọn:
    --task-dir       Đường dẫn tới thư mục dự án (bắt buộc)
    --style          Phong cách hình ảnh (vd: 'Studio Ghibli style')
    --voice          Giọng TTS (mặc định: ja-JP-NanamiNeural)
    --tts-mode       Chế độ TTS: local, omnivoice, comfyui (mặc định: local)
    --ref-audio      Đường dẫn file audio mẫu cho voice cloning (OmniVoice)
    --ref-text       Đoạn text tương ứng với file audio mẫu (OmniVoice)
    --bgm            Đường dẫn nhạc nền
    --bgm-volume     Âm lượng nhạc nền (mặc định: 0.2)
    --template       Template frame (mặc định: đọc từ config.yaml)
    --skip-concat    Chỉ chạy các cảnh thiếu, KHÔNG ghép video cuối
"""

import asyncio
import argparse
import json
import os
import sys
from pathlib import Path

# Thêm đường dẫn project vào sys.path
sys.path.append(str(Path(__file__).parent))

from loguru import logger


def scan_completed_frames(frames_dir: str, total_scenes: int) -> dict:
    """
    Quét thư mục frames để xác định trạng thái hoàn thành của từng cảnh.
    
    Returns:
        dict với key là frame_index (0-based), value là dict trạng thái
    """
    status = {}
    for i in range(total_scenes):
        frame_num = i + 1  # 1-based filename
        prefix = f"{frame_num:02d}"
        
        audio_path = os.path.join(frames_dir, f"{prefix}_audio.mp3")
        video_path = os.path.join(frames_dir, f"{prefix}_video.mp4")
        composed_path = os.path.join(frames_dir, f"{prefix}_composed.png")
        segment_path = os.path.join(frames_dir, f"{prefix}_segment.mp4")
        image_path = os.path.join(frames_dir, f"{prefix}_image.png")
        
        has_audio = os.path.exists(audio_path) and os.path.getsize(audio_path) > 0
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


async def main():
    parser = argparse.ArgumentParser(description="Resume Pixelle-Video Pipeline từ dự án bị gián đoạn")
    parser.add_argument("--task-dir", type=str, required=True,
                        help="Đường dẫn tới thư mục dự án (vd: output/20260510_022626_d0be)")
    parser.add_argument("--style", type=str, default="",
                        help="Phong cách hình ảnh (vd: 'Studio Ghibli style')")
    parser.add_argument("--voice", type=str, default="ja-JP-NanamiNeural",
                        help="Giọng TTS (mặc định: ja-JP-NanamiNeural)")
    parser.add_argument("--tts-mode", type=str, default="local",
                        choices=["local", "omnivoice", "comfyui"],
                        help="Chế độ TTS: local (Edge TTS), omnivoice (clone giọng), comfyui (mặc định: local)")
    parser.add_argument("--ref-audio", type=str, default=None,
                        help="Đường dẫn file audio mẫu cho voice cloning (dùng với --tts-mode omnivoice)")
    parser.add_argument("--ref-text", type=str, default=None,
                        help="Đoạn text tương ứng với file audio mẫu (dùng với --tts-mode omnivoice)")
    parser.add_argument("--bgm", type=str, default=None,
                        help="Đường dẫn nhạc nền (optional)")
    parser.add_argument("--bgm-volume", type=float, default=0.2,
                        help="Âm lượng nhạc nền (mặc định: 0.2)")
    parser.add_argument("--template", type=str, default=None,
                        help="Template frame (mặc định: đọc từ config.yaml)")
    parser.add_argument("--skip-concat", action="store_true",
                        help="Chỉ chạy các cảnh thiếu, KHÔNG ghép video cuối")
    parser.add_argument("--tts-speed", type=float, default=1.0,
                        help="Tốc độ giọng đọc TTS (mặc định: 1.0)")
    
    args = parser.parse_args()
    
    # === 1. Xác định đường dẫn dự án ===
    # Validate OmniVoice params
    if args.tts_mode == "omnivoice":
        if not args.ref_audio:
            logger.error("❌ Chế độ omnivoice yêu cầu --ref-audio (file audio mẫu)")
            sys.exit(1)
        if not os.path.exists(args.ref_audio):
            logger.error(f"❌ File ref-audio không tồn tại: {args.ref_audio}")
            sys.exit(1)
        logger.info(f"🎤 Voice Cloning mode: ref_audio={args.ref_audio}")
        if args.ref_text:
            logger.info(f"   ref_text: {args.ref_text[:60]}...")
    
    task_dir = Path(args.task_dir)
    if not task_dir.is_absolute():
        task_dir = Path(__file__).parent / task_dir
    
    task_dir = task_dir.resolve()
    
    if not task_dir.exists():
        logger.error(f"❌ Thư mục dự án không tồn tại: {task_dir}")
        sys.exit(1)
    
    script_json_path = task_dir / "script.json"
    if not script_json_path.exists():
        logger.error(f"❌ Không tìm thấy script.json trong: {task_dir}")
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
    
    # === 2. Đọc kịch bản ===
    with open(script_json_path, "r", encoding="utf-8") as f:
        script_data = json.load(f)
    
    narrations = script_data.get("narrations", [])
    topic = script_data.get("topic", "Untitled")
    total_scenes = len(narrations)
    
    if total_scenes == 0:
        logger.error("❌ Kịch bản rỗng (0 narrations)")
        sys.exit(1)
    
    logger.info(f"📖 Đọc kịch bản: '{topic}' — {total_scenes} cảnh")
    
    # === 3. Quét trạng thái hoàn thành ===
    frame_status = scan_completed_frames(str(frames_dir), total_scenes)
    
    completed = [i for i, s in frame_status.items() if s["complete"]]
    incomplete = [i for i, s in frame_status.items() if not s["complete"]]
    
    logger.info(f"✅ Đã hoàn thành: {len(completed)}/{total_scenes} cảnh")
    if completed:
        completed_nums = [frame_status[i]["frame_num"] for i in completed]
        logger.info(f"   Cảnh đã xong: {completed_nums}")
    
    if not incomplete:
        logger.success(f"🎉 Tất cả {total_scenes} cảnh đều đã hoàn thành!")
        if not args.skip_concat:
            logger.info("⏩ Tiến hành ghép video cuối cùng...")
        else:
            logger.info("✅ Không cần làm gì thêm.")
            return
    else:
        incomplete_nums = [frame_status[i]["frame_num"] for i in incomplete]
        logger.warning(f"⚠️  Cần chạy lại: {len(incomplete)} cảnh: {incomplete_nums}")
    
    # === 4. Khởi tạo Pixelle-Video Core ===
    logger.info("🔧 Khởi tạo Pixelle-Video Core...")
    from pixelle_video.service import PixelleVideoCore
    core = PixelleVideoCore()
    await core.initialize()
    
    # === 5. Đọc cấu hình ===
    from pixelle_video.config import config_manager
    config_yaml = config_manager.config
    
    frame_template = args.template or config_yaml.template.default_template
    
    # Xác định workflow
    from pixelle_video.utils.template_util import get_template_type
    template_name = Path(frame_template).name
    template_type = get_template_type(template_name)
    
    if template_type == "video":
        media_workflow = "flowkit/google-veo"
    elif template_type == "image":
        media_workflow = "flowkit/google-imagen-3"
    else:
        media_workflow = None
    
    logger.info(f"🎨 Template: {frame_template} (type: {template_type})")
    logger.info(f"🎥 Media workflow: {media_workflow}")
    
    # === 5b. Generate YouTube title (if not already saved) ===
    youtube_title = script_data.get("youtube_title", "")
    if not youtube_title:
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
            
            logger.success(f"📺 YouTube title generated: {youtube_title}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to generate YouTube title: {e}")
            youtube_title = script_data.get("title", topic)
    else:
        logger.info(f"📺 YouTube title (cached): {youtube_title}")
    
    # === 6. Tạo cấu hình Storyboard ===
    from pixelle_video.models.storyboard import (
        Storyboard, StoryboardFrame, StoryboardConfig
    )
    from pixelle_video.services.frame_html import HTMLFrameGenerator
    from pixelle_video.utils.template_util import resolve_template_path
    
    template_path = resolve_template_path(frame_template)
    generator = HTMLFrameGenerator(template_path)
    media_width, media_height = generator.get_media_size()
    
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
        template_params={
            "title": youtube_title,
            "author": "@sukoyaka.life1",
            "describe": "健康長寿の知恵",
            "brand": "健康長寿の知恵"
        }
    )
    
    logger.info(f"🔍 StoryboardConfig check:")
    logger.info(f"   tts_inference_mode={storyboard_config.tts_inference_mode!r}")
    logger.info(f"   ref_audio={storyboard_config.ref_audio!r}")
    logger.info(f"   ref_text={storyboard_config.ref_text!r}")
    logger.info(f"   voice_id={storyboard_config.voice_id!r}")
    logger.info(f"   tts_speed={storyboard_config.tts_speed!r}")
    
    # === 7. Tạo image prompts cho các cảnh chưa hoàn thành ===
    # Chỉ tạo prompts nếu template cần media
    image_prompts = [None] * total_scenes
    
    # Check if script.json contains pre-generated video_prompts (from generate_anime_storyboard.py)
    pre_generated_prompts = script_data.get("video_prompts", [])
    if pre_generated_prompts and len(pre_generated_prompts) == total_scenes:
        logger.info(f"📋 Found {len(pre_generated_prompts)} pre-generated video prompts in script.json (anime storyboard mode)")
        
        scenes = script_data.get("scenes", [])
        
        # Anime style prefix to ensure consistent anime output
        ANIME_PREFIX = "Japanese anime style, Studio Ghibli inspired, soft watercolor textures, warm cinematic lighting. "
        
        # Use pre-generated prompts with ANIME_PREFIX + Setting + base prompt
        # Character visuals are NOT in text prompt (already passed via ref image media_ids)
        for i in range(total_scenes):
            if not (frame_status[i].get("video_path") or frame_status[i].get("image_path")):
                base_prompt = pre_generated_prompts[i]
                
                # Inject setting from scene data
                setting = ""
                if i < len(scenes) and scenes[i].get("setting"):
                    setting = f"Setting: {scenes[i]['setting']}. "
                
                # Compose: ANIME_PREFIX + Setting + Video Prompt
                image_prompts[i] = f"{ANIME_PREFIX}{setting}{base_prompt}"
                
        assigned = sum(1 for p in image_prompts if p is not None)
        logger.info(f"   Assigned {assigned} prompts (ANIME_PREFIX + Setting + base prompt)")
    else:
        # Fallback: generate prompts via LLM (original behavior)
        needs_prompt = [i for i in incomplete if not (frame_status[i]["video_path"] or frame_status[i]["image_path"])]
        
        if template_type in ["image", "video"] and needs_prompt:
            logger.info(f"🖼️  Tạo image prompts cho {len(needs_prompt)} cảnh chưa có media...")
            
            from pixelle_video.utils.content_generators import generate_image_prompts
            from pixelle_video.utils.prompt_helper import build_image_prompt
            
            # Chỉ gửi narrations của các cảnh chưa xong để tiết kiệm API calls
            incomplete_narrations = [narrations[i] for i in needs_prompt]
            
            llm = core.llm
            base_prompts = await generate_image_prompts(
                llm,
                narrations=incomplete_narrations,
                min_words=30,
                max_words=60,
            )
            
            # Áp dụng style prefix
            image_config = core.config.get("comfyui", {}).get("image", {})
            prompt_prefix = args.style if args.style else image_config.get("prompt_prefix", "")
            
            for idx, base_prompt in enumerate(base_prompts):
                frame_idx = needs_prompt[idx]
                final_prompt = build_image_prompt(base_prompt, prompt_prefix)
                image_prompts[frame_idx] = final_prompt
    
    # === 8. Build per-scene character_media_ids mapping ===
    from datetime import datetime
    
    # Load character_refs.json for char_id → media_id mapping
    char_id_to_media_id = {}
    char_refs_path = task_dir.parent / "character_refs.json"
    if char_refs_path.exists():
        with open(char_refs_path, "r", encoding="utf-8") as f:
            char_refs = json.load(f)
        for cr in char_refs:
            char_id_to_media_id[cr["id"]] = cr["media_id"]
        logger.info(f"📎 Loaded {len(char_id_to_media_id)} character ref mappings from {char_refs_path.name}")
    
    # Build per-scene character_media_ids from scenes data
    scenes_data = script_data.get("scenes", [])
    per_scene_char_media_ids = [None] * total_scenes
    for i in range(total_scenes):
        if i < len(scenes_data) and scenes_data[i].get("characters"):
            scene_chars = scenes_data[i]["characters"]
            scene_media_ids = [char_id_to_media_id[cid] for cid in scene_chars if cid in char_id_to_media_id]
            if scene_media_ids:
                per_scene_char_media_ids[i] = scene_media_ids
    
    assigned_refs = sum(1 for x in per_scene_char_media_ids if x)
    logger.info(f"   {assigned_refs}/{total_scenes} scenes have per-scene character refs")
    
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
            character_media_ids=per_scene_char_media_ids[i],
            created_at=datetime.now()
        )
        
        # Bỏ qua image_prompt nếu đã có media sẵn để tránh generate lại
        if status["video_path"] or status["image_path"]:
            frame.image_prompt = None
        
        # Gán lại đường dẫn đã có sẵn (kể cả cảnh chưa complete)
        if status["audio_path"]:
            frame.audio_path = status["audio_path"]
            # Đọc duration từ audio file
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
    
    # === 9. Xử lý các cảnh chưa hoàn thành ===
    if incomplete:
        logger.info(f"🚀 Bắt đầu xử lý {len(incomplete)} cảnh chưa hoàn thành...")
        
        for count, frame_idx in enumerate(incomplete, 1):
            frame = storyboard.frames[frame_idx]
            frame_num = frame_idx + 1
            
            logger.info(f"")
            logger.info(f"{'='*50}")
            logger.info(f"🎬 Cảnh {frame_num}/{total_scenes} (tiến độ resume: {count}/{len(incomplete)})")
            logger.info(f"{'='*50}")
            logger.info(f"📝 Nội dung: {frame.narration[:60]}...")
            
            try:
                processed_frame = await core.frame_processor(
                    frame=frame,
                    storyboard=storyboard,
                    config=storyboard_config,
                    total_frames=total_scenes,
                )
                
                storyboard.frames[frame_idx] = processed_frame
                storyboard.total_duration += processed_frame.duration
                
                logger.success(f"✅ Cảnh {frame_num} hoàn thành! ({processed_frame.duration:.2f}s)")
                
            except Exception as e:
                logger.error(f"❌ Cảnh {frame_num} thất bại: {e}")
                logger.warning(f"⚠️  Bỏ qua cảnh {frame_num}, tiếp tục xử lý các cảnh còn lại...")
                continue
    
    # Cộng duration của các cảnh đã hoàn thành trước đó
    for i in completed:
        frame = storyboard.frames[i]
        storyboard.total_duration += frame.duration
    
    # === 10. Ghép video cuối cùng ===
    if not args.skip_concat:
        logger.info(f"")
        logger.info(f"{'='*50}")
        logger.info(f"🎬 Ghép {total_scenes} đoạn video thành video cuối cùng...")
        logger.info(f"{'='*50}")
        
        segment_paths = []
        missing_segments = []
        
        for i in range(total_scenes):
            frame = storyboard.frames[i]
            seg_path = frame.video_segment_path
            
            if seg_path and os.path.exists(seg_path):
                segment_paths.append(seg_path)
            else:
                # Thử tìm segment file dựa trên naming convention
                from pixelle_video.utils.os_util import get_task_frame_path
                fallback_path = get_task_frame_path(task_id, i, "segment")
                if os.path.exists(fallback_path):
                    segment_paths.append(fallback_path)
                else:
                    missing_segments.append(i + 1)
        
        if missing_segments:
            logger.error(f"❌ Thiếu segment cho các cảnh: {missing_segments}")
            logger.error(f"   Video cuối cùng sẽ không đầy đủ!")
            if len(missing_segments) > total_scenes // 2:
                logger.error(f"   Quá nhiều cảnh thiếu. Hủy ghép video.")
                return
        
        from pixelle_video.services.video import VideoService
        from pixelle_video.utils.os_util import get_task_final_video_path
        
        video_service = VideoService()
        final_video_path = get_task_final_video_path(task_id)
        
        final_path = video_service.concat_videos(
            videos=segment_paths,
            output=final_video_path,
            bgm_path=args.bgm,
            bgm_volume=args.bgm_volume,
            bgm_mode="loop"
        )
        
        logger.success(f"")
        logger.success(f"{'='*50}")
        logger.success(f"🎉 VIDEO HOÀN THÀNH!")
        logger.success(f"📁 Đường dẫn: {final_path}")
        logger.success(f"⏱️  Tổng thời lượng: {storyboard.total_duration:.2f}s")
        logger.success(f"🎬 Số cảnh: {total_scenes}")
        logger.success(f"{'='*50}")
        
        # === 11. Generate YouTube SEO metadata ===
        if not script_data.get("youtube_seo"):
            logger.info("")
            logger.info(f"{'='*50}")
            logger.info(f"📊 Generating YouTube SEO metadata...")
            logger.info(f"{'='*50}")
            try:
                from pixelle_video.prompts.youtube_seo import build_youtube_seo_prompt
                
                seo_prompt = build_youtube_seo_prompt(
                    title=script_data.get("title", topic),
                    youtube_title=youtube_title,
                    narrations=narrations,
                    language=script_data.get("language", "Japanese"),
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
                        f.write(f"# YouTube SEO — {youtube_title}\n\n")
                        f.write(f"## Description\n```\n{seo_data.get('description', '')}\n```\n\n")
                        f.write(f"## Hashtags\n{' '.join(seo_data.get('hashtags', []))}\n\n")
                        f.write(f"## Tags\n{', '.join(seo_data.get('tags', []))}\n\n")
                        if seo_data.get('thumbnail_prompts'):
                            f.write(f"## Thumbnail Prompts\n")
                            for i, p in enumerate(seo_data['thumbnail_prompts']):
                                f.write(f"### V{i+1}\n{p}\n\n")
                    
                    logger.success(f"📊 SEO metadata saved to {seo_file}")
                    logger.info(f"   Description: {len(seo_data.get('description', ''))} chars")
                    logger.info(f"   Hashtags: {len(seo_data.get('hashtags', []))}")
                    logger.info(f"   Tags: {len(seo_data.get('tags', []))}")
                else:
                    logger.warning("⚠️ Could not parse SEO JSON from LLM response")
            except Exception as e:
                logger.warning(f"⚠️ SEO generation failed: {e}")
        else:
            logger.info(f"📊 YouTube SEO metadata already exists (cached)")
        
        # === 12. Generate Thumbnails ===
        thumbnail_dir = task_dir / "thumbnails"
        existing_thumbs = list(thumbnail_dir.glob("thumbnail_v*.png")) if thumbnail_dir.exists() else []
        
        if not existing_thumbs and script_data.get("youtube_seo", {}).get("thumbnail_prompts"):
            logger.info("")
            logger.info(f"{'='*50}")
            logger.info(f"🖼️  Generating thumbnails...")
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
                    char_media_ids = list(char_refs.values())[:2]  # Max 2 character refs
                
                for i, prompt in enumerate(thumb_prompts[:2]):
                    logger.info(f"   Generating thumbnail V{i+1}...")
                    try:
                        # Use FlowKit/Imagen to generate thumbnail
                        result = await core.media_service(
                            prompt=f"Japanese anime style, Studio Ghibli inspired. {prompt}",
                            media_type="image",
                            width=1280,
                            height=720,
                            character_media_ids=char_media_ids if char_media_ids else None,
                        )
                        
                        if result and hasattr(result, 'path') and result.path:
                            import shutil
                            thumb_path = thumbnail_dir / f"thumbnail_v{i+1}.png"
                            shutil.copy2(result.path, thumb_path)
                            logger.success(f"   ✅ Thumbnail V{i+1}: {thumb_path}")
                        else:
                            logger.warning(f"   ⚠️ Thumbnail V{i+1} generation returned no result")
                    except Exception as e:
                        logger.warning(f"   ⚠️ Thumbnail V{i+1} failed: {e}")
                    
                    # Cooldown between generations
                    import asyncio as _asyncio
                    await _asyncio.sleep(5)
                    
            except Exception as e:
                logger.warning(f"⚠️ Thumbnail generation failed: {e}")
        elif existing_thumbs:
            logger.info(f"🖼️  Thumbnails already exist: {len(existing_thumbs)} files")
        
    else:
        logger.info(f"⏭️  Bỏ qua ghép video (--skip-concat)")
        logger.success(f"✅ Đã xử lý xong {len(incomplete)} cảnh còn thiếu!")


if __name__ == "__main__":
    asyncio.run(main())

