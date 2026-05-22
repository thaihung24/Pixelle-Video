import json
import os
import sys
import ffmpeg
from loguru import logger

def add_audio_layer(video_path: str, output_path: str, episode_key: str):
    """Adds BGM and SFX to a video based on the audio manifest."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    audio_dir = os.path.join(base_dir, "assets", "audio")
    manifest_path = os.path.join(audio_dir, "audio_manifest.json")
    
    if not os.path.exists(manifest_path):
        logger.error(f"Manifest not found: {manifest_path}")
        return
        
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
        
    ep_profiles = manifest.get("episode_profiles", {})
    if episode_key not in ep_profiles:
        logger.error(f"Episode {episode_key} not found in manifest!")
        return
        
    profile = ep_profiles[episode_key]
    primary_bgm_keys = profile.get("primary_bgm", [])
    ambient_sfx_keys = profile.get("ambient_sfx", [])
    
    logger.info(f"Applying audio layer for {episode_key}")
    logger.info(f"BGM Keys: {primary_bgm_keys}")
    logger.info(f"SFX Keys: {ambient_sfx_keys}")
    
    # Helper to find file paths
    def find_audio_path(basename):
        for root, dirs, files in os.walk(audio_dir):
            for file in files:
                if file.startswith(basename) and file.endswith(('.mp3', '.wav')):
                    return os.path.join(root, file)
        return None

    # Pick the first available BGM and SFX for simplicity
    bgm_path = None
    for k in primary_bgm_keys:
        path = find_audio_path(k)
        if path:
            bgm_path = path
            break
            
    sfx_path = None
    for k in ambient_sfx_keys:
        path = find_audio_path(k)
        if path:
            sfx_path = path
            break

    inputs = [ffmpeg.input(video_path)]
    audio_filters = []
    
    # Original video audio (voiceover)
    audio_filters.append(inputs[0].audio.filter('volume', 1.0))
    
    if bgm_path:
        logger.info(f"Found BGM: {bgm_path}")
        # Loop BGM infinitely
        bgm_in = ffmpeg.input(bgm_path, stream_loop=-1)
        inputs.append(bgm_in)
        # Volume 0.15 for BGM
        audio_filters.append(bgm_in.audio.filter('volume', 0.15))
        
    if sfx_path:
        logger.info(f"Found SFX: {sfx_path}")
        # Loop SFX infinitely
        sfx_in = ffmpeg.input(sfx_path, stream_loop=-1)
        inputs.append(sfx_in)
        # Volume 0.08 for Ambient SFX
        audio_filters.append(sfx_in.audio.filter('volume', 0.08))
        
    if len(audio_filters) > 1:
        # Mix all audio streams
        mixed_audio = ffmpeg.filter(
            audio_filters,
            'amix',
            inputs=len(audio_filters),
            duration='first' # matches video length
        )
    else:
        mixed_audio = audio_filters[0]
        
    logger.info(f"Rendering final mix to {output_path}...")
    try:
        (
            ffmpeg
            .output(
                inputs[0].video, 
                mixed_audio, 
                output_path, 
                vcodec='copy', 
                acodec='aac', 
                audio_bitrate='192k'
            )
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
        logger.success(f"Successfully mixed audio! Saved to: {output_path}")
    except ffmpeg.Error as e:
        logger.error(f"FFmpeg error: {e.stderr.decode('utf-8') if e.stderr else str(e)}")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python add_audio_layer.py <input_video.mp4> <output_video.mp4> <episode_key>")
        sys.exit(1)
        
    add_audio_layer(sys.argv[1], sys.argv[2], sys.argv[3])
