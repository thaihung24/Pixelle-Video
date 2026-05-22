"""
style_registry.py — Cinematic Style Layer System for Pixelle-Video

Architecture:
  GLOBAL (always injected): art direction, rendering style, anime identity, anti-drift constraints
  SCENE-SPECIFIC (auto-detected): lighting, mood, color palette, cinematography

Usage:
    from pixelle_video.prompts.style_registry import build_scene_style
    
    style_block = build_scene_style(
        act=scene["act"],
        setting=scene["setting"],
        scene_brief=scene.get("scene_brief", ""),
    )
    final_prompt = f"{style_block} {base_prompt}"
"""

import re
from typing import Optional


# ===========================================================================
# LAYER 1: GLOBAL STYLE BIBLE (inject into every scene, always)
# ===========================================================================
# Giữ nguyên: art direction, rendering style, anime identity, anti-drift
GLOBAL_STYLE = (
    "anime cel-shaded rendering, hand-painted cozy anime film background, "
    "soft watercolor background painting, polished anime linework, "
    "subtle soft shading, atmospheric perspective, "
    "production-quality anime visual development art, "
    "consistent recurring art direction, cohesive visual continuity"
)

# ===========================================================================
# LAYER 2: NEGATIVE STYLE CONSTRAINTS (inject into every scene, always)
# ===========================================================================
# Ngắn, mạnh, không verbose
NEGATIVE_STYLE = (
    "no photorealism, no hyperrealism, no CGI, no 3D rendering, "
    "no Pixar, no Unreal Engine, no glossy surfaces, "
    "no cyberpunk, no neon lighting, no futuristic elements, "
    "no western cartoon style, no split-screen, no transitions, "
    "no montage, no before-and-after layout, no time-lapse"
)

# ===========================================================================
# LAYER 3: LIGHTING PRESETS (scene-specific)
# ===========================================================================
LIGHTING = {
    "golden_hour": (
        "golden-hour sunlight, soft volumetric light rays, "
        "warm amber glow, long soft shadows"
    ),
    "morning": (
        "soft morning light, cool white daylight, gentle diffused illumination, "
        "dew-fresh atmosphere, faint mist"
    ),
    "morning_mist": (
        "dawn mist, pale cool blue-green light, fog clinging to surfaces, "
        "silhouettes emerging from haze, ethereal and quiet"
    ),
    "bright_daylight": (
        "bright midday daylight, high-key natural lighting, "
        "crisp shadows, clean and energetic"
    ),
    "clinical_light": (
        "bright neutral medical lighting, clean white illumination, "
        "no harsh shadows, professional and informative atmosphere"
    ),
    "rainy_evening": (
        "rainy afternoon light, diffused grey-blue overcast, "
        "wet reflections on surfaces, soft moody ambient light"
    ),
    "sunset": (
        "late afternoon sunset, warm rose and amber tones, "
        "long horizontal shadows, soft golden rim light"
    ),
    "dusk": (
        "dusk twilight, deep blue-purple sky, soft warm interior lights "
        "contrasting cool exterior, transitional liminal feeling"
    ),
    "moonlight": (
        "cool moonlit night, silver-blue ambient light, "
        "deep soft shadows, quiet and still atmosphere"
    ),
    "indoor_warm": (
        "warm indoor lamp light, cozy incandescent glow, "
        "soft shadow pools, intimate and sheltered"
    ),
    "fireplace": (
        "flickering fireplace light, deep warm amber and orange, "
        "dancing shadows on walls, radiant core warmth"
    ),
    "dramatic_contrast": (
        "high-contrast dramatic lighting, strong chiaroscuro, "
        "deep shadows and bright highlights, emotional and cinematic"
    ),
}

# ===========================================================================
# LAYER 4: MOOD PRESETS (scene-specific)
# ===========================================================================
MOOD = {
    "nostalgic": (
        "nostalgic healing-anime mood, emotionally warm storytelling, "
        "gentle contemplative pacing"
    ),
    "calm": (
        "calm, serene, peaceful atmosphere, unhurried and meditative"
    ),
    "lively": (
        "lively, energetic, joyful atmosphere, communal warmth and vitality"
    ),
    "melancholic": (
        "quietly melancholic, reflective and bittersweet, "
        "soft emotional weight"
    ),
    "spiritual": (
        "spiritual, sacred stillness, reverent and deeply peaceful, "
        "sense of something greater"
    ),
    "hopeful": (
        "hopeful, gently uplifting, forward-looking warmth, "
        "quiet sense of possibility"
    ),
    "clinical": (
        "objective, educational, calm and trustworthy, "
        "scientific precision with human warmth"
    ),
    "cozy": (
        "cozy, intimate, sheltered warmth, lived-in comfort"
    ),
    "dramatic": (
        "emotionally heightened, quietly dramatic, "
        "charged atmosphere with restrained tension"
    ),
    "wabi_sabi": (
        "wabi-sabi aesthetic, finding beauty in impermanence and simplicity, "
        "quiet acceptance and present-moment awareness"
    ),
}

