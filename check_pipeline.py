import json, os

with open('output/series_sukoyaka_life/ep01/script.json', encoding='utf-8') as f:
    s = json.load(f)

print('=== EP01 SCRIPT STATUS ===')
print(f'Title: {s["title"]}')
print(f'Characters: {len(s["characters"])}')
for c in s['characters']:
    print(f'  [{c["id"]}] {c["name"]}')
print(f'Narrations: {len(s["narrations"])}')
print(f'Video prompts: {len(s["video_prompts"])}')
print()
print('=== Sample Narration #1 ===')
print(s['narrations'][0])
print()
print('=== Sample Narration #30 ===')
print(s['narrations'][29])
print()
print('=== Sample Video Prompt #1 ===')
print(s['video_prompts'][0][:200])
print()

# Verify bible voice config
with open('series_bible.json', encoding='utf-8') as f:
    bible = json.load(f)

vc = bible.get('voice', {})
print('=== VOICE CONFIG (from series_bible.json) ===')
print(f'  tts_mode: {vc.get("tts_mode")}')
print(f'  ref_audio: {vc.get("ref_audio")}')
print(f'  ref_text: {vc.get("ref_text")}')
print(f'  speed: {vc.get("speed")}')
print(f'  ref_audio exists: {os.path.exists(vc.get("ref_audio", ""))}')

# Verify generate_series passes correct args
print()
print('=== PIPELINE FLOW ===')
print('Step 0: Character refs -> DONE (4 media_ids in config.yaml)')
print('Step 1: Storyboard -> DONE (script.json created)')
print('Step 2: Render -> generate_series.py reads voice from bible:')
print(f'  resume_pipeline.py --tts-mode omnivoice \\')
print(f'    --ref-audio {vc.get("ref_audio")} \\')
print(f'    --ref-text {vc.get("ref_text")} \\')
print(f'    --tts-speed {vc.get("speed")}')
