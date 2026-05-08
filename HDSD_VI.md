# 📖 HƯỚNG DẪN SỬ DỤNG — Pixelle-Video

> Tạo video AI tự động từ văn bản trong vài phút

---

## 1. YÊU CẦU HỆ THỐNG

| Thành phần | Yêu cầu |
|-----------|---------|
| Python | ≥ 3.11 |
| FFmpeg | Bắt buộc (cài hệ thống) |
| RAM | ≥ 4GB |
| Docker | Tùy chọn (khuyến nghị) |
| ComfyUI | Tùy chọn (nếu dùng self-host) |
| API Key LLM | Bắt buộc (OpenAI / Qwen / DeepSeek...) |

---

## 2. CÀI ĐẶT

### Cách A — Chạy với Docker (Khuyến nghị)

```bash
# Clone project
git clone https://github.com/AIDC-AI/Pixelle-Video.git
cd Pixelle-Video

# Tạo file cấu hình
cp config.example.yaml config.yaml
# → Mở config.yaml và điền API key

# Khởi động
docker-compose up -d
```

Sau khi chạy:
- **Web UI**: http://localhost:8501
- **API Docs**: http://localhost:8000/docs

---

### Cách B — Chạy Thủ Công (Development)

```bash
# Cài FFmpeg
# macOS:
brew install ffmpeg
# Ubuntu:
sudo apt-get install ffmpeg fonts-noto-cjk

# Cài uv (package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Cài dependencies
uv pip install -e .

# Cài Playwright (để render HTML frame)
uv run playwright install --with-deps chromium

# Sao chép và chỉnh config
cp config.example.yaml config.yaml

# Khởi động API
uv run python api/app.py

# Khởi động Web UI (terminal khác)
uv run streamlit run web/app.py
```

---

## 3. CẤU HÌNH (`config.yaml`)

```yaml
project_name: Pixelle-Video

# === LLM — Bắt buộc ===
llm:
  api_key: "dummy"               # API key của bạn
  base_url: "https://api.deepseek.com"  # URL của provider
  model: "deepseek-chat"            # Tên model

# Các preset phổ biến:
# Qwen:    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"  model: "qwen-max"
# OpenAI:  base_url: "https://api.openai.com/v1"                          model: "gpt-4o"
# Ollama:  base_url: "http://localhost:11434/v1"                          model: "llama3.2"

# === ComfyUI ===
comfyui:
  comfyui_url: http://127.0.0.1:8188
  runninghub_api_key: ""     # Nếu dùng RunningHub cloud
  runninghub_concurrent_limit: 1

  tts:
    default_workflow: selfhost/tts_edge.json

  image:
    default_workflow: runninghub/image_flux.json
    prompt_prefix: "Minimalist black-and-white matchstick figure style"

  video:
    default_workflow: runninghub/video_wan2.1_fusionx.json

# === Template mặc định ===
template:
  default_template: "1080x1920/image_default.html"
```

---

## 4. SỬ DỤNG WEB UI

Mở trình duyệt vào `http://localhost:8501`

### Bước 1: Chọn Pipeline

| Pipeline | Khi nào dùng |
|----------|-------------|
| **Standard** | Tạo video từ chủ đề hoặc kịch bản văn bản |
| **Asset-Based** | Bạn đã có ảnh/video, muốn tạo video marketing |
| **Custom** | Tự định nghĩa logic |

### Bước 2: Nhập Nội Dung

**Pipeline Standard:**
- Nhập chủ đề (vd: `5 lợi ích của việc đọc sách mỗi ngày`)
- Chọn số cảnh (`n_scenes`: 3–10)
- Chọn chế độ: `generate` (LLM tự viết) hoặc `fixed` (dùng script của bạn)

**Pipeline Asset-Based:**
- Upload ảnh/video lên
- Nhập tiêu đề và mục đích video
- Chọn thời lượng mong muốn (giây)

### Bước 3: Chọn Cài Đặt

- **Template**: Chọn kiểu layout (xem mục 6)
- **Giọng đọc**: Chọn từ danh sách Edge TTS hoặc workflow ComfyUI
- **Nhạc nền**: Tùy chọn file BGM

### Bước 4: Tạo Video

Nhấn **Generate** và theo dõi tiến độ:
```
Sinh narration → Sinh image prompt → Xử lý từng frame → Ghép video
```

Video hoàn chỉnh được lưu trong thư mục `output/`

---

## 5. SỬ DỤNG API

Xem Swagger UI tại: `http://localhost:8000/docs`

### Tạo video (bất đồng bộ — khuyến nghị)

```bash
# Bước 1: Gửi yêu cầu tạo video
curl -X POST http://localhost:8000/api/video/generate/async \
  -H "Content-Type: application/json" \
  -d '{
    "text": "5 lợi ích của việc đọc sách",
    "pipeline": "standard",
    "n_scenes": 5,
    "frame_template": "1080x1920/image_default.html"
  }'

# Kết quả trả về: {"task_id": "20251028_143052_ab3d"}

# Bước 2: Kiểm tra tiến độ
curl http://localhost:8000/api/tasks/20251028_143052_ab3d

# Bước 3: Tải video khi hoàn thành
curl http://localhost:8000/api/files/20251028_143052_ab3d/final.mp4 -o output.mp4
```

