"""
Smart Audio Mixer — Per-scene BGM + SFX mapping based on scene content.

Strategy:
1. Read each scene's image_prompt and narration from script.json
2. Match keywords → pick appropriate BGM and SFX per scene
3. Trim/loop each audio to match exact scene duration
4. Concatenate all per-scene BGM chunks → full BGM timeline
5. Concatenate all per-scene SFX chunks → full SFX timeline
6. Mix final.mp4 + BGM timeline + SFX timeline → final_audio.mp4
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
from loguru import logger


# ─────────────────────────────────────────────
# Keyword → (bgm_key, sfx_key) mapping table
# Keywords are matched against image_prompt + narration (case-insensitive)
# More specific rules first (order matters)
# ─────────────────────────────────────────────
KEYWORD_AUDIO_MAP = [
    # Rain / Water scenes
    (["rain", "rainy", "drizzle", "shower", "umbrella"], "rainy_tatami", "rain_light"),
    (["stream", "brook", "creek", "waterfall", "flowing water"], "water_meditation", "stream_gentle"),
    (["onsen", "hot spring", "mineral bath", "bath"], "night_onsen", "stream_gentle"),
    (["pond", "lake", "river", "water"], "water_meditation", "stream_gentle"),

    # Kitchen / Cooking scenes
    (["chop", "cutting", "knife", "slice", "dice", "mince", "daikon", "carrot", "vegetable", "ingredient"], "cooking_time", "chopping_veg"),
    (["sizzle", "fry", "grilling", "pan-fry", "grilled fish", "yakizakana", "teriyaki"], "cooking_time", "sizzling_pan"),
    (["simmering", "boiling", "soup", "broth", "miso", "dashi", "pot", "stew", "nabe"], "cooking_time", "soup_simmering"),
    (["pour", "tea", "matcha", "green tea", "gyokuro", "sencha", "teapot", "teacup", "ceremony"], "afternoon_tea", "pour_tea"),
    (["cook", "kitchen", "prepare", "meal", "breakfast", "lunch", "dinner", "bento", "obento"], "cooking_time", "chopping_veg"),

    # Outdoor / Nature scenes
    (["sakura", "cherry blossom", "petal", "hanami"], "sakura_petals", "birds_morning"),
    (["cicada", "semi", "summer heat", "midsummer"], "zen_study", "cicadas_summer"),
    (["garden", "pruning", "weeding", "planting", "flower bed", "harvest", "vegetable patch"], "garden_breeze", "birds_morning"),
    (["market", "morning market", "vendor", "stall", "shopping", "supermarket", "grocery"], "market_morning", "market_ambience"),
    (["bicycle", "cycling", "bike", "mamachari"], "walking_path", "bicycle_bell"),
    (["walk", "stroll", "path", "trail", "road", "promenade", "park"], "walking_path", "birds_morning"),
    (["bamboo", "bamboo grove", "bamboo forest"], "bamboo_forest", "birds_morning"),
    (["bird", "birdsong", "sparrow", "warbler", "uguisu", "crow"], "morning_light", "birds_morning"),
    (["morning", "sunrise", "dawn", "early morning", "waking up", "good morning"], "morning_light", "birds_morning"),
    (["evening", "sunset", "dusk", "twilight", "golden hour"], "evening_reflection", "wind_chime"),

    # Indoor / Traditional scenes
    (["wind chime", "furin", "chime", "breeze through window"], "afternoon_tea", "wind_chime"),
    (["shoji", "sliding door", "tatami", "zabuton", "chabudai", "kotatsu"], "afternoon_tea", "sliding_door"),
    (["fire", "hearth", "irori", "fireplace", "wood stove", "crackling"], "evening_reflection", "fire_crackling"),
    (["tea ceremony", "chado", "chanoyu", "matcha bowl", "chakin"], "autumn_temple", "pour_tea"),

    # Temple / Zen / Meditation scenes
    (["temple", "shrine", "jinja", "torii", "incense", "prayer", "meditat", "zen", "zazen", "monk"], "autumn_temple", "wind_chime"),
    (["autumn", "fall", "maple", "momiji", "red leaves", "koyo", "leaves falling"], "autumn_temple", "wind_chime"),

    # Social / Family scenes
    (["family", "grandmother", "grandchild", "grandparent", "together", "gathering", "reunion"], "family_table", "wind_chime"),
    (["friend", "neighbor", "community", "group", "elderly", "together"], "old_friends", "wind_chime"),
    (["laugh", "smile", "joy", "happy", "cheerful", "fun"], "simple_happiness", "wind_chime"),

    # Memory / Reflection scenes
    (["memory", "flashback", "recall", "reminisce", "past", "nostalgia", "old photo"], "memory_lane", None),
    (["reflect", "contemplat", "ponder", "think", "wisdom", "lesson", "philosophy"], "gentle_wisdom", "wind_chime"),

    # Hope / Inspiration scenes
    (["hope", "future", "dream", "inspire", "aspire", "goal", "purpose", "ikigai"], "hope_and_warmth", None),
    (["gratitude", "thank", "appreciation", "blessing", "grateful"], "life_is_beautiful", "wind_chime"),
    (["season", "seasonal", "time passes", "year", "change"], "seasons_passing", "wind_chime"),
]

# Default fallback: used when no keyword matches
DEFAULT_BGM = "main_theme"
DEFAULT_SFX = None


def _find_audio_file(audio_dir: str, basename: str) -> Optional[str]:
    """Find audio file by basename (without extension) in the audio library."""
    for root, _, files in os.walk(audio_dir):
        for f in files:
            if os.path.splitext(f)[0] == basename and f.endswith(('.mp3', '.wav')):
                return os.path.join(root, f)
    return None


def _match_scene_audio(prompt: str, narration: str, audio_dir: str) -> tuple[Optional[str], Optional[str]]:
    """
    Match scene content to BGM and SFX files.
    Returns (bgm_path, sfx_path) — either can be None if no match or file not found.
    """
    text = f"{prompt} {narration}".lower()

    matched_bgm_key = DEFAULT_BGM
    matched_sfx_key = DEFAULT_SFX

    for keywords, bgm_key, sfx_key in KEYWORD_AUDIO_MAP:
        if any(kw in text for kw in keywords):
            matched_bgm_key = bgm_key
            matched_sfx_key = sfx_key
            logger.debug(f"    Matched keywords for BGM={bgm_key}, SFX={sfx_key}")
            break  # First match wins (most specific first)

    bgm_path = _find_audio_file(audio_dir, matched_bgm_key) if matched_bgm_key else None
    sfx_path = _find_audio_file(audio_dir, matched_sfx_key) if matched_sfx_key else None

    return bgm_path, sfx_path


def _get_audio_duration(path: str) -> float:
    """Get duration of an audio/video file using ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True
    )
    try:
        return float(result.stdout.strip())
    except Exception:
        return 5.0


