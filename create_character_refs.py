"""
Create Character References — Tự động tạo ảnh tham chiếu nhân vật trên FlowKit

Đọc characters từ blueprint.json HOẶC series_bible.json
→ Gọi FlowKit/Imagen 3 sinh ảnh chân dung cho từng nhân vật
→ Lưu media_ids vào config.yaml (flowkit.character_media_ids)
→ Khi pipeline chạy, media_ids được truyền vào generate-image API
→ Imagen 3 dùng ảnh ref để vẽ nhân vật nhất quán trong mọi scene
→ Ảnh mồi từ Imagen 3 → start_image cho Veo → video nhất quán

Usage:
    # Từ series bible (KHUYẾN KHÍCH cho series dài tập)
    python create_character_refs.py --series-bible series_bible.json

    # Từ blueprint (1 tập đơn lẻ)
    python create_character_refs.py --blueprint output/test/blueprint.json

Sau khi chạy xong:
    - Ảnh nhân vật lưu tại output/characters/
    - config.yaml được update tự động với character_media_ids
    - character_refs.json lưu mapping id → media_id để tra cứu
    - resume_pipeline.py sẽ tự dùng media_ids cho nhất quán nhân vật
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


async def generate_character_image(flowkit_service, character: dict, output_dir: Path) -> dict:
    """
    Sinh ảnh tham chiếu cho 1 nhân vật và trả về media_id.
    """
    char_id = character["id"]
    visual = character["visual"]
    name = character.get("name", char_id)
    
    # Prompt: chỉ vẽ chân dung nhân vật, nền đơn giản
    portrait_prompt = (
        f"Character portrait reference sheet, anime cel-shaded style, "
        f"clean white background, front-facing view, upper body, "
        f"detailed face and clothing, {visual}"
    )
    
    logger.info(f"🎨 Generating reference image for [{char_id}] {name}...")
    logger.info(f"   Prompt: {portrait_prompt[:100]}...")
    
    import httpx
    
    # Gọi FlowKit API trực tiếp để lấy media_id
    payload = {
        "prompt": portrait_prompt,
        "project_id": flowkit_service.project_id,
        "aspect_ratio": "IMAGE_ASPECT_RATIO_SQUARE",  # Chân dung vuông cho ref
        "user_paygate_tier": flowkit_service.user_paygate_tier,
    }
    
    async with httpx.AsyncClient(timeout=flowkit_service.timeout) as client:
        resp = await client.post(
            f"{flowkit_service.base_url}/api/flow/generate-image",
            json=payload,
        )
        
        if resp.status_code != 200:
            logger.error(f"FlowKit error {resp.status_code}: {resp.text[:300]}")
            return None
        
        data = resp.json()
    
    # Extract media_id
    media_id = None
    media_list = data.get("media", [])
    if media_list and isinstance(media_list, list):
        first = media_list[0]
        if isinstance(first, dict):
            media_id = first.get("name")
        else:
            media_id = str(first)
    
    if not media_id:
        logger.error(f"Cannot extract media_id from response: {data}")
        return None
    
    logger.success(f"✅ [{char_id}] media_id: {media_id}")
    
    # Download image for visual reference
    try:
        resolved_url = await flowkit_service._resolve_media_id_to_url(media_id)
        if resolved_url:
            char_dir = output_dir / "characters"
            char_dir.mkdir(exist_ok=True)
            img_path = char_dir / f"{char_id}_ref.png"
            
            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                img_resp = await client.get(resolved_url)
                if img_resp.status_code == 200:
                    with open(img_path, "wb") as f:
                        f.write(img_resp.content)
                    logger.info(f"   Saved: {img_path} ({len(img_resp.content) // 1024}KB)")
    except Exception as e:
        logger.warning(f"   Could not download preview: {e}")
    
    return {
        "id": char_id,
        "name": name,
        "media_id": media_id,
        "visual": visual,
    }


def update_config_yaml(media_ids: list[str]):
    """Update config.yaml with character_media_ids."""
    config_path = Path(__file__).parent / "config.yaml"
    
    if not config_path.exists():
        logger.error(f"config.yaml not found: {config_path}")
        return
    
    content = config_path.read_text(encoding="utf-8")
    
    # Replace character_media_ids line
    import re
    ids_str = json.dumps(media_ids)
    
    # Match: character_media_ids: [] or character_media_ids: ["..."]
    pattern = r'(character_media_ids:\s*)\[.*?\]'
    if re.search(pattern, content):
        new_content = re.sub(pattern, f'\\1{ids_str}', content)
    else:
        # Append under flowkit section
        new_content = content.replace(
            "  timeout: 120",
            f"  timeout: 120\n  character_media_ids: {ids_str}"
        )
    
    config_path.write_text(new_content, encoding="utf-8")
    logger.success(f"✅ Updated config.yaml with {len(media_ids)} character_media_ids")


async def main():
    parser = argparse.ArgumentParser(description="Create Character Reference Images on FlowKit")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--blueprint", type=str,
                        help="Path to blueprint.json (from generate_anime_storyboard.py)")
    group.add_argument("--series-bible", type=str,
                        help="Path to series_bible.json (for series production)")
    parser.add_argument("--no-update-config", action="store_true",
                        help="Don't auto-update config.yaml")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Custom output directory for character images")
    
    args = parser.parse_args()
    
    # Load characters from blueprint or series bible
    if args.series_bible:
        source_path = Path(args.series_bible)
        if not source_path.exists():
            logger.error(f"Series bible not found: {source_path}")
            sys.exit(1)
        with open(source_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        characters = data.get("characters", [])
        # For series, save refs alongside the bible
        output_dir = Path(args.output_dir) if args.output_dir else source_path.parent
        logger.info(f"📖 Loading characters from series bible: {source_path}")
    else:
        source_path = Path(args.blueprint)
        if not source_path.exists():
            logger.error(f"Blueprint not found: {source_path}")
            sys.exit(1)
        with open(source_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        characters = data.get("characters", [])
        output_dir = Path(args.output_dir) if args.output_dir else source_path.parent
        logger.info(f"📋 Loading characters from blueprint: {source_path}")
    
    if not characters:
        logger.error("No characters found!")
        sys.exit(1)
    
    logger.info("")
    logger.info("=" * 70)
    logger.info("🎨 CHARACTER REFERENCE GENERATION")
    logger.info("=" * 70)
    logger.info(f"   Source: {source_path}")
    logger.info(f"   Characters: {len(characters)}")
    for c in characters:
        logger.info(f"     - [{c['id']}] {c.get('name', '?')}: {c['visual'][:50]}...")
    logger.info(f"   Output: {output_dir}")
    logger.info("")
    logger.info("   Flow: Create ref image → save media_id → config.yaml")
    logger.info("   Then:  Pipeline uses media_ids → Imagen 3 character ref → seed image → Veo video")
    logger.info("=" * 70)
    
    # Initialize FlowKit service
    from pixelle_video.service import PixelleVideoCore
    core = PixelleVideoCore()
    await core.initialize()
    
    from pixelle_video.services.flowkit_media import FlowKitMediaService
    flowkit = FlowKitMediaService(core.config)
    
    if not await flowkit.check_connection():
        logger.error("FlowKit not connected! Make sure Chrome Extension is running.")
        sys.exit(1)
    
    # Generate reference images
    results = []
    media_ids = []
    
    for char in characters:
        result = await generate_character_image(flowkit, char, output_dir)
        if result:
            results.append(result)
            media_ids.append(result["media_id"])
        else:
            logger.warning(f"Failed to generate ref for {char['id']}, skipping")
    
    # Save character_refs.json
    refs_path = output_dir / "character_refs.json"
    with open(refs_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved: {refs_path}")
    
    # Update config.yaml
    if not args.no_update_config and media_ids:
        update_config_yaml(media_ids)
    
    # Summary
    logger.info("")
    logger.info("=" * 70)
    logger.success(f"🎨 CHARACTER REFERENCES CREATED!")
    logger.info("=" * 70)
    logger.info(f"  Total: {len(results)}/{len(characters)}")
    for r in results:
        logger.info(f"  [{r['id']}] {r['name']}: media_id={r['media_id'][:20]}...")
    logger.info(f"")
    logger.info(f"  📁 Refs JSON: {refs_path}")
    logger.info(f"  🖼️  Images: {output_dir / 'characters'}/")
    if not args.no_update_config:
        logger.info(f"  ⚙️  config.yaml: UPDATED with {len(media_ids)} character_media_ids")
    logger.info("")
    logger.info("  HOW IT WORKS:")
    logger.info("  1. character_media_ids → truyền vào FlowKit generate-image API")
    logger.info("  2. Google Imagen 3 dùng ảnh ref → vẽ nhân vật nhất quán trong ảnh mồi")
    logger.info("  3. Ảnh mồi → start_image_media_id → Google Veo tạo video")
    logger.info("  → Nhân vật nhất quán từ ảnh ref → ảnh mồi → video!")
    logger.info("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
