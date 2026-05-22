# 🎵 Hướng dẫn sử dụng Thư viện Audio — すこやかライフ

## Cấu trúc thư mục (Compact Version - 50 Files)

```
assets/audio/
├── audio_manifest.json          ← Toàn bộ danh sách file, mô tả, và gợi ý theo tập
│
├── bgm/                         ← Background Music (Nhạc nền)
│   ├── ghibli_piano/            ← Piano phong cách Studio Ghibli
│   │   ├── main_theme.mp3
│   │   ├── hanako_theme.mp3
│   │   ├── kenji_theme.mp3
│   │   ├── morning_light.mp3
│   │   ├── evening_reflection.mp3
│   │   ├── memory_lane.mp3
│   │   ├── hope_and_warmth.mp3
│   │   ├── gentle_wisdom.mp3
│   │   └── seasons_passing.mp3
│   │
│   ├── acoustic_folk/           ← Acoustic Guitar / Folk ấm áp
│   │   ├── daily_joy.mp3
│   │   ├── village_morning.mp3
│   │   ├── cooking_time.mp3
│   │   ├── garden_breeze.mp3
│   │   ├── walking_path.mp3
│   │   ├── family_table.mp3
│   │   ├── old_friends.mp3
│   │   ├── harvest_festival.mp3
│   │   ├── simple_happiness.mp3
│   │   └── countryside_road.mp3
│   │
│   ├── lofi_japanese/           ← Lofi Chillhop + nhạc cụ Nhật
│   │   ├── koto_chill.mp3
│   │   ├── shakuhachi_beat.mp3
│   │   ├── zen_study.mp3
│   │   ├── afternoon_tea.mp3
│   │   ├── rainy_tatami.mp3
│   │   ├── night_onsen.mp3
│   │   ├── sakura_petals.mp3
│   │   └── market_morning.mp3
│   │
│   ├── orchestral/              ← Dàn nhạc — cảnh cảm xúc lớn
│   │   ├── epic_sunrise.mp3
│   │   ├── life_is_beautiful.mp3
│   │   └── ikigai_anthem.mp3
│   │
│   └── zen_ambient/             ← Nhạc Zen / Thiên nhiên Ambient
│       ├── bamboo_forest.mp3
│       ├── water_meditation.mp3
│       └── autumn_temple.mp3
│
├── sfx/                         ← Sound Effects & Ambient
│   ├── nature/                  ← Thiên nhiên Nhật Bản
│   │   ├── cicadas_summer.mp3
│   │   ├── birds_morning.mp3
│   │   ├── rain_light.mp3
│   │   └── stream_gentle.mp3
│   │
│   ├── kitchen/                 ← Bếp núc / Nấu ăn
│   │   ├── chopping_veg.mp3
│   │   ├── soup_simmering.mp3
│   │   ├── pour_tea.mp3
│   │   └── sizzling_pan.mp3
│   │
│   ├── indoor/                  ← Trong nhà / Đồ vật truyền thống Nhật
│   │   ├── wind_chime.mp3
│   │   ├── sliding_door.mp3
│   │   └── fire_crackling.mp3
│   │
│   ├── outdoor/                 ← Ngoại cảnh — chợ, vườn, đền
│   │   ├── market_ambience.mp3
│   │   └── bicycle_bell.mp3
│   │
│   └── transition/              ← Hiệu ứng chuyển cảnh
│       ├── whoosh_soft.mp3
│       └── chime_transition.mp3
│
└── jingles/                     ← Nhạc hiệu ngắn (Intro/Outro/Logo)
    ├── intro_full.mp3           ← 15 giây
    └── outro_full.mp3           ← 20 giây
```

---

## Cách sử dụng

### 1. Bỏ file vào đúng thư mục, đúng tên
Tìm file nhạc bất kỳ từ internet → đổi tên thành **đúng tên trong danh sách** → bỏ vào đúng thư mục.

**Ví dụ:**
- Tải nhạc piano Ghibli → đổi thành `morning_light.mp3` → bỏ vào `bgm/ghibli_piano/`
- Tải tiếng Ve sầu → đổi thành `cicadas_summer.mp3` → bỏ vào `sfx/nature/`

### 2. Nguồn nhạc miễn phí bản quyền (CC0 / Royalty-Free)
| Nguồn | Loại | Link |
|---|---|---|
| **YouTube Audio Library** | BGM + SFX | https://studio.youtube.com/channel/music |
| **Freesound.org** | SFX + Ambient | https://freesound.org |
| **Pixabay Music** | BGM | https://pixabay.com/music |
| **Uppbeat.io** | BGM Lofi / Acoustic | https://uppbeat.io |
| **Mixkit** | BGM + SFX | https://mixkit.co |
