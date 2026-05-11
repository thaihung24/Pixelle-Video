import json

with open('output/series_sukoyaka_life/ep01/script.json', encoding='utf-8') as f:
    s = json.load(f)

lines = []
lines.append(f"# EP01: {s['title']}")
lines.append("")
lines.append("## Characters")
for c in s['characters']:
    lines.append(f"- **{c['name']}** ({c['id']}, {c.get('role','')})")
    lines.append(f"  - {c.get('visual','')}")
lines.append("")
lines.append(f"## Scenes ({len(s['narrations'])} total)")
lines.append("")

scenes = s.get('scenes', [])
for i, (narr, vp) in enumerate(zip(s['narrations'], s['video_prompts'])):
    sc = scenes[i] if i < len(scenes) else {}
    chars = sc.get('characters', [])
    char_str = ', '.join(chars) if chars else 'no character'
    lines.append(f"### Scene {i+1:02d} [{char_str}]")
    lines.append(f"**Narration:** {narr}")
    lines.append(f"**Video:** {vp[:200]}...")
    lines.append("")

with open('output/series_sukoyaka_life/ep01/script_readable.md', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print("Saved to output/series_sukoyaka_life/ep01/script_readable.md")