def _trim_loop_audio(src: str, duration: float, output: str) -> bool:
    """
    Trim or loop an audio file to exactly `duration` seconds.
    Uses ffmpeg aloop filter for seamless looping.
    """
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", src,
        "-t", str(duration),
        "-af", f"afade=t=out:st={max(0, duration - 0.3):.3f}:d=0.3",
        "-acodec", "pcm_s16le",
        "-ar", "44100",
        "-ac", "2",
        output
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0 and os.path.exists(output)


def _concat_audio_files(file_list: list[str], output: str) -> bool:
    """Concatenate multiple WAV files into one using ffmpeg concat demuxer."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        for fp in file_list:
            f.write(f"file '{fp.replace(chr(92), '/')}'\n")
        list_file = f.name

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-acodec", "pcm_s16le",
        "-ar", "44100",
        "-ac", "2",
        output
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    os.unlink(list_file)
    return result.returncode == 0 and os.path.exists(output)


def _mix_video_with_audio_tracks(
    video_path: str,
    bgm_path: Optional[str],
    sfx_path: Optional[str],
    transition_sfx_path: Optional[str],
    transition_offsets: Optional[list[float]],
    output_path: str,
    bgm_volume: float = 0.15,
    sfx_volume: float = 0.08,
    transition_volume: float = 0.18,
    duck_factor: float = 0.35,
    duck_window_s: float = 0.35,
) -> bool:
    """Mix video's original audio with BGM and SFX timelines."""
    cmd = ["ffmpeg", "-y", "-i", video_path]
    audio_inputs = []
    filter_parts = []
    n_inputs = 1  # video is input 0

    if bgm_path:
        cmd += ["-i", bgm_path]
        audio_inputs.append((n_inputs, bgm_volume))
        n_inputs += 1

    if sfx_path:
        cmd += ["-i", sfx_path]
        audio_inputs.append((n_inputs, sfx_volume))
        n_inputs += 1

    transition_input_index: Optional[int] = None
    if transition_sfx_path and transition_offsets:
        # Add the transition SFX as a separate input; we'll delay it per boundary in filter_complex.
        cmd += ["-i", transition_sfx_path]
        transition_input_index = n_inputs
        n_inputs += 1

    # Build filter graph.
    # Keep voice (0:a) at full level, add BGM/SFX, and optionally insert transition SFX at offsets.
    filter_parts.append("[0:a]volume=1.0[va]")
    bgm_label = None
    sfx_label = None

    # Assign labels deterministically by input index order.
    for idx, (inp_idx, vol) in enumerate(audio_inputs):
        label = f"[a{idx}]"
        filter_parts.append(f"[{inp_idx}:a]volume={vol}{label}")
        if bgm_path and bgm_label is None:
            bgm_label = label
        elif sfx_path and sfx_label is None and (label != bgm_label):
            sfx_label = label

    bed_inputs = ["[va]"]
    if bgm_label:
        bed_inputs.append(bgm_label)
    if sfx_label:
        bed_inputs.append(sfx_label)

    bed_mix = "".join(bed_inputs)
    filter_parts.append(f"{bed_mix}amix=inputs={len(bed_inputs)}:duration=first:normalize=0[bed0]")

    if transition_input_index is not None and transition_offsets:
        # Create one delayed instance per boundary, then mix them into a single transition bus.
        # Example: [N:a]asplit=6[t0][t1]...; [t0]adelay=... [td0]; ...; [td0][td1]...amix=...
        n_tr = len(transition_offsets)
        split_labels = "".join([f"[t{i}]" for i in range(n_tr)])
        # Normalize transition input format before splitting/delaying to avoid channel/layout quirks.
        filter_parts.append(
            f"[{transition_input_index}:a]volume={transition_volume},aresample=48000,"
            f"aformat=sample_rates=48000:channel_layouts=stereo,asplit={n_tr}{split_labels}"
        )
        delayed_labels = []
        for i, t in enumerate(transition_offsets):
            delay_ms = int(max(0.0, float(t)) * 1000.0)
            out_lbl = f"[td{i}]"
            # Small fade-in to avoid clicks.
            # NOTE: Do NOT apply a fade-out without an explicit start time (st),
            # otherwise it will fade out immediately at t=0 and effectively mute the SFX.
            # Use adelay with all=1 so it applies cleanly regardless of channel count.
            filter_parts.append(f"[t{i}]adelay={delay_ms}:all=1,afade=t=in:d=0.01{out_lbl}")
            delayed_labels.append(out_lbl)

        tr_mix_inputs = "".join(delayed_labels)
        # Important: use longest here, otherwise output duration is truncated to the first delayed SFX.
        filter_parts.append(f"{tr_mix_inputs}amix=inputs={len(delayed_labels)}:duration=longest:normalize=0[tr]")

        # Deterministic ducking at boundaries (easier to make audible than pure sidechain on short SFX).
        # Lower the entire bed for a short window at each transition offset.
        try:
            duck_factor_f = float(duck_factor)
        except Exception:
            duck_factor_f = 0.35
        duck_factor_f = max(0.05, min(1.0, duck_factor_f))

        try:
            win = float(duck_window_s)
        except Exception:
            win = 0.35
        win = max(0.05, min(2.0, win))

        terms = [f"between(t\\,{t:.3f}\\,{t+win:.3f})" for t in transition_offsets]
        cond = "+".join(terms) if terms else "0"
        duck_expr = f"if(gt({cond}\\,0)\\,{duck_factor_f:.3f}\\,1)"
        filter_parts.append(f"[bed0]volume='{duck_expr}'[bed]")

        filter_parts.append("[bed][tr]amix=inputs=2:duration=first:normalize=0[mix]")
    else:
        filter_parts.append("[bed0]anull[mix]")

    filter_parts.append(
        "[mix]alimiter=limit=0.98,aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo[aout]"
    )
    filter_complex = ";".join(filter_parts)

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[aout]",
        "-vcodec", "copy",
        "-acodec", "aac",
        "-ar", "48000",
        "-ac", "2",
        "-b:a", "192k",
        output_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"FFmpeg mix error: {result.stderr[-500:]}")
    return result.returncode == 0 and os.path.exists(output_path)


