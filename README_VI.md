# 🎬 Pixelle-Video — Tài Liệu Tiếng Việt

> **Phiên bản:** 0.1.15 | **Giấy phép:** Apache 2.0 | **Tác giả:** AIDC-AI (Alibaba International Digital Commerce)

---

## 🛡️ BÁO CÁO KIỂM TRA BẢO MẬT (Security Audit)

> ⚠️ **Đây là phần quan trọng nhất — đọc trước khi sử dụng.**

### Kết Quả Kiểm Tra: ✅ KHÔNG PHÁT HIỆN MÃ ĐỘC

Sau khi phân tích toàn bộ source code, **không tìm thấy bất kỳ mã độc, backdoor, hay hành vi đáng ngờ nào** trong project này. Chi tiết:

---

### 🔍 Kiểm Tra Theo Từng Mục

#### 1. Thư mục `resources/` — ✅ SẠCH
- Chỉ chứa **7 file ảnh PNG** (ảnh minh họa tài liệu):
  - `discord.png`, `example.png`, `flow.png`, `flow_en.png`
  - `webui.png`, `webui_en.png`, `wechat.png`
- **Không có file thực thi, script ẩn, hay payload độc hại**
- Đây là ảnh tĩnh thuần túy dùng trong README

#### 2. Thư mục `workflows/` — ✅ SẠCH
- Chứa **29 file JSON** định nghĩa workflow ComfyUI (selfhost & RunningHub)
- Các file JSON này là cấu hình node AI (TTS, Image, Video generation)
- **Không có code thực thi, eval(), exec(), hay lệnh shell ẩn**

#### 3. Thư mục `bgm/` — ✅ SẠCH
- Chỉ có `default.mp3` — file âm thanh nền mặc định
- **Không phát hiện file .exe, .sh ẩn hay payload**

#### 4. Thư mục `templates/` — ✅ SẠCH
- Chứa **file HTML thuần túy** (21 file cho định dạng 1080x1920, 1080x1080, 1920x1080)
- Templates dùng cú pháp placeholder `{{title}}`, `{{text}}`, `{{image}}` — an toàn
- Không có JavaScript độc hại, XSS, hay inline code nguy hiểm

#### 5. Core Python Code — ✅ SẠCH

| File | Đánh Giá |
|------|----------|
| `pixelle_video/service.py` | Khởi tạo service, không có gì đáng ngờ |
| `pixelle_video/services/llm_service.py` | Gọi OpenAI SDK thuần túy |
| `pixelle_video/services/tts_service.py` | Dùng EdgeTTS + ComfyKit |
| `pixelle_video/utils/tts_util.py` | Gọi Microsoft Edge TTS API |
| `pixelle_video/utils/os_util.py` | Quản lý path/file hệ thống |
| `pixelle_video/services/video.py` | Dùng FFmpeg thuần túy |
| `pixelle_video/services/frame_html.py` | Playwright render HTML |
| `pixelle_video/services/frame_processor.py` | Điều phối pipeline |
| `api/app.py` | FastAPI server |

#### 6. Dockerfile — ✅ SẠCH
- Chỉ cài đặt: `ffmpeg`, `fonts-noto-cjk`, `curl`
- Dùng `uv pip install` từ PyPI chính thống
- Không có lệnh `curl | bash` hay download từ nguồn lạ

#### 7. `pyproject.toml` — ✅ SẠCH
- Tất cả dependencies là thư viện Python chính thống:
  - `fastapi`, `openai`, `pydantic`, `loguru`, `edge-tts`, `playwright`
  - `ffmpeg-python`, `moviepy`, `httpx`, `streamlit`, `comfykit`
- **Không có dependency giả mạo hay typosquatting**

---

### ⚠️ Lưu Ý Về Bảo Mật Khi Sử Dụng

Dù code sạch, người dùng cần chú ý những điều sau:

1. **API Key trong `config.yaml`**: File này được `.gitignore` loại trừ nhưng hãy đảm bảo **không commit** lên Git
2. **ComfyUI Port 8188**: Nếu dùng self-host, không expose port này ra internet
3. **RunningHub API Key**: Là API key trả phí, bảo quản cẩn thận
4. **CORS đang mở rộng** (`allow_origins: *` khi enabled) — phù hợp cho dev, cần restrict khi production

---

## 📖 GIỚI THIỆU DỰ ÁN

**Pixelle-Video** là nền tảng tạo video AI tự động hoàn toàn, được phát triển bởi **AIDC-AI** (nhóm AI của Alibaba International Digital Commerce). Dự án cho phép biến một đoạn văn bản (chủ đề, kịch bản, hay script có sẵn) thành video ngắn hoàn chỉnh với:

