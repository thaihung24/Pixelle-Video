import json
with open('output/series_sukoyaka_life/ep01/script.json', encoding='utf-8') as f:
    s = json.load(f)
scenes = s.get('scenes', [])
chars = s.get('characters', [])
print(f"Characters: {len(chars)}")
for c in chars:
    vid = c.get("visual", "")[:80]
    print(f"  {c['id']}: {vid}...")
print(f"\nScenes with char info: {len(scenes)}")
for sc in scenes[:3]:
    print(f"  Scene {sc.get('scene_number')}: chars={sc.get('characters', [])}")
print(f"\nVideo prompt 1: {s['video_prompts'][0][:150]}...")
print(f"Video prompt 5: {s['video_prompts'][4][:150]}...")