### Tạo video đồng bộ (video ngắn <30s)

```bash
curl -X POST http://localhost:8000/api/video/generate/sync \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Xin chào Việt Nam",
    "pipeline": "standard",
    "n_scenes": 3,
    "tts_inference_mode": "local",
    "tts_voice": "vi-VN-HoaiMyNeural"
  }'
```

### Sinh giọng đọc riêng lẻ

```bash
curl -X POST http://localhost:8000/api/tts \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Xin chào, đây là giọng đọc tiếng Việt",
    "voice": "vi-VN-HoaiMyNeural",
    "speed": 1.1
  }'
```

### Gọi LLM

```bash
curl -X POST http://localhost:8000/api/llm \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Viết 3 câu về lợi ích của trà xanh"
  }'
```

---

## 6. CHỌN TEMPLATE

### Quy Tắc Chọn Template

```
Tiền tố tên file → Loại media cần thiết
────────────────────────────────────────
static_*   →  Không cần ComfyUI (nhanh nhất, miễn phí)
image_*    →  Cần sinh ảnh AI (Flux, SD3.5...)
video_*    →  Cần sinh video AI (Wan2.1...)
asset_*    →  Dùng với AssetBasedPipeline
```

### Templates Phổ Biến (1080×1920 — Dọc)

| Template | Phong cách | Cần ComfyUI? |
|----------|-----------|-------------|
| `image_default.html` | Tối giản chuẩn | ✅ Có |
| `image_elegant.html` | Thanh lịch | ✅ Có |
| `image_neon.html` | Neon phát sáng | ✅ Có |
| `image_book.html` | Phong cách sách | ✅ Có |
| `image_cartoon.html` | Hoạt hình | ✅ Có |
| `image_healing.html` | Nhẹ nhàng, dịu mắt | ✅ Có |
| `static_simple.html` | Đơn giản, nhanh | ❌ Không |
| `asset_default.html` | Cho pipeline asset | ✅ (asset) |

### Thêm Template Tùy Chỉnh

1. Tạo file HTML trong `data/templates/1080x1920/my_template.html`
2. Dùng placeholder: `{{title}}`, `{{text}}`, `{{image}}`, `{{index}}`
3. Thêm meta tags kích thước media:
```html
<meta name="template:media-width" content="1080">
<meta name="template:media-height" content="1080">
```

---

## 7. CÁC GIỌNG ĐỌC TIẾNG VIỆT

### Edge TTS (Miễn phí, không cần setup)

| Voice ID | Giới tính | Phong cách |
|----------|-----------|-----------|
| `vi-VN-HoaiMyNeural` | Nữ | Tự nhiên, thân thiện |
| `vi-VN-NamMinhNeural` | Nam | Chuyên nghiệp |

### Điều Chỉnh Tốc Độ

```yaml
# Trong config.yaml
comfyui:
  tts:
    local:
      voice: "vi-VN-HoaiMyNeural"
      speed: 1.1   # 0.5 = chậm, 1.0 = bình thường, 2.0 = nhanh
```

---

## 8. WORKFLOW COMFYUI

### Self-host (ComfyUI cài local)

```yaml
comfyui:
  comfyui_url: http://127.0.0.1:8188
  image:
    default_workflow: selfhost/image_flux.json
```

**Workflows self-host có sẵn:**
- `selfhost/image_flux.json` — Sinh ảnh Flux
- `selfhost/video_wan2.1_fusionx.json` — Sinh video Wan2.1
- `selfhost/tts_edge.json` — TTS qua ComfyUI
- `selfhost/tts_index2.json` — Index-TTS
- `selfhost/analyse_image.json` — Phân tích ảnh
- `selfhost/analyse_video.json` — Phân tích video

### RunningHub (Cloud, không cần GPU)

```yaml
comfyui:
  runninghub_api_key: "your-key"
  runninghub_concurrent_limit: 3  # Chạy song song
  image:
    default_workflow: runninghub/image_flux.json
```

**Workflows RunningHub có sẵn:**
- `runninghub/image_flux.json` — Flux image
- `runninghub/image_flux2.json` — Flux image v2
- `runninghub/image_sd3.5.json` — Stable Diffusion 3.5
- `runninghub/image_qwen_chinese_cartoon.json` — Hoạt hình Qwen
- `runninghub/video_wan2.1_fusionx.json` — Video Wan2.1
- `runninghub/video_qwen_wan2.2.json` — Video Qwen+Wan2.2
- `runninghub/tts_spark.json` — Spark TTS

---

## 9. SỬ DỤNG BẰNG PYTHON SDK