- 🗣️ **Giọng đọc (TTS)** tự động bằng Microsoft Edge TTS hoặc ComfyUI
- 🎨 **Hình ảnh AI** được sinh ra từ Flux, Wan2.1, SD3.5, v.v.
- 🎬 **Video AI** được tổng hợp qua ComfyUI workflows
- 📝 **Phụ đề** tự động overlay lên video
- 🎵 **Nhạc nền (BGM)** tùy chọn

---

## 🏗️ KIẾN TRÚC HỆ THỐNG

```
Pixelle-Video
├── pixelle_video/              # Core Python library
│   ├── service.py              # PixelleVideoCore — điểm vào chính
│   ├── config/                 # Quản lý cấu hình (YAML → Pydantic)
│   ├── pipelines/              # Các pipeline tạo video
│   │   ├── standard.py         # Pipeline chuẩn (chủ đề → video)
│   │   ├── custom.py           # Pipeline tùy chỉnh (template)
│   │   ├── asset_based.py      # Pipeline từ ảnh/video có sẵn
│   │   └── linear.py           # Base class (Template Method Pattern)
│   ├── services/               # Các dịch vụ riêng lẻ
│   │   ├── llm_service.py      # Gọi LLM (OpenAI SDK compatible)
│   │   ├── tts_service.py      # Tổng hợp giọng đọc
│   │   ├── media.py            # Sinh ảnh/video AI
│   │   ├── video.py            # Ghép video (FFmpeg)
│   │   ├── frame_html.py       # Render frame từ HTML (Playwright)
│   │   ├── frame_processor.py  # Điều phối xử lý từng frame
│   │   ├── persistence.py      # Lưu lịch sử task
│   │   └── history_manager.py  # Quản lý lịch sử
│   ├── utils/                  # Tiện ích
│   │   ├── os_util.py          # Quản lý path/file
│   │   ├── tts_util.py         # Edge TTS client
│   │   ├── content_generators.py # Sinh nội dung (narration, prompt)
│   │   └── template_util.py    # Xử lý template HTML
│   └── models/                 # Data models (Pydantic)
├── api/                        # FastAPI REST API
│   ├── app.py                  # FastAPI app + routers
│   └── routers/                # Các endpoint API
├── web/                        # Streamlit Web UI
├── workflows/                  # ComfyUI workflow JSON
│   ├── selfhost/               # Dành cho ComfyUI local
│   └── runninghub/             # Dành cho RunningHub cloud
├── templates/                  # HTML frame templates
│   ├── 1080x1920/              # Dọc (21 templates)
│   ├── 1080x1080/              # Vuông
│   └── 1920x1080/              # Ngang
├── bgm/                        # Nhạc nền mặc định
├── resources/                  # Ảnh tài liệu
├── Dockerfile                  # Docker image
├── docker-compose.yml          # Docker Compose
└── config.example.yaml         # Mẫu cấu hình
```

---

## ⚙️ CÁC THÀNH PHẦN CHÍNH — PHÂN TÍCH CHI TIẾT

### 1. `PixelleVideoCore` — Trung Tâm Điều Phối

**File:** `pixelle_video/service.py`

Đây là class trung tâm của toàn bộ hệ thống. Khi khởi tạo, nó tạo ra tất cả các service:

```python
# Khởi tạo đầy đủ
from pixelle_video import pixelle_video
await pixelle_video.initialize()

# Dùng các service
answer = await pixelle_video.llm("Giải thích về năng lượng tái tạo")
audio  = await pixelle_video.tts("Xin chào thế giới")
result = await pixelle_video.generate_video(text="5 lợi ích của việc đọc sách", n_scenes=5)
```

**Lazy initialization**: `ComfyKit` (kết nối ComfyUI) chỉ được tạo khi có request đầu tiên, giảm thời gian khởi động.

**Config hot-reload**: Cấu hình được đọc lại từ `config_manager` mỗi lần gọi, không cần restart.

---

### 2. Ba Pipeline Tạo Video

#### Pipeline 1: `StandardPipeline` — Chuẩn
**File:** `pixelle_video/pipelines/standard.py`

Dành cho việc tạo video từ một **chủ đề hoặc script văn bản**. Gồm 8 bước:

| Bước | Tên | Mô Tả |
|------|-----|--------|
| 1 | `setup_environment` | Tạo thư mục task, xác định đường dẫn output |
| 2 | `generate_content` | LLM sinh narration hoặc tách script có sẵn |
| 3 | `determine_title` | Xác định tiêu đề video (tự động hoặc LLM) |
| 4 | `plan_visuals` | Sinh image prompt cho từng cảnh |
| 5 | `initialize_storyboard` | Tạo Storyboard + StoryboardFrame |
| 6 | `produce_assets` | Sinh audio + hình ảnh + compose từng frame |
| 7 | `post_production` | Ghép video + thêm nhạc nền |
| 8 | `finalize` | Tạo kết quả + lưu metadata |

