import os
import re
import sys
import asyncio
import subprocess
from pathlib import Path

# Adjust path so we can import pixelle_video
sys.path.insert(0, os.path.abspath("."))
from pixelle_video.services.frame_html import HTMLFrameGenerator

def parse_markdown(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    scenes = []
    blocks = re.split(r'\*\*Scene (\d+)', content)
    
    for i in range(1, len(blocks), 2):
        scene_num = int(blocks[i])
        block = blocks[i + 1]
        
        text_match = re.search(r'\*\*Narrator \(JP\):\*\*\s*(.+)', block)
        sub_match = re.search(r'\*\*Sub \(VN\):\*\*\s*(.+)', block)
        
        text = text_match.group(1).strip() if text_match else ""
        sub = sub_match.group(1).strip() if sub_match else ""
        
        scenes.append({
            "scene": scene_num,
            "text": text,
            "sub": sub
        })
    return scenes

async def main():
    script_path = r"C:\Users\ADMIN\Dev\tool\flowkit\input\podcast\KichBanPHIM_Suckhoe_Japan.md"
    out_dir = r"C:\Users\ADMIN\Dev\tool\flowkit\output\KichBanPHIM_Suckhoe_Japan\temp_processing"
    
    if not os.path.exists(out_dir):
        print(f"Output dir does not exist: {out_dir}")
        return

    scenes = parse_markdown(script_path)
    print(f"Found {len(scenes)} scenes in markdown.")

    template_path = os.path.join(os.getcwd(), "templates", "1920x1080", "video_youtube.html")
    print(f"Loading template: {template_path}")
    generator = HTMLFrameGenerator(template_path)

    topic = "日本人の長寿の秘訣" # from the markdown title
    ext_params = {
        "author": "@sukoyaka.life1",
        "describe": "健康長寿の知恵",
        "brand": "健康長寿の知恵",
        "sub": ""
    }

    final_segments = []

    for s in scenes:
        scene_id = s["scene"]
        text = s["text"]
        ext_params["sub"] = "" # User requested no vietnamese sub
        
        print(f"\n🎬 Composing Scene {scene_id}...")
        
        raw_video = os.path.join(out_dir, f"scene_{scene_id:03d}_raw.mp4")
        audio_in = os.path.join(out_dir, f"scene_{scene_id:03d}_audio_padded.mp3")
        composed_img = os.path.join(out_dir, f"scene_{scene_id:03d}_composed.png")
        segment_out = os.path.join(out_dir, f"scene_{scene_id:03d}_final_new.mp4")
        
        if not os.path.exists(raw_video):
            print(f"  -> Missing raw video: {os.path.basename(raw_video)}")
            continue
            
        # 1. Generate composed.png using HTMLFrameGenerator
        if not os.path.exists(composed_img):
            print(f"  -> Rendering HTML to {os.path.basename(composed_img)}...")
            await generator.generate_frame(
                title=topic,
                text=text,
                image=Path(raw_video).as_uri(), # Using the video as background in HTML
                ext=ext_params,
                output_path=composed_img
            )

        # 2. Merge composed.png + raw.mp4 + audio.mp3
        print(f"  -> Merging into {os.path.basename(segment_out)}...")
        cmd = [
            "ffmpeg", "-y",
            "-i", raw_video,
            "-i", composed_img,
            "-i", audio_in,
            "-filter_complex", "[1:v]scale=1280:720[img];[0:v][img]overlay=0:0[outv]",
            "-map", "[outv]",
            "-map", "2:a",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-shortest",
            segment_out
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        if os.path.exists(segment_out):
            final_segments.append(segment_out)

    await generator.close_browser()

    # 3. Concat all
    if final_segments:
        print("\n=================================")
        print("Concatenating all segments...")
        list_file = os.path.join(out_dir, "new_concat_list.txt")
        with open(list_file, "w", encoding="utf-8") as f:
            for seg in final_segments:
                safe_path = seg.replace("\\", "/")
                f.write(f"file '{safe_path}'\n")
        
        final_video = os.path.join(out_dir, "FINAL_SUCKHOE_JAPAN_COMPOSED.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file,
            "-c", "copy",
            final_video
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"SUCCESS: {final_video}")

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    asyncio.run(main())