```python
import asyncio
from pixelle_video import pixelle_video

async def main():
    # Khởi tạo
    await pixelle_video.initialize()

    # --- Ví dụ 1: Tạo video từ chủ đề ---
    result = await pixelle_video.generate_video(
        text="5 lợi ích của việc uống đủ nước mỗi ngày",
        pipeline="standard",
        n_scenes=5,
        frame_template="1080x1920/image_default.html",
        tts_voice="vi-VN-HoaiMyNeural",
        tts_speed=1.1
    )
    print(f"Video: {result.video_path}")

    # --- Ví dụ 2: Dùng script cố định ---
    script = """
    Uống đủ nước giúp da sáng hơn.
    Nước tăng cường khả năng tập trung.
    Uống nước giúp giảm cân hiệu quả.
    """
    result = await pixelle_video.generate_video(
        text=script,
        pipeline="standard",
        mode="fixed",
        split_mode="sentence"
    )

    # --- Ví dụ 3: Pipeline asset-based ---
    result = await pixelle_video.generate_video(
        pipeline="asset_based",
        assets=["img1.jpg", "img2.jpg", "promo.mp4"],
        video_title="Khuyến mãi tháng 5",
        intent="Quảng bá sản phẩm mỹ phẩm với giọng điệu sang trọng",
        duration=30,
        bgm_path="bgm/default.mp3",
        bgm_volume=0.2
    )

    # --- Ví dụ 4: Dùng riêng từng service ---
    text = await pixelle_video.llm("Viết 1 câu hay về mùa hè")
    audio = await pixelle_video.tts(text, voice="vi-VN-HoaiMyNeural")
    print(f"Audio: {audio}")

    await pixelle_video.cleanup()

asyncio.run(main())
```

---

## 10. CẤU TRÚC OUTPUT

Mỗi lần tạo video, hệ thống tạo thư mục riêng:

```
output/
└── 20251028_143052_ab3d/        ← Task ID
    ├── final.mp4                ← Video hoàn chỉnh
    ├── frames/
    │   ├── 01_audio.mp3         ← Giọng đọc cảnh 1
    │   ├── 01_composed.png      ← Frame ảnh đã render
    │   ├── 01_segment.mp4       ← Video clip cảnh 1
    │   ├── 02_audio.mp3
    │   ├── 02_composed.png
    │   ├── 02_segment.mp4
    │   └── ...
    ├── metadata.json            ← Thông tin task
    └── storyboard.json          ← Kịch bản đầy đủ
```

---

## 11. TỐI ƯU HIỆU SUẤT

### Tăng Tốc Với Template Tĩnh
```yaml
template:
  default_template: "1080x1920/static_simple.html"
```
→ Bỏ qua hoàn toàn bước sinh ảnh AI, tiết kiệm 60–80% thời gian.

### Xử Lý Song Song (RunningHub)
```yaml
comfyui:
  runninghub_concurrent_limit: 3  # Chạy 3 frame cùng lúc
```

### Dùng Ollama (Miễn phí, chạy local)
```yaml
llm:
  api_key: "dummy"
  base_url: "http://localhost:11434/v1"
  model: "qwen2.5"
```

---

## 12. XỬ LÝ LỖI THƯỜNG GẶP

| Lỗi | Nguyên nhân | Giải pháp |
|-----|------------|-----------|
| `FFmpeg not found` | FFmpeg chưa cài | `brew install ffmpeg` (macOS) |
| `Playwright browser not found` | Chưa cài chromium | `playwright install --with-deps chromium` |
| `Edge TTS 401 error` | Rate limit | Tự động retry, hoặc chờ vài giây |
| `ComfyUI connection refused` | Server chưa chạy | Khởi động ComfyUI trước |
| `LLM API error` | API key sai hoặc hết credit | Kiểm tra lại `config.yaml` |
| `Template not found` | Sai đường dẫn template | Kiểm tra thư mục `templates/` |
| `No audio generated` | Workflow TTS lỗi | Thử `inference_mode: local` |

---

## 13. THÊM NHẠC NỀN TÙY CHỈNH

```bash
# Đặt file MP3 vào thư mục
mkdir -p data/bgm
cp my_music.mp3 data/bgm/
```

Sau đó chọn trong Web UI hoặc truyền vào API:
```json
{
  "bgm_path": "my_music.mp3",
  "bgm_volume": 0.2,
  "bgm_mode": "loop"
}
```

---

## 14. DOCKER COMPOSE — CẤU HÌNH NÂNG CAO

```yaml
# docker-compose.yml (tùy chỉnh)
services:
  pixelle-video:
    environment:
      - PIXELLE_VIDEO_ROOT=/app
    volumes:
      - ./config.yaml:/app/config.yaml  # Mount config
      - ./output:/app/output             # Mount output
      - ./data:/app/data                 # Mount custom data
    ports:
      - "8000:8000"   # API
      - "8501:8501"   # Web UI
```

**Build với mirror Trung Quốc** (tăng tốc download):
```bash
docker-compose build --build-arg USE_CN_MIRROR=true
```

---

## 15. LIÊN HỆ & HỖ TRỢ

- **GitHub**: https://github.com/AIDC-AI/Pixelle-Video
- **Issues**: Báo lỗi qua GitHub Issues
- **Discord**: Xem ảnh `resources/discord.png` để tham gia cộng đồng
- **WeChat**: Xem ảnh `resources/wechat.png` để tham gia nhóm

---

*Tài liệu được biên soạn bởi phân tích source code phiên bản 0.1.15*
