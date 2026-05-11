import asyncio
import argparse
from pathlib import Path

# Thêm đường dẫn project vào sys.path để chạy ở bất kỳ đâu
import sys
sys.path.append(str(Path(__file__).parent))

from pixelle_video.service import PixelleVideoCore
from pixelle_video.pipelines.standard import StandardPipeline
from loguru import logger

async def main():
    parser = argparse.ArgumentParser(description="Run Pixelle-Video Pipeline from Terminal")
    parser.add_argument("--topic", type=str, required=True, help="Chủ đề của video")
    parser.add_argument("--scenes", type=int, default=5, help="Số lượng cảnh (mặc định: 5)")
    parser.add_argument("--style", type=str, default="", help="Phong cách hình ảnh (vd: 'Studio Ghibli style')")
    parser.add_argument("--voice", type=str, default="zh-CN-YunjianNeural", help="Giọng TTS (mặc định: tiếng Trung)")
    parser.add_argument("--workflow", type=str, default="runninghub/digital_image.json", help="Workflow để tạo ảnh/video")
    parser.add_argument("--bgm", type=str, default=None, help="Đường dẫn nhạc nền (optional)")
    parser.add_argument("--script-only", action="store_true", help="Chỉ chạy LLM để tạo kịch bản/prompt, KHÔNG tạo video")
    
    args = parser.parse_args()
    
    logger.info("Initializing Pixelle-Video Core...")
    core = PixelleVideoCore()
    await core.initialize()
    
    logger.info(f"Running Standard Pipeline for topic: {args.topic}")
    pipeline = StandardPipeline(core)
    
    # Cấu hình các tham số chạy pipeline
    params = {
        "mode": "generate",
        "n_scenes": args.scenes,
        "prompt_prefix": args.style if args.style else None,  # Ghi đè cấu hình style mặc định trong config.yaml
        "workflow_key": args.workflow,
        "tts_voice": args.voice,
        "tts_speed": 1.2,
        "tts_inference_mode": "local",
        "bgm_path": args.bgm,
        "bgm_volume": 0.2
    }
    
    try:
        if args.script_only:
            from pixelle_video.pipelines.linear import PipelineContext
            ctx = PipelineContext(input_text=args.topic, params=params)
            await pipeline.setup_environment(ctx)
            await pipeline.generate_content(ctx)
            await pipeline.determine_title(ctx)
            await pipeline.plan_visuals(ctx)
            
            logger.info("="*50)
            logger.success("🚀 CHỈ CHẠY LLM (SCRIPT ONLY) - KẾT QUẢ ĐẦU RA:")
            logger.info(f"📍 Tiêu đề: {ctx.title}")
            
            # Lưu ra file markdown
            import os
            output_file = os.path.join(ctx.task_dir, "script_preview.md")
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(f"# 📍 Tiêu đề: {ctx.title}\n\n")
                
                for i, (narration, prompt) in enumerate(zip(ctx.narrations, ctx.image_prompts)):
                    logger.info(f"\n--- CẢNH {i+1} ---")
                    logger.info(f"🎙️ Lời thoại : {narration}")
                    logger.info(f"🎨 Lệnh vẽ   : {prompt}")
                    
                    f.write(f"## --- CẢNH {i+1} ---\n")
                    f.write(f"**🎙️ Lời thoại:** {narration}\n\n")
                    f.write(f"**🎨 Lệnh vẽ:** `{prompt}`\n\n")
                    
            logger.info("="*50)
            logger.success(f"✅ Đã lưu toàn bộ kịch bản ra file: {output_file}")
        else:
            # Chạy toàn bộ pipeline
            result = await pipeline(text=args.topic, **params)
            logger.info("="*50)
            logger.success(f"Video đã tạo thành công tại:\n{result.video_path}")
            logger.info(f"Thời lượng: {result.duration} giây")
            logger.info("="*50)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
