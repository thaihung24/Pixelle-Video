# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Anime Storyboard Generation Prompt

2-stage approach that REUSES existing Alibaba prompt modules:
  Stage 1 (NEW):  Generate character definitions + scene outline
  Stage 2 (REUSE): Use existing topic_narration.py + video_generation.py
                    with character visuals injected as context

This ensures we leverage the battle-tested prompt engineering from AIDC-AI
(opening diversity, word count calibration, citation guidelines, etc.)
while adding character consistency for long-form anime productions.
"""

import json
from typing import Optional

from loguru import logger


# ==============================================================================
# Stage 1: Character & Scene Blueprint
# This is the ONLY truly new prompt. It generates:
#   - Character definitions (visual descriptions for consistency)
#   - Scene outline (which characters appear where, settings)
# Narrations and video prompts are generated separately using Alibaba's prompts.
# ==============================================================================

ANIME_BLUEPRINT_PROMPT = """# Role
You are a professional anime documentary scriptwriter specializing in educational series
about health, culture, and lifestyle for Japanese elderly audiences.

# Task
Create a CHARACTER SHEET and SCENE OUTLINE for a {n_scenes}-scene anime documentary about:
**{topic}**

Language: **{language}**

# PART 1: Characters (2-4 recurring characters)
For each character provide:
- `id`: short snake_case (e.g. "grandma_hanako")
- `name`: character name in {language}
- `visual`: EXTREMELY DETAILED English appearance description for AI image generation.
  Include: exact age, gender, hair color+style, eye color, skin tone, body build+height,
  default clothing with colors+patterns, accessories, distinguishing features.
  This description will be copy-pasted into EVERY video prompt where the character appears,
  so it must be precise and repeatable.
  Example: "78-year-old Japanese woman, silver-white hair in neat traditional bun held with wooden kanzashi pin, warm brown eyes with gentle crow's feet, fair skin with subtle age spots on cheeks, petite build 148cm, wearing deep indigo cotton kimono with small white wave pattern and cream-colored obi, round tortoiseshell reading glasses perched on small nose"
- `role`: "narrator" | "protagonist" | "supporting"

# PART 2: Scene Outline
For each scene provide:
- `scene_number`: 1 to {n_scenes}
- `act`: 1 (introduction, scenes 1-{act1_end}), 2 (exploration, {act2_start}-{act2_end}), 3 (conclusion, {act3_start}-{n_scenes})
- `characters`: array of character `id`s present
- `setting`: English description of location/environment (15-30 words)
- `scene_brief`: one-sentence summary of what happens (in {language}, 10-20 chars)

NOTE: Do NOT generate narrations or video prompts here. They will be generated separately.

# Narrative Arc
- **Act 1**: Establish world, introduce characters, pose central question
- **Act 2**: Explore topics through character activities (diet, exercise, social bonds, mindset)
- **Act 3**: Synthesize insights, emotional climax, forward-looking wisdom

# Output — ONLY valid JSON:
```json
{{
  "title": "Title in {language}",
  "characters": [
    {{
      "id": "grandma_hanako",
      "name": "花子おばあちゃん",
      "visual": "78-year-old Japanese woman, silver-white hair in neat traditional bun...",
      "role": "protagonist"
    }}
  ],
  "scenes": [
    {{
      "scene_number": 1,
      "act": 1,
      "characters": ["grandma_hanako"],
      "setting": "Peaceful Japanese mountain village at dawn, cherry blossoms, traditional wooden houses",
      "scene_brief": "村の朝の風景を紹介"
    }}
  ]
}}
```

# Critical
1. ONLY valid JSON output
2. EXACTLY {n_scenes} scenes
3. Character `visual` must be 40-80 English words — VERY detailed and specific
4. `setting` in English, 15-30 words
5. `scene_brief` in {language}, 10-20 characters — just a summary, NOT the narration
6. Every character `id` in scenes must match a defined character
"""


# ==============================================================================
# Character Visual Injection — prepend character descriptions to narrations
# before passing them to the EXISTING Alibaba video_generation.py prompt.
# ==============================================================================

CHARACTER_INJECTION_TEMPLATE = """[CHARACTER VISUAL REFERENCES — Include these descriptions verbatim in every video prompt where the character appears]
{char_descriptions}

[SCENE CONTEXT]
{scene_context}

[NARRATION TO VISUALIZE]
{narration}"""


def build_anime_blueprint_prompt(
    topic: str,
    n_scenes: int = 65,
    language: str = "Japanese",
    fixed_characters: list[dict] | None = None,
) -> str:
    """
    Build Stage 1 prompt: scene outline (+ characters if not from bible).

    Args:
        topic: Documentary topic/theme
        n_scenes: Total number of scenes
        language: Target narration language
        fixed_characters: If provided, characters from series bible (skip generation)
    Returns:
        Formatted prompt for LLM
    """
    act1_end = max(1, round(n_scenes * 0.20))
    act2_start = act1_end + 1
    act2_end = max(act2_start, round(n_scenes * 0.75))
    act3_start = act2_end + 1

    base_prompt = ANIME_BLUEPRINT_PROMPT.format(
        topic=topic,
        n_scenes=n_scenes,
        language=language,
        act1_end=act1_end,
        act2_start=act2_start,
        act2_end=act2_end,
        act3_start=act3_start,
    )

    if fixed_characters:
        # Append character definitions — LLM only needs to generate scenes
        import json
        char_block = json.dumps(fixed_characters, ensure_ascii=False, indent=2)
        bible_instruction = f"""