def mix_smart_audio(
    final_video_path: str,
    output_path: str,
    frames_dir: str,
    script_data: dict,
    audio_dir: str,
    bgm_volume: float = 0.15,
    sfx_volume: float = 0.08,
    transition_sfx_path: str = "",
    transition_sfx_volume: float = 0.18,
    transition_duck_factor: float = 0.20,
    transition_duck_window_s: float = 0.50,
    total_scenes: int = 0,
) -> Optional[str]:
    """
    Main entry point: per-scene smart audio mixing.

    Args:
        final_video_path: Path to the concatenated video (final.mp4)
        output_path: Output path for video with audio layer (final_audio.mp4)
        frames_dir: Path to the frames/ directory
        script_data: Loaded script.json dict
        audio_dir: Root path to assets/audio/
        bgm_volume: BGM volume (0.0–1.0)
        sfx_volume: SFX ambient volume (0.0–1.0)
        total_scenes: Number of scenes

    Returns:
        output_path on success, None on failure
    """
    narrations = script_data.get("narrations", [])
    image_prompts = script_data.get("video_prompts", script_data.get("image_prompts", []))

    # Optional transition SFX (inserted between scenes).
    # Prefer explicit args from runtime (project.json via resume_pipeline).
    if not transition_sfx_path:
        project_params = (script_data.get("project") or {}).get("template_params") or {}
        transition_sfx_path = project_params.get("transition_sfx_path") or ""
        transition_sfx_volume = float(project_params.get("transition_sfx_volume") or transition_sfx_volume)
        transition_duck_factor = float(project_params.get("transition_duck_factor") or transition_duck_factor)
        transition_duck_window_s = float(project_params.get("transition_duck_window_s") or transition_duck_window_s)

    if not total_scenes:
        total_scenes = len(narrations)

    logger.info(f"Smart Audio Mixer: processing {total_scenes} scenes")

    bgm_chunks = []
    sfx_chunks = []
    tmp_files = []

    with tempfile.TemporaryDirectory() as tmpdir:
        scene_durations: list[float] = []
        for i in range(total_scenes):
            frame_num = i + 1
            prefix = f"{frame_num:02d}"
            narration = narrations[i] if i < len(narrations) else ""
            prompt = image_prompts[i] if i < len(image_prompts) else ""

            # Lấy thời lượng chuẩn xác từ file segment (video đã ghép) thay vì audio thô
            segment_mp4 = os.path.join(frames_dir, f"{prefix}_segment.mp4")
            if os.path.exists(segment_mp4):
                duration = _get_audio_duration(segment_mp4)
            else:
                # Fallback nếu không có segment (dù bình thường chắc chắn có)
                audio_wav = os.path.join(frames_dir, f"{prefix}_audio.wav")
                audio_mp3 = os.path.join(frames_dir, f"{prefix}_audio.mp3")
                scene_audio = audio_wav if os.path.exists(audio_wav) else audio_mp3
                duration = _get_audio_duration(scene_audio) if os.path.exists(scene_audio) else 5.0

            scene_durations.append(duration)

            # Match audio for this scene
            bgm_path, sfx_path = _match_scene_audio(prompt, narration, audio_dir)

            logger.debug(f"  Scene {frame_num}: dur={duration:.1f}s | BGM={Path(bgm_path).stem if bgm_path else 'none'} | SFX={Path(sfx_path).stem if sfx_path else 'none'}")

            # Trim/loop BGM for this scene
            if bgm_path:
                bgm_chunk = os.path.join(tmpdir, f"bgm_{prefix}.wav")
                if _trim_loop_audio(bgm_path, duration, bgm_chunk):
                    bgm_chunks.append(bgm_chunk)
                else:
                    # Fallback: silence
                    bgm_chunks.append(None)
                    logger.warning(f"  Scene {frame_num}: failed to trim BGM, using silence")
            else:
                bgm_chunks.append(None)

            # Trim/loop SFX for this scene
            if sfx_path:
                sfx_chunk = os.path.join(tmpdir, f"sfx_{prefix}.wav")
                if _trim_loop_audio(sfx_path, duration, sfx_chunk):
                    sfx_chunks.append(sfx_chunk)
                else:
                    sfx_chunks.append(None)
            else:
                sfx_chunks.append(None)

        # Generate silence for missing chunks
        silence_cache = {}
        def _get_silence(dur: float) -> str:
            key = round(dur, 1)
            if key not in silence_cache:
                sil = os.path.join(tmpdir, f"silence_{key}.wav")
                subprocess.run([
                    "ffmpeg", "-y", "-f", "lavfi",
                    "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
                    "-t", str(dur), "-acodec", "pcm_s16le", sil
                ], capture_output=True)
                silence_cache[key] = sil
            return silence_cache[key]

        # Fill None chunks with appropriate silence durations
        all_bgm_valid = []
        all_sfx_valid = []
        for i in range(total_scenes):
            frame_num = i + 1
            prefix = f"{frame_num:02d}"
            
            segment_mp4 = os.path.join(frames_dir, f"{prefix}_segment.mp4")
            if os.path.exists(segment_mp4):
                dur = _get_audio_duration(segment_mp4)
            else:
                audio_wav = os.path.join(frames_dir, f"{prefix}_audio.wav")
                audio_mp3 = os.path.join(frames_dir, f"{prefix}_audio.mp3")
                scene_audio = audio_wav if os.path.exists(audio_wav) else audio_mp3
                dur = _get_audio_duration(scene_audio) if os.path.exists(scene_audio) else 5.0

            all_bgm_valid.append(bgm_chunks[i] if bgm_chunks[i] else _get_silence(dur))
            all_sfx_valid.append(sfx_chunks[i] if sfx_chunks[i] else _get_silence(dur))

        # Concatenate BGM and SFX timelines
        bgm_timeline = os.path.join(tmpdir, "bgm_timeline.wav")
        sfx_timeline = os.path.join(tmpdir, "sfx_timeline.wav")
        # We now insert transition SFX directly in the final mix filter graph,
        # so no need to pre-render a transition timeline WAV.

        logger.info("  Concatenating BGM timeline...")
        has_bgm = _concat_audio_files(all_bgm_valid, bgm_timeline)

        logger.info("  Concatenating SFX timeline...")
        has_sfx = _concat_audio_files(all_sfx_valid, sfx_timeline)

        # Build transition offsets (scene boundaries)
        transition_offsets: list[float] = []
        if transition_sfx_path and total_scenes > 1:
            logger.info(f"  Transition SFX enabled: path='{transition_sfx_path}' vol={transition_sfx_volume}")
            # Resolve relative path against repo root (CWD) first, then audio_dir.
            cand = transition_sfx_path
            if not os.path.isabs(cand):
                cand_abs = os.path.abspath(cand)
                if os.path.exists(cand_abs):
                    cand = cand_abs
                else:
                    cand2 = os.path.join(audio_dir, os.path.basename(transition_sfx_path))
                    if os.path.exists(cand2):
                        cand = cand2

            if os.path.exists(cand):
                logger.info(f"  Transition SFX resolved: {cand}")
                acc = 0.0
                for d in scene_durations[:-1]:
                    acc += float(d)
                    transition_offsets.append(acc)
                logger.info(f"  Transition boundaries: {len(transition_offsets)} at {transition_offsets[:3]}{'...' if len(transition_offsets) > 3 else ''}")
                transition_sfx_path = cand
            else:
                logger.warning(f"Transition SFX not found: {transition_sfx_path}")
                transition_sfx_path = ""

        if not has_bgm and not has_sfx:
            logger.warning("  Both BGM and SFX timelines failed. Skipping audio layer.")
            return None

        # Final mix: video + BGM timeline + SFX timeline
        logger.info("  Mixing final video with audio layer...")
        success = _mix_video_with_audio_tracks(
            video_path=final_video_path,
            bgm_path=bgm_timeline if has_bgm else None,
            sfx_path=sfx_timeline if has_sfx else None,
            transition_sfx_path=transition_sfx_path if transition_offsets else None,
            transition_offsets=transition_offsets if transition_offsets else None,
            output_path=output_path,
            bgm_volume=bgm_volume,
            sfx_volume=sfx_volume,
            transition_volume=transition_sfx_volume,
            duck_factor=transition_duck_factor,
            duck_window_s=transition_duck_window_s,
        )

        if success:
            logger.success(f"  Smart audio mix complete: {output_path}")
            return output_path
        else:
            logger.error("  Smart audio mix failed.")
            return None