# ===========================================================================
# LAYER 5: CAMERA GRAMMAR (scene-specific)
# ===========================================================================
CAMERA = {
    "wide_establishing": (
        "wide establishing shot, slow contemplative camera drift, "
        "full environment visible, cinematic scope"
    ),
    "medium_shot": (
        "medium shot, steady grounded framing, "
        "character and environment in balance"
    ),
    "close_up": (
        "close-up shot, slow gentle push-in, "
        "emotional intimacy, focused expression detail"
    ),
    "extreme_close_up": (
        "extreme close-up, macro detail, "
        "texture and fine detail in full focus"
    ),
    "tracking": (
        "slow tracking shot, smooth continuous lateral movement, "
        "following action with steady energy"
    ),
    "overhead": (
        "overhead god's-eye view, top-down composition, "
        "geometric and deliberate framing"
    ),
    "low_angle": (
        "low-angle shot, upward-looking camera, "
        "subjects feel strong and monumental"
    ),
    "aerial": (
        "aerial wide shot, slow crane-up or drone descent, "
        "landscape scale and freedom"
    ),
    "handheld": (
        "gentle handheld drift, intimate naturalistic movement, "
        "alive and present feeling"
    ),
    "orbit": (
        "slow orbiting shot, camera circles subject smoothly, "
        "360-degree revelation of detail"
    ),
}

# ===========================================================================
# LAYER 6: COLOR PALETTE PRESETS (scene-specific)
# ===========================================================================
COLOR_PALETTE = {
    "warm_natural": (
        "warm cedar brown, moss green, soft sky blue, "
        "muted natural saturation, creamy sunlight highlights"
    ),
    "cool_mist": (
        "cool pale blue, silver grey, faint lavender, "
        "low saturation, atmospheric haze tones"
    ),
    "clinical_neutral": (
        "clean white, light grey, pale teal accent, "
        "neutral medical palette, crisp and clear"
    ),
    "autumn_harvest": (
        "deep amber, burnt sienna, ochre gold, "
        "dark mossy green, rich seasonal warmth"
    ),
    "winter_blue": (
        "cold steel blue, deep grey, icy white, "
        "warm hearth amber as accent, contrast of cold exterior and warm interior"
    ),
    "spring_fresh": (
        "bright fresh green, cherry blossom pale pink, "
        "clear sky blue, white light, vibrant and energizing"
    ),
    "summer_vivid": (
        "saturated emerald green, electric blue sky, "
        "cool ice tones, deep cool shadow, refreshing contrast"
    ),
    "twilight_rose": (
        "rose gold, warm lavender, deep indigo sky, "
        "soft amber, transitional palette of ending and reflection"
    ),
    "dramatic_dark": (
        "deep shadow, high-contrast warm highlights, "
        "rich dark tones with golden or amber accent"
    ),
}