**Hai chế độ:**
- `mode="generate"` (mặc định): LLM tự viết narration từ chủ đề
- `mode="fixed"`: Dùng script văn bản có sẵn, tách theo dòng/đoạn

**Hỗ trợ xử lý song song** (parallel): Khi dùng RunningHub workflows, có thể xử lý nhiều frame cùng lúc theo `runninghub_concurrent_limit`.

---

#### Pipeline 2: `AssetBasedPipeline` — Dựa Trên Tài Nguyên Có Sẵn
**File:** `pixelle_video/pipelines/asset_based.py`

Dành cho doanh nghiệp đã có ảnh/video sẵn và muốn tạo video marketing:

1. **Phân tích ảnh/video** bằng AI (ImageAnalysisService / VideoAnalysisService)
2. **LLM viết kịch bản** phù hợp với từng ảnh
3. **Ghép narration + asset** thành video hoàn chỉnh

```python
result = await pixelle_video.generate_video(
    pipeline="asset_based",
    assets=["/path/to/img1.jpg", "/path/to/img2.jpg"],
    video_title="Khuyến mãi cuối năm",
    intent="Quảng bá sản phẩm thú cưng với giọng điệu thân thiện",
    duration=30
)
```

---

#### Pipeline 3: `CustomPipeline` — Tùy Chỉnh
**File:** `pixelle_video/pipelines/custom.py`

Template để người dùng tự viết logic pipeline riêng.

---

### 3. `LLMService` — Gọi Mô Hình Ngôn Ngữ Lớn

**File:** `pixelle_video/services/llm_service.py`

Hỗ trợ **bất kỳ API tương thích OpenAI**:

| Provider | Base URL | Model ví dụ |
|----------|----------|-------------|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o`, `gpt-4o-mini` |
| Alibaba Qwen | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-max`, `qwen-plus` |
| DeepSeek | `https://api.deepseek.com` | `deepseek-chat` |
| Anthropic Claude | (OpenAI-compatible gateway) | `claude-sonnet-4-5` |
| Ollama (Local) | `http://localhost:11434/v1` | `llama3.2`, `qwen2.5` |

**Structured Output**: Hỗ trợ trả về Pydantic model thay vì chuỗi text thuần:

```python
class VideoScript(BaseModel):
    scenes: List[SceneScript]

script = await pixelle_video.llm(
    prompt="Viết kịch bản về lợi ích đọc sách",
    response_type=VideoScript
)
```

---

### 4. `TTSService` — Tổng Hợp Giọng Đọc

**File:** `pixelle_video/services/tts_service.py`

**Hai chế độ:**

| Chế độ | Cách hoạt động | Yêu cầu |
|--------|----------------|---------|
| `local` | Microsoft Edge TTS (miễn phí, 400+ giọng) | Không cần API key |
| `comfyui` | ComfyUI workflow (CosyVoice, Index-TTS, Spark TTS) | ComfyUI server |

**Giọng tiếng Việt** (Edge TTS): `vi-VN-HoaiMyNeural`, `vi-VN-NamMinhNeural`

**Xử lý lỗi**: Tự động retry 5 lần với exponential backoff khi gặp lỗi 401 (rate limit)

---

### 5. `VideoService` — Xử Lý Video

**File:** `pixelle_video/services/video.py`

Tất cả xử lý video dùng **FFmpeg** qua thư viện `ffmpeg-python`:

| Phương thức | Chức năng |
|-------------|-----------|
| `concat_videos()` | Ghép nhiều video clip thành 1 |
| `merge_audio_video()` | Thêm giọng đọc vào video |
| `add_bgm()` | Thêm nhạc nền |
| `create_video_from_image()` | Tạo video từ ảnh tĩnh + audio |
| `overlay_image_on_video()` | Chồng ảnh trong suốt lên video |

**Thông minh về thời lượng**: Tự động padding/trim video để khớp với audio, tránh màn hình đen.

---

### 6. `HTMLFrameGenerator` — Render Frame Bằng HTML

**File:** `pixelle_video/services/frame_html.py`

Thay vì dùng PIL/OpenCV để vẽ frame, hệ thống dùng **Playwright + Chromium** để render HTML template thành ảnh PNG. Điều này cho phép:

- Thiết kế frame phức tạp với CSS
- Font chữ CJK (Trung/Nhật/Hàn/Việt) chính xác
- Animation/gradient dễ dàng

**Cú pháp template**: `{{title}}`, `{{text}}`, `{{image}}`, `{{index}}`, + custom params

---

### 7. `FrameProcessor` — Điều Phối Xử Lý Frame

**File:** `pixelle_video/services/frame_processor.py`

