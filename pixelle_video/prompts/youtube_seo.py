"""
YouTube SEO metadata generation prompt.

Generates: description, hashtags, tags, and timestamps for YouTube upload.
Adapted from FlowKit fk-youtube-seo.md skill.
"""


YOUTUBE_SEO_PROMPT = """# Role
You are a YouTube SEO expert for health/wellness anime documentary channels.

# Task
Generate complete YouTube metadata for the following video.

## Video Info
- **Title**: {title}
- **YouTube Title**: {youtube_title}
- **Language**: {language}
- **Channel**: {channel}
- **Author**: {author}
- **Brand**: {brand}
- **Niche**: health-wellness-documentary
- **Total scenes**: {n_scenes}
- **Estimated duration**: {est_duration}

## Content (first 10 narrations as summary):
{content_summary}

# Output Requirements — STRICT JSON

Generate a JSON object with these fields:

## 1. description
YouTube description with 3 zones:
- **Zone 1 (first 150 chars)**: Hook sentence + "チャンネル登録お願いします🔔"
- **Zone 2**: 3-5 sentence story summary (keyword-rich, natural) + timestamps
- **Zone 3**: Channel info + hashtags

Rules:
- ALL text in {language}
- Primary keyword in first 150 chars
- Total description: 500-2000 chars
- Include timestamps every ~30 seconds based on {n_scenes} scenes at ~6s each

## 2. hashtags (array of 15 strings)
- Tier 1 (5): broad health/wellness tags
- Tier 2 (5): topic-specific
- Tier 3 (5): long-tail niche
- Mix {language} + English
- No spaces in hashtags

## 3. tags (array of strings, total < 500 chars)
- Primary keywords first
- Mix exact + broad + long-tail
- Mix {language} + English

## 4. thumbnail_prompts (array of 2 prompt strings)
Generate 2 thumbnail image prompts for this video:
- Include anime style, 1280x720 format
- Bold text in {language} embedded in the image
- Line 1: 2-3 power words (HOOK)
- Line 2: 5-8 words context
- Character: elderly Japanese person in the scene
- Bright, saturated colors, dramatic lighting

**Variant 1 (Face+Text):** Character face 50% of frame, extreme emotion, text at top
**Variant 2 (Action+Text):** Wide angle, character in action, text at upper-left

# Output — ONLY valid JSON:
```json
{{
  "description": "full youtube description text",
  "hashtags": ["#tag1", "#tag2", ...],
  "tags": ["keyword1", "keyword2", ...],
  "thumbnail_prompts": ["prompt1", "prompt2"]
}}
```

# Critical
1. ONLY valid JSON output, no explanations
2. All text in {language} (except English crossover keywords)
3. Description must include timestamps
4. Hashtags: exactly 15, no spaces
5. Tags total: under 500 characters
6. Thumbnail prompts: include anime style, bold text, 1280x720
"""


def build_youtube_seo_prompt(
    title: str,
    youtube_title: str,
    narrations: list[str],
    language: str = "Japanese",
    channel: str = "sukoyaka_life",
    author: str = "@sukoyaka.life1",
    brand: str = "健康長寿の知恵",
    n_scenes: int = 60,
) -> str:
    """
    Build YouTube SEO metadata generation prompt.

    Args:
        title: Episode title
        youtube_title: Generated YouTube title
        narrations: All narration texts
        language: Target language
        channel: Channel name
        author: Author handle
        brand: Brand name
        n_scenes: Total number of scenes
    Returns:
        Formatted prompt for LLM
    """
    # Take first 10 narrations as content summary
    content_summary = "\n".join(
        f"Scene {i+1}: {n}" for i, n in enumerate(narrations[:10])
    )

    # Estimate duration: ~6s per scene
    est_seconds = n_scenes * 6
    est_min = est_seconds // 60
    est_sec = est_seconds % 60
    est_duration = f"{est_min}:{est_sec:02d}"

    return YOUTUBE_SEO_PROMPT.format(
        title=title,
        youtube_title=youtube_title,
        language=language,
        channel=channel,
        author=author,
        brand=brand,
        n_scenes=n_scenes,
        est_duration=est_duration,
        content_summary=content_summary,
    )