# IMPORTANT: CHARACTERS ARE PRE-DEFINED (from Series Bible)
Do NOT create new characters. Use EXACTLY these characters:

```json
{char_block}
```

Your output JSON must include these exact characters in the "characters" array.
You only need to create the "scenes" array using these character IDs.
Assign characters to scenes based on their roles and the scene content.
"""
        base_prompt += bible_instruction
        logger.debug(f"[anime_storyboard] Appended {len(fixed_characters)} fixed characters to blueprint prompt")

    return base_prompt


def build_narration_topic_with_characters(
    topic: str,
    characters: list[dict],
    scenes: list[dict],
) -> str:
    """
    Enrich the topic string with character + scene context before passing
    to the EXISTING build_topic_narration_prompt() from Alibaba.

    This way, the Alibaba prompt's diversity rules, word count calibration,
    citation guidelines, etc. are all preserved — we just give it richer context.

    Args:
        topic: Original documentary topic
        characters: Character definitions from blueprint
        scenes: Scene outline from blueprint
    Returns:
        Enriched topic string
    """
    logger.debug(f"[anime_storyboard] build_narration_topic_with_characters()")
    logger.debug(f"   → Enriching topic for Alibaba's build_topic_narration_prompt()")
    logger.debug(f"   → Characters: {[c['id'] for c in characters]}")
    logger.debug(f"   → Scenes: {len(scenes)}")

    char_lines = []
    for c in characters:
        char_lines.append(f"- {c['name']} ({c['id']}): {c.get('role', 'supporting')}")

    scene_lines = []
    for s in scenes:
        chars_in_scene = ", ".join(s.get("characters", []))
        scene_lines.append(
            f"Scene {s['scene_number']} (Act {s.get('act', 2)}): "
            f"{s.get('scene_brief', '')} [{chars_in_scene}] — {s.get('setting', '')}"
        )

    enriched = f"""{topic}

=== DOCUMENTARY STRUCTURE ===
Characters:
{chr(10).join(char_lines)}

Scene outline (each narration should follow this scene order):
{chr(10).join(scene_lines)}

IMPORTANT: Generate exactly {len(scenes)} narrations, one per scene, following the outline above.
Each narration should naturally convey the scene's content as described in the outline."""

    logger.debug(f"   → Enriched topic: {len(enriched)} chars (original: {len(topic)} chars)")
    return enriched


def inject_character_visuals_into_narrations(
    narrations: list[str],
    characters: list[dict],
    scenes: list[dict],
) -> list[str]:
    """
    Enrich narrations with character visual context before passing them
    to the EXISTING build_video_prompt_prompt() from Alibaba (video_generation.py).

    Instead of rewriting the video prompt generation logic, we prepend
    character visual info to each narration so the Alibaba prompt naturally
    incorporates it into the generated video prompts.

    Args:
        narrations: List of narration texts
        characters: Character definitions with 'id' and 'visual'
        scenes: Scene metadata with 'characters' and 'setting'
    Returns:
        List of enriched narration strings for video prompt generation
    """
    logger.debug(f"[anime_storyboard] inject_character_visuals_into_narrations()")
    logger.debug(f"   → Enriching {len(narrations)} narrations for Alibaba's build_video_prompt_prompt()")
    logger.debug(f"   → Characters available: {[c['id'] for c in characters]}")

    char_map = {c["id"]: c for c in characters}
    enriched = []

    for i, narration in enumerate(narrations):
        if i < len(scenes):
            scene = scenes[i]
            # Build character description block for this scene
            scene_chars = scene.get("characters", [])
            char_descs = []
            for cid in scene_chars:
                if cid in char_map:
                    c = char_map[cid]
                    char_descs.append(f"- {c.get('name', cid)} ({cid}): {c['visual']}")

            char_block = "\n".join(char_descs) if char_descs else "No specific characters"
            setting = scene.get("setting", "")

            enriched_narration = CHARACTER_INJECTION_TEMPLATE.format(
                char_descriptions=char_block,
                scene_context=f"Setting: {setting}" if setting else "",
                narration=narration,
            )
            enriched.append(enriched_narration)

            if i < 2:  # Log first 2 enriched narrations for audit
                logger.debug(f"   → Scene {i+1} chars: {scene_chars} | setting: {setting[:40]}...")
        else:
            enriched.append(narration)

    logger.debug(f"   → Enriched {len(enriched)} narrations (avg {sum(len(e) for e in enriched) // max(1, len(enriched))} chars each)")
    return enriched