# ===========================================================================
# AUTO-DETECTION RULES
# ===========================================================================
def _detect_from_setting(setting: str) -> dict:
    """Detect lighting, mood, camera, palette from setting text."""
    s = setting.lower()
    result = {}

    # --- Lighting ---
    if any(x in s for x in ["sunrise", "golden light", "golden hour", "warm light hitting"]):
        result["lighting"] = "golden_hour"
    elif any(x in s for x in ["morning mist", "mist clinging", "dawn"]):
        result["lighting"] = "morning_mist"
    elif any(x in s for x in ["morning", "clear sky", "bright morning", "sunlit"]):
        result["lighting"] = "morning"
    elif any(x in s for x in ["bright", "modern", "clinical", "infographic", "diagram", "chart", "laboratory", "digital", "microscop"]):
        result["lighting"] = "clinical_light"
    elif any(x in s for x in ["rainy", "rain", "overcast"]):
        result["lighting"] = "rainy_evening"
    elif any(x in s for x in ["sunset", "sun setting"]):
        result["lighting"] = "sunset"
    elif any(x in s for x in ["dusk", "twilight"]):
        result["lighting"] = "dusk"
    elif any(x in s for x in ["night", "lamp", "heater", "indoor"]):
        result["lighting"] = "indoor_warm"
    elif any(x in s for x in ["fireplace", "fire"]):
        result["lighting"] = "fireplace"
    elif any(x in s for x in ["dramatic", "contrast"]):
        result["lighting"] = "dramatic_contrast"
    else:
        result["lighting"] = "morning"  # default

    # --- Mood ---
    if any(x in s for x in ["zen", "shrine", "temple", "prayer", "meditat"]):
        result["mood"] = "spiritual"
    elif any(x in s for x in ["clinic", "medical", "laboratory", "microscop", "diagram", "chart", "infographic", "digital"]):
        result["mood"] = "clinical"
    elif any(x in s for x in ["market", "festival", "group", "community", "laughing", "lively"]):
        result["mood"] = "lively"
    elif any(x in s for x in ["rainy", "winter", "dim", "fireplace"]):
        result["mood"] = "cozy"
    elif any(x in s for x in ["sunset", "dusk", "lookout", "panoramic", "peaceful"]):
        result["mood"] = "nostalgic"
    elif any(x in s for x in ["night", "packing", "final"]):
        result["mood"] = "wabi_sabi"
    else:
        result["mood"] = "calm"

    # --- Camera ---
    if any(x in s for x in ["close-up", "extreme close", "close up", "macro"]):
        result["camera"] = "close_up"
    elif any(x in s for x in ["panoramic", "mountain", "village", "countryside", "landscape", "sky"]):
        result["camera"] = "aerial"
    elif any(x in s for x in ["overhead", "top-down", "top down"]):
        result["camera"] = "overhead"
    elif any(x in s for x in ["tracking", "follows", "market", "garden", "walking"]):
        result["camera"] = "tracking"
    else:
        result["camera"] = "medium_shot"

    # --- Color Palette ---
    if any(x in s for x in ["autumn", "mushroom", "chestnut", "harvest"]):
        result["palette"] = "autumn_harvest"
    elif any(x in s for x in ["winter", "fireplace", "root vegetable", "heavy iron"]):
        result["palette"] = "winter_blue"
    elif any(x in s for x in ["summer", "festival", "cool tofu", "cucumber"]):
        result["palette"] = "summer_vivid"
    elif any(x in s for x in ["spring", "snow", "mountain vegetable"]):
        result["palette"] = "spring_fresh"
    elif any(x in s for x in ["sunset", "twilight", "dusk"]):
        result["palette"] = "twilight_rose"
    elif any(x in s for x in ["clinic", "medical", "chart", "infographic", "diagram", "digital"]):
        result["palette"] = "clinical_neutral"
    elif any(x in s for x in ["mist", "cool", "fog"]):
        result["palette"] = "cool_mist"
    else:
        result["palette"] = "warm_natural"

    return result


def _detect_from_act(act: int) -> dict:
    """Override camera and mood based on narrative act position."""
    if act == 1:
        return {"mood_override": None, "camera_override": "wide_establishing"}
    elif act == 2:
        return {"mood_override": None, "camera_override": None}
    elif act == 3:
        return {"mood_override": "hopeful", "camera_override": None}
    return {}


# ===========================================================================
# PUBLIC API
# ===========================================================================
def build_scene_style(
    act: int,
    setting: str,
    scene_brief: str = "",
    force_lighting: Optional[str] = None,
    force_mood: Optional[str] = None,
    force_camera: Optional[str] = None,
    force_palette: Optional[str] = None,
) -> str:
    """
    Build the full cinematic style block for a single scene.

    Args:
        act: Narrative act number (1, 2, or 3)
        setting: Scene setting description from script.json
        scene_brief: Short scene description (optional, used as extra signal)
        force_*: Override auto-detected layers manually

    Returns:
        A ready-to-prepend style string for the final prompt.

    Example:
        >>> style = build_scene_style(act=2, setting="Rainy afternoon in the kitchen...")
        >>> final_prompt = f"{style} Grandma Hanako stirs a simmering pot..."
    """
    detected = _detect_from_setting(setting + " " + scene_brief)
    act_hints = _detect_from_act(act)

    # Resolve each layer (force > act hint > auto-detected)
    lighting_key = force_lighting or detected.get("lighting", "morning")
    mood_key = force_mood or act_hints.get("mood_override") or detected.get("mood", "calm")
    camera_key = force_camera or act_hints.get("camera_override") or detected.get("camera", "medium_shot")
    palette_key = force_palette or detected.get("palette", "warm_natural")

    lighting_text = LIGHTING.get(lighting_key, LIGHTING["morning"])
    mood_text = MOOD.get(mood_key, MOOD["calm"])
    camera_text = CAMERA.get(camera_key, CAMERA["medium_shot"])
    palette_text = COLOR_PALETTE.get(palette_key, COLOR_PALETTE["warm_natural"])

    style_block = (
        f"{GLOBAL_STYLE}. "
        f"{lighting_text}. "
        f"{mood_text}. "
        f"{camera_text}. "
        f"Color palette: {palette_text}. "
        f"{NEGATIVE_STYLE}."
    )
    return style_block


def get_debug_layers(act: int, setting: str, scene_brief: str = "") -> dict:
    """Return the detected layer keys for a scene (for debugging/logging)."""
    detected = _detect_from_setting(setting + " " + scene_brief)
    act_hints = _detect_from_act(act)
    return {
        "lighting": detected.get("lighting"),
        "mood": act_hints.get("mood_override") or detected.get("mood"),
        "camera": act_hints.get("camera_override") or detected.get("camera"),
        "palette": detected.get("palette"),
    }