Xử lý từng "frame" (cảnh) theo 4 bước:

```
TTS Audio → AI Image/Video → HTML Render → Video Segment
```

Đối với **video template**: Chèn HTML overlay (transparent) lên trên video AI.
Đối với **image template**: Compose ảnh AI vào HTML rồi tạo video tĩnh từ ảnh + audio.

---

### 8. REST API — FastAPI

**File:** `api/app.py`

Các endpoint chính:

| Endpoint | Phương thức | Chức năng |
|----------|-------------|-----------|
| `/health` | GET | Kiểm tra trạng thái server |
| `/api/llm` | POST | Gọi LLM |
| `/api/tts` | POST | Tổng hợp giọng đọc |
| `/api/image` | POST | Sinh ảnh AI |
| `/api/content/narration` | POST | Sinh narration từ chủ đề |
| `/api/video/generate/sync` | POST | Tạo video (đồng bộ, <30s) |
| `/api/video/generate/async` | POST | Tạo video (bất đồng bộ) |
| `/api/tasks/{task_id}` | GET | Theo dõi tiến độ task |
| `/api/files/{task_id}` | GET | Tải file output |
| `/api/resources` | GET | Liệt kê templates/BGM/workflows |

---

## 🎨 HỆ THỐNG TEMPLATE

### Định Dạng Hỗ Trợ
- **1080×1920** (dọc/portrait) — 21 templates
- **1080×1080** (vuông/square)
- **1920×1080** (ngang/landscape)

### Quy Ước Đặt Tên Template

| Tiền tố | Ý nghĩa |
|---------|---------|
| `static_` | Template tĩnh, **không cần AI** sinh ảnh |
| `image_` | Template cần **AI sinh ảnh** |
| `video_` | Template cần **AI sinh video** |
| `asset_` | Template dùng **tài nguyên có sẵn** |

### Một Số Template Nổi Bật
- `image_default.html` — Template chuẩn, phong cách tối giản
- `image_elegant.html` — Phong cách thanh lịch
- `image_neon.html` — Phong cách neon glow
- `image_book.html` — Phong cách sách
- `static_simple.html` — Nhanh nhất, không cần ComfyUI
- `asset_default.html` — Dành cho AssetBasedPipeline

---

## 🔗 PHỤ THUỘC QUAN TRỌNG

| Thư viện | Phiên bản | Mục đích |
|----------|-----------|---------|
| `comfykit` | ≥0.1.12 | SDK gọi ComfyUI/RunningHub |
| `openai` | ≥2.6.0 | OpenAI SDK (dùng cho mọi LLM) |
| `edge-tts` | 7.2.7 | Microsoft Edge TTS (miễn phí) |
| `playwright` | ≥1.58.0 | Headless browser để render HTML |
| `ffmpeg-python` | ≥0.2.0 | Xử lý video/audio |
| `moviepy` | 1.0.3 | Xử lý video bổ sung |
| `streamlit` | ≥1.40.0 | Web UI |
| `fastapi` | ≥0.115.0 | REST API |
| `pydantic` | ≥2.0.0 | Data validation & config |
| `loguru` | ≥0.7.0 | Logging |
| `pillow` | ≥10.0.0 | Xử lý ảnh |
| `httpx` | ≥0.28.1 | HTTP client async |
| `beautifulsoup4` | ≥4.14.2 | Parse HTML templates |
| `certifi` | ≥2025.10.5 | SSL certificates |
| `fastmcp` | ≥2.0.0 | MCP protocol support |

---

## 📊 LUỒNG XỬ LÝ TỔNG QUAN

```
[Người dùng nhập chủ đề/script]
        │
        ▼
[LLM sinh narration + tiêu đề]
        │
        ▼
[LLM sinh image prompt cho từng cảnh]
        │
        ▼
    ┌───┴───┐
    │       │  (song song nếu RunningHub)
    ▼       ▼
[TTS]   [AI Image/Video]
    │       │
    └───┬───┘
        │
        ▼
[Playwright render HTML → PNG frame]
        │
        ▼
[FFmpeg: image+audio → video segment]
        │
        ▼ (lặp lại cho mỗi cảnh)
[FFmpeg: ghép tất cả segments]
        │
        ▼
[Thêm BGM (tùy chọn)]
        │
        ▼
   [Video hoàn chỉnh 🎬]
```

---
# CHO CHỦ ĐỀ VŨ TRỤ — photorealistic, cinematic
prompt_prefix: "Cinematic photorealistic space scene, 8K ultra-detailed, dramatic lighting, NASA-style imagery, deep space"
## 📜 GIẤY PHÉP

Apache License 2.0 — Xem file `LICENSE` để biết chi tiết.

© 2025 AIDC-AI (Alibaba International Digital Commerce AI)
