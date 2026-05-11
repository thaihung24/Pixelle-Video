import os
import re
import sys
import subprocess
import torch
import soundfile as sf
from omnivoice import OmniVoice

def parse_markdown(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    scenes = []
    # Tìm các block Scene
    blocks = re.split(r'\*\*Scene (\d+)', content)
    
    for i in range(1, len(blocks), 2):
        scene_num = int(blocks[i])
        block = blocks[i + 1]
        
        narrator_match = re.search(r'\*\*Narrator \(JP\):\*\*\s*(.+)', block)
        if narrator_match:
            narrator_text = narrator_match.group(1).strip()
            scenes.append({
                "scene": scene_num,
                "text": narrator_text
            })
    return scenes

def main():
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    
    script_path = r"C:\Users\ADMIN\Dev\tool\flowkit\input\podcast\KichBanPHIM_Suckhoe_Japan.md"
    out_dir = r"C:\Users\ADMIN\Dev\tool\flowkit\output\KichBanPHIM_Suckhoe_Japan\temp_processing"
    
    if not os.path.exists(out_dir):
        print(f"Output dir does not exist: {out_dir}")
        return

    scenes = parse_markdown(script_path)
    print(f"Found {len(scenes)} scenes in markdown.")

    print('Loading OmniVoice model...')
    model = OmniVoice.from_pretrained('k2-fsa/omnivoice', device_map='cuda' if torch.cuda.is_available() else 'cpu')
    print('Model loaded.')

    ref_audio = r"C:\Users\ADMIN\Dev\tool\flowkit\output\_shared\tts_templates\mina.WAV"
    ref_text = "私の声は誰にとっても聞きやすい落ち着い。心地よい音です"

    final_segments = []

    for s in scenes:
        scene_id = s["scene"]
        text = s["text"]
        print(f"\nProcessing Scene {scene_id}...")
        
        audio_out = os.path.join(out_dir, f"scene_{scene_id:03d}_audio_omni.wav")
        raw_video = os.path.join(out_dir, f"scene_{scene_id:03d}_raw.mp4")
        segment_out = os.path.join(out_dir, f"scene_{scene_id:03d}_final_omni.mp4")
        
        # 1. Generate audio
        if not os.path.exists(audio_out):
            try:
                audio = model.generate(text=text, ref_audio=ref_audio, ref_text=ref_text)
                sf.write(audio_out, audio[0], 24000)
                print(f"  -> Generated TTS audio: {os.path.basename(audio_out)}")
            except Exception as e:
                print(f"  -> Error generating audio for scene {scene_id}: {e}")
                continue
        else:
            print(f"  -> Audio already exists: {os.path.basename(audio_out)}")

        # 2. Merge audio + video
        if os.path.exists(raw_video) and not os.path.exists(segment_out):
            print(f"  -> Merging audio and video...")
            cmd = [
                "ffmpeg", "-y",
                "-stream_loop", "-1", "-i", raw_video,
                "-i", audio_out,
                "-shortest",
                "-c:v", "copy",
                "-c:a", "aac",
                segment_out
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"  -> Created {os.path.basename(segment_out)}")
        elif not os.path.exists(raw_video):
            print(f"  -> Error: Raw video {os.path.basename(raw_video)} not found!")
        
        if os.path.exists(segment_out):
            final_segments.append(segment_out)

    # 3. Concat all
    if final_segments:
        print("\n=================================")
        print("Concatenating all segments...")
        list_file = os.path.join(out_dir, "omni_concat_list.txt")
        with open(list_file, "w", encoding="utf-8") as f:
            for seg in final_segments:
                safe_path = seg.replace("\\", "/")
                f.write(f"file '{safe_path}'\n")
        
        final_video = os.path.join(out_dir, "FINAL_SUCKHOE_JAPAN.mp4")
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
    main()
