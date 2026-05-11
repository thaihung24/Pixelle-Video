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
FlowKit Media Service — Adapter

Sinh ảnh AI bằng cách gọi FlowKit API (port 8100).
FlowKit dùng Chrome Extension làm bridge đến Google Flow (Imagen 3).

Yêu cầu:
    - FlowKit agent đang chạy tại http://127.0.0.1:8100
    - Chrome Extension đang kết nối đến FlowKit (kiểm tra /api/flow/status)

Cách hoạt động:
    1. Gọi POST http://127.0.0.1:8100/api/flow/generate-image với prompt + project_id
    2. FlowKit chuyển tiếp đến Chrome Extension qua WebSocket
    3. Extension gọi Google Flow API với reCAPTCHA + cookie
    4. Trả về image URL (Google Storage signed URL)
    5. Download ảnh về local → trả về đường dẫn file

Config trong config.yaml:
    flowkit:
      enabled: true
      base_url: "http://127.0.0.1:8100"
      project_id: "your-google-flow-project-id"
      orientation: "VERTICAL"          # VERTICAL | HORIZONTAL
      user_paygate_tier: "PAYGATE_TIER_TWO"  # PAYGATE_TIER_ONE | PAYGATE_TIER_TWO
      poll_interval: 3                 # giây giữa các lần poll status
      timeout: 120                     # giây timeout tổng cộng

Ví dụ sử dụng:
    service = FlowKitMediaService(config)
    result = await service(
        prompt="A beautiful mountain landscape at sunset",
        width=1080, height=1920
    )
    print(result.url)       # /path/to/output/image.png
    print(result.is_image)  # True
"""

import asyncio
import os
import uuid
from pathlib import Path
from typing import Optional

import httpx
from loguru import logger

from pixelle_video.models.media import MediaResult


# ── Sentinel cho reCAPTCHA retry ────────────────────────────────────────────
class _CaptchaRetryError(Exception):
    """Raised inside _generate_video_via_flowkit khi gặp reCAPTCHA 403.
    Dùng làm sentinel để vòng lặp ngoài biết cần thử lại từ đầu (kể cả ảnh mồi)."""
    def __init__(self, backoff_seconds: float = 60):
        self.backoff_seconds = backoff_seconds
        super().__init__(f"reCAPTCHA 403 — đã chờ {backoff_seconds}s")

class _TimeoutRetryError(Exception):
    """Raised khi video bị treo chờ quá lâu (15 phút), báo hiệu cần sinh lại từ đầu."""
    pass


# Mapping kích thước → aspect ratio của Google Flow
_ASPECT_RATIO_MAP = {
    # Portrait / Vertical (1080x1920, 768x1024...)
    "portrait":  "IMAGE_ASPECT_RATIO_PORTRAIT",
    "vertical":  "IMAGE_ASPECT_RATIO_PORTRAIT",
    # Landscape / Horizontal (1920x1080, 1280x720...)
    "landscape": "IMAGE_ASPECT_RATIO_LANDSCAPE",
    "horizontal":"IMAGE_ASPECT_RATIO_LANDSCAPE",
    # Square (1080x1080, 1024x1024...)
    "square":    "IMAGE_ASPECT_RATIO_SQUARE",
}


def _resolve_aspect_ratio(width: Optional[int], height: Optional[int], orientation: str) -> str:
    """Tính aspect ratio từ kích thước hoặc orientation config."""
    if width and height:
        ratio = width / height
        if ratio > 1.2:
            return _ASPECT_RATIO_MAP["landscape"]
        elif ratio < 0.85:
            return _ASPECT_RATIO_MAP["portrait"]
        else:
            return _ASPECT_RATIO_MAP["square"]

    # Fallback: dùng orientation từ config
    orientation_lower = orientation.lower()
    return _ASPECT_RATIO_MAP.get(orientation_lower, _ASPECT_RATIO_MAP["portrait"])


def _extract_image_url(response_data: dict) -> Optional[str]:
    """
    Trích xuất URL ảnh từ response của FlowKit /api/flow/generate-image.

    Google Flow trả về nhiều định dạng khác nhau tùy phiên bản:
    - data.media[].name  (media_id, cần gọi /api/flow/media/{id} để lấy URL)
    - data.images[].url  (signed URL trực tiếp)
    - data.fifeUrl       (signed URL)
    - Đôi khi trong data.data.*
    """
    if not response_data:
        return None

    # Thử data.images[].url hoặc data.images[].fifeUrl
    images = response_data.get("images", [])
    if images and isinstance(images, list):
        first = images[0]
        url = first.get("url") or first.get("fifeUrl") or first.get("servingUri")
        if url:
            return url

    # Thử data.media[] (trả về media_id, không phải URL)
    # Đây là format cũ — lưu lại để xử lý trong _download_image
    media_list = response_data.get("media", [])
    if media_list and isinstance(media_list, list):
        first = media_list[0]
        if isinstance(first, dict):
            # Format mới của Google Flow
            gen_image = first.get("image", {}).get("generatedImage", {})
            url = gen_image.get("fifeUrl") or gen_image.get("imageUri")
            if url:
                return url
                
            # Ưu tiên URL nếu có ở cấp trên
            url = first.get("fifeUrl") or first.get("servingUri") or first.get("url")
            if url:
                return url
                
            # Fallback: trả về media_id (có prefix "MEDIA_ID:") để xử lý sau
            name = first.get("name", "")
            if name:
                return f"MEDIA_ID:{name}"

    # Thử trực tiếp
    url = response_data.get("fifeUrl") or response_data.get("servingUri") or response_data.get("url")
    if url:
        return url

    return None


class FlowKitMediaService:
    """
    Media generation service sử dụng FlowKit làm backend.

    Thay thế MediaService (ComfyKit) trong pipeline Pixelle-Video.
    Sinh ảnh bằng Google Imagen 3 (qua Google Flow) thông qua FlowKit.
    """

    def __init__(self, config: dict, core=None):
        """
        Khởi tạo FlowKitMediaService.

        Args:
            config: Full application config dict (từ config.yaml)
            core: PixelleVideoCore instance (không dùng trực tiếp, để tương thích)
        """
        self._config = config
        self._core = core
        self._fk_config = config.get("flowkit", {})

        self.base_url = self._fk_config.get("base_url", "http://127.0.0.1:8100").rstrip("/")
        self.project_id = self._fk_config.get("project_id", "")
        self.orientation = self._fk_config.get("orientation", "VERTICAL")
        self.user_paygate_tier = self._fk_config.get("user_paygate_tier", "PAYGATE_TIER_TWO")
        self.poll_interval = self._fk_config.get("poll_interval", 10)
        self.poll_max_attempts = self._fk_config.get("poll_max_attempts", 50)
        self.timeout = self._fk_config.get("timeout", 120)
        # Character consistency: read default character_media_ids from config
        self.default_character_media_ids = self._fk_config.get("character_media_ids", [])

        char_info = f", characters={len(self.default_character_media_ids)}" if self.default_character_media_ids else ""
        logger.info(
            f"FlowKitMediaService initialized: url={self.base_url}, "
            f"project_id={self.project_id[:12] if self.project_id else 'NOT SET'}, "
            f"orientation={self.orientation}{char_info}"
        )

    async def check_connection(self) -> bool:
        """
        Kiểm tra FlowKit agent và Chrome Extension đang kết nối.

        Returns:
            True nếu extension đang kết nối, False nếu không
        """
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/api/flow/status")
                if resp.status_code == 200:
                    data = resp.json()
                    connected = data.get("connected", False)
                    if not connected:
                        logger.warning(
                            "FlowKit: Chrome Extension chưa kết nối. "
                            "Hãy mở Chrome và đảm bảo extension đang chạy."
                        )
                    return connected
        except Exception as e:
            logger.warning(f"Không thể kết nối đến FlowKit tại {self.base_url}: {e}")
        return False

    async def _sanitize_unsafe_prompt(self, original_prompt: str) -> str:
        """
        Gọi LLM để viết lại prompt bị Google từ chối (UNSAFE_GENERATION).
        Giữ nguyên ý tưởng gốc, chỉ thay các từ/cụm từ nhạy cảm.
        """
        sanitize_prompt = f"""You are a prompt engineer specializing in making AI image/video generation prompts comply with Google's safety policy.

The following prompt was rejected by Google Imagen/Veo with error PUBLIC_ERROR_UNSAFE_GENERATION:

<ORIGINAL_PROMPT>
{original_prompt}
</ORIGINAL_PROMPT>

Your task:
1. Identify which words or phrases likely triggered the safety filter (violence, weapons, political figures, religious content, adult content, dangerous activities, etc.)
2. Rewrite the prompt to preserve the SAME visual concept and artistic intent, but replace or rephrase any problematic elements
3. Keep the same cinematic/artistic style descriptors (lighting, camera angle, resolution tags, etc.)
4. Output ONLY the rewritten prompt text, no explanations, no markdown formatting

Rules for safe prompts:
- Replace specific weapons with abstract/symbolic alternatives
- Replace real/named people with generic descriptions ("a person", "a silhouette", "a figure")
- Replace violent actions with peaceful alternatives that convey similar emotion
- Keep nature, landscapes, abstract art, architecture, science, technology themes as-is
- Use artistic/metaphorical language instead of literal dangerous descriptions

Output ONLY the rewritten prompt:"""

        try:
            from pixelle_video.services.llm_service import LLMService
            llm = LLMService({})
            sanitized = await llm(sanitize_prompt, temperature=0.3, max_tokens=500)
            sanitized = sanitized.strip()

            if not sanitized or len(sanitized) < 20:
                raise ValueError("LLM trả về prompt rỗng")

            logger.info(f"FlowKit: Prompt được viết lại để vượt bộ lọc an toàn:")
            logger.info(f"  Gốc : {original_prompt[:100]}...")
            logger.info(f"  Mới  : {sanitized[:100]}...")
            return sanitized

        except Exception as e:
            logger.error(f"FlowKit: Không thể viết lại prompt: {e}")
            safe_prefix = "Safe, family-friendly, artistic, cinematic illustration. "
            return safe_prefix + original_prompt

    async def _generate_image_via_flowkit(
        self,
        prompt: str,
        aspect_ratio: str,
        character_media_ids: Optional[list] = None,
    ) -> dict:
        """
        Gọi FlowKit API để sinh ảnh.

        Args:
            prompt: Text prompt để sinh ảnh
            aspect_ratio: Google Flow aspect ratio string
            character_media_ids: Danh sách media_id của characters (cho consistency)

        Returns:
            Response data từ FlowKit (đã parse JSON)

        Raises:
            RuntimeError: Nếu FlowKit trả lỗi hoặc timeout
        """
        if not self.project_id:
            raise RuntimeError(
                "FlowKit: project_id chưa được cấu hình. "
                "Thêm 'flowkit.project_id' vào config.yaml. "
                "Bạn có thể lấy project_id bằng cách tạo project trên FlowKit."
            )

        payload = {
            "prompt": prompt,
            "project_id": self.project_id,
            "aspect_ratio": aspect_ratio,
            "user_paygate_tier": self.user_paygate_tier,
        }
        if character_media_ids:
            payload["character_media_ids"] = character_media_ids

        logger.info(f"FlowKit: Gửi yêu cầu sinh ảnh | aspect={aspect_ratio} | prompt={prompt[:60]}...")

        current_prompt = prompt
        for attempt in range(1, 3):  # Tối đa 2 lần: lần 1 gốc, lần 2 đã xử lý
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                payload["prompt"] = current_prompt
                resp = await client.post(
                    f"{self.base_url}/api/flow/generate-image",
                    json=payload,
                )

                if resp.status_code == 503:
                    raise RuntimeError(
                        "FlowKit: Chrome Extension chưa kết nối (503). "
                        "Hãy mở Chrome, đảm bảo extension đang chạy và kết nối đến FlowKit."
                    )

                if resp.status_code == 400:
                    error_text = resp.text
                    if "UNSAFE_GENERATION" in error_text or "PUBLIC_ERROR_UNSAFE" in error_text:
                        if attempt == 1:
                            logger.warning(
                                f"FlowKit: Prompt bị Google từ chối (UNSAFE_GENERATION). "
                                f"Tự động viết lại prompt... (lần thử {attempt + 1})"
                            )
                            current_prompt = await self._sanitize_unsafe_prompt(current_prompt)
                            continue  # Thử lại với prompt mới
                        else:
                            raise RuntimeError(
                                f"FlowKit: Prompt vẫn bị từ chối sau khi đã viết lại. "
                                f"Hãy thay đổi topic hoặc prompt thủ công.\n"
                                f"Prompt đã viết lại: {current_prompt[:200]}"
                            )
                    raise RuntimeError(f"FlowKit API lỗi {resp.status_code}: {error_text[:300]}")

                if resp.status_code == 403:
                    error_text = resp.text
                    if "reCAPTCHA" in error_text or "UNUSUAL_ACTIVITY" in error_text:
                        _captcha_retries = getattr(self, "_img_captcha_retries", 0)
                        _max_captcha = 5
                        if _captcha_retries < _max_captcha:
                            _captcha_retries += 1
                            self._img_captcha_retries = _captcha_retries
                            backoff = min(60 * (2 ** (_captcha_retries - 1)), 600)
                            logger.warning(
                                f"🚫 reCAPTCHA/403 khi sinh ảnh (lần {_captcha_retries}/{_max_captcha}). "
                                f"Chờ {backoff}s rồi thử lại... "
                                f"Trong lúc chờ: vào https://labs.google/fx/tools/image-fx và xác minh CAPTCHA."
                            )
                            await asyncio.sleep(backoff)
                            continue  # Thử lại vòng lặp attempt
                        else:
                            self._img_captcha_retries = 0  # Reset cho lần sau
                            raise RuntimeError(
                                "🚫 FlowKit: Bị Google chặn vì reCAPTCHA (Lỗi 403)!\n"
                                "👉 CÁCH XỬ LÝ:\n"
                                "1. Mở Chrome (nơi cài Extension FlowKit).\n"
                                "2. Vào trang: https://labs.google/fx/tools/image-fx\n"
                                "3. Gõ đại 1 chữ vào ô prompt rồi bấm Generate.\n"
                                "4. Google sẽ hiện bảng reCAPTCHA -> Bấm xác nhận.\n"
                                "5. Đợi sinh ảnh xong 1 lần -> Quay lại tool bấm Generate tiếp."
                            )
                    raise RuntimeError(f"FlowKit API lỗi {resp.status_code}: {error_text[:300]}")

                if resp.status_code != 200:
                    raise RuntimeError(f"FlowKit API lỗi {resp.status_code}: {resp.text[:300]}")

                # Reset captcha retry counter on success
                self._img_captcha_retries = 0
                return resp.json()

        raise RuntimeError("FlowKit: Không thể sinh ảnh sau 2 lần thử.")

    async def _generate_video_via_flowkit(
        self,
        prompt: str,
        aspect_ratio: str,
        character_media_ids: Optional[list] = None,
    ) -> str:
        """
        Gọi FlowKit API để sinh video (Veo). Trả về URL của video đã hoàn thành.
        1. Sinh ảnh mồi (with character_media_ids for consistency)
        2. Sinh video từ ảnh mồi
        3. Polling cho đến khi xong
        Có retry với exponential backoff khi Google trả reCAPTCHA/403, và retry khi Timeout.
        """
        _MAX_RETRIES = 5
        for _vid_outer_attempt in range(1, _MAX_RETRIES + 2):
            try:
                return await self._generate_video_via_flowkit_once(prompt, aspect_ratio, character_media_ids)
            except _CaptchaRetryError as exc:
                if _vid_outer_attempt <= _MAX_RETRIES:
                    logger.warning(
                        f"🔄 Video CAPTCHA retry {_vid_outer_attempt}/{_MAX_RETRIES}: "
                        f"đã chờ xong, thử lại ảnh mồi và video cho cảnh này..."
                    )
                    continue
                raise RuntimeError(
                    "🚫 FlowKit: Đã thử lại 5 lần vẫn bị Google chặn vì reCAPTCHA!\n"
                    "Hãy xác minh CAPTCHA thủ công rồi chạy lại pipeline."
                ) from exc
            except _TimeoutRetryError as exc:
                if _vid_outer_attempt <= _MAX_RETRIES:
                    logger.warning(
                        f"⏳ Video Timeout retry {_vid_outer_attempt}/{_MAX_RETRIES}: "
                        f"Quá thời gian chờ (15 phút), tiến hành tạo lại ảnh mồi và video cho riêng cảnh này..."
                    )
                    continue
                raise RuntimeError(
                    "🚫 FlowKit: Đã thử lại 5 lần nhưng sinh video vẫn bị timeout (quá 15 phút)!"
                ) from exc
        raise RuntimeError("FlowKit: Không thể sinh video sau nhiều lần thử.")

    async def _generate_video_via_flowkit_once(
        self,
        prompt: str,
        aspect_ratio: str,
        character_media_ids: Optional[list] = None,
    ) -> str:
        """Một lần thử sinh video (ảnh mồi + video). Raise _CaptchaRetryError nếu gặp CAPTCHA."""
        # Pass character_media_ids to seed image generation for character consistency
        img_resp = await self._generate_image_via_flowkit(prompt, aspect_ratio, character_media_ids)
        
        # Format trả về thường có media[0].name
        media_id = None
        media_list = img_resp.get("media", [])
        if media_list and isinstance(media_list, list):
            first = media_list[0]
            if isinstance(first, dict):
                media_id = first.get("name")
            else:
                media_id = str(first)
                
        if not media_id:
            logger.error(f"FlowKit: Không tìm thấy media_id trong response ảnh: {img_resp}")
            raise RuntimeError("FlowKit: Không thể trích xuất media_id từ ảnh mồi để làm video.")
            
        logger.info(f"FlowKit (Video): Ảnh mồi thành công (media_id: {media_id[:16]}...). Bắt đầu sinh video...")
        
        # Convert aspect_ratio (IMAGE_ASPECT_RATIO_PORTRAIT -> VIDEO_ASPECT_RATIO_PORTRAIT)
        video_aspect_ratio = aspect_ratio.replace("IMAGE_", "VIDEO_")
        
        # 2. Gọi API sinh video
        video_payload = {
            "start_image_media_id": media_id,
            "prompt": prompt,
            "project_id": self.project_id,
            "scene_id": f"scene_{uuid.uuid4().hex[:8]}",
            "aspect_ratio": video_aspect_ratio,
            "user_paygate_tier": self.user_paygate_tier,
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/flow/generate-video",
                json=video_payload,
            )
            
            if resp.status_code == 403:
                error_text = resp.text
                if "reCAPTCHA" in error_text or "UNUSUAL_ACTIVITY" in error_text:
                    _vid_captcha_retries = getattr(self, "_vid_captcha_retries", 0)
                    _max_captcha = 5
                    if _vid_captcha_retries < _max_captcha:
                        _vid_captcha_retries += 1
                        self._vid_captcha_retries = _vid_captcha_retries
                        backoff = min(60 * (2 ** (_vid_captcha_retries - 1)), 600)
                        logger.warning(
                            f"🚫 reCAPTCHA/403 khi sinh video (lần {_vid_captcha_retries}/{_max_captcha}). "
                            f"Chờ {backoff}s rồi thử lại toàn bộ (ảnh mồi + video)... "
                            f"Trong lúc chờ: vào https://labs.google/fx/tools/video-fx và xác minh CAPTCHA."
                        )
                        await asyncio.sleep(backoff)
                        # Re-raise as special sentinel để caller có thể retry toàn bộ pipeline
                        raise _CaptchaRetryError(backoff)
                    else:
                        self._vid_captcha_retries = 0  # Reset cho lần sau
                        raise RuntimeError(
                            "🚫 FlowKit: Bị Google chặn vì reCAPTCHA (Lỗi 403 khi làm video)!\n"
                            "👉 CÁCH XỬ LÝ:\n"
                            "1. Mở Chrome (nơi cài Extension FlowKit).\n"
                            "2. Vào trang: https://labs.google/fx/tools/video-fx\n"
                            "3. Bấm Generate 1 video bất kỳ để xác minh reCAPTCHA.\n"
                            "4. Quay lại đây bấm Generate tiếp."
                        )
                raise RuntimeError(f"FlowKit API lỗi {resp.status_code} khi gọi generate-video: {error_text[:300]}")

            if resp.status_code != 200:
                raise RuntimeError(f"FlowKit API lỗi {resp.status_code} khi gọi generate-video: {resp.text[:300]}")
                
            video_data = resp.json()
            
        video_media_list = video_data.get("media", [])
        video_media_id = None
        if video_media_list and isinstance(video_media_list, list):
            first = video_media_list[0]
            if isinstance(first, dict):
                video_media_id = first.get("name")
            else:
                video_media_id = str(first)
                
        if not video_media_id:
            # Fallback to operations if available (older API version)
            operations = video_data.get("operations", [])
            if operations:
                # Trích xuất URL từ operation luôn nếu có thể
                pass # Để tương thích ngược, nhưng ưu tiên media_id
            raise RuntimeError(f"FlowKit API không trả về media id cho video: {video_data}")
            
        logger.info(f"FlowKit (Video): Đã submit job video (media_id: {video_media_id[:16]}...). Bắt đầu chờ (polling)...")
        
        # 3. Polling — Google Veo thường mất một lúc mỗi video
        max_attempts = self.poll_max_attempts
        for attempt in range(max_attempts):
            await asyncio.sleep(self.poll_interval)
            
            try:
                # Sử dụng _resolve_media_id_to_url để poll status
                video_url = await self._resolve_media_id_to_url(video_media_id)
                if video_url:
                    logger.info(f"FlowKit (Video): Sinh video 720p hoàn tất!")
                    
                    # 4. Upscale to 1080p + download via CDN
                    try:
                        upscaled_path = await self._upscale_and_download_cdn(video_media_id)
                        if upscaled_path:
                            logger.success(f"FlowKit (Video): Upscale 1080p + CDN download thành công!")
                            return upscaled_path
                    except Exception as e:
                        logger.warning(f"FlowKit (Video): Upscale/CDN failed ({e}), using 720p fallback")
                    
                    return video_url
            except Exception as e:
                logger.warning(f"FlowKit (Video): Lỗi kết nối khi poll status: {e}")
                
            if attempt % 20 == 0 and attempt > 0:
                waited_sec = attempt * self.poll_interval
                remaining_sec = (max_attempts - attempt) * self.poll_interval
                logger.debug(f"FlowKit (Video): Đang xử lý... (đã chờ {waited_sec}s / còn tối đa {remaining_sec}s)")
                
        raise _TimeoutRetryError("FlowKit (Video): Timeout chờ sinh video.")
    
    async def _upscale_and_download_cdn(self, media_id: str, timeout: int = 180) -> Optional[str]:
        """
        Upscale video to 1080p and download via CDN.
        
        1080p upscale requires an explicit API call (batchAsyncGenerateVideoUpsampleVideo)
        but is FREE for unlimited accounts (PAYGATE_TIER_TWO).
        Only 4K upscale costs 50 credits.
        
        Flow: Submit upscale (1080p) → Poll _upsampled → Download via CDN
        
        Args:
            media_id: Original 720p video media_id
            timeout: Max seconds to wait for upscale to complete
        Returns:
            Local file path of 1080p video, or None if failed
        """
        upsampled_media_id = f"{media_id}_upsampled"
        logger.info(f"FlowKit (1080p): Submitting 1080p upscale for {media_id[:16]}...")
        
        # Step 1: Submit upscale request via FlowKit Agent
        # Uses VIDEO_RESOLUTION_1080P + veo_3_1_upsampler_1080p → FREE for PAYGATE_TIER_TWO
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                upscale_resp = await client.post(
                    f"{self.base_url}/api/flow/upscale-video",
                    json={
                        "media_id": media_id,
                        "scene_id": "upscale_cdn",
                        "aspect_ratio": "VIDEO_ASPECT_RATIO_LANDSCAPE",
                        "resolution": "VIDEO_RESOLUTION_1080P"
                    }
                )
            
            if upscale_resp.status_code not in (200, 201, 202):
                logger.warning(f"FlowKit (1080p): Submit failed (HTTP {upscale_resp.status_code}): {upscale_resp.text[:200]}")
                return None
            
            logger.info(f"FlowKit (1080p): Upscale job submitted OK, polling for {upsampled_media_id[:20]}...")
        except Exception as e:
            logger.warning(f"FlowKit (1080p): Submit error: {e}")
            return None
        
        # Step 2: Poll until 1080p upsampled version is ready
        # Note: Google Flow returns video.encodedVideo (base64) when ready,
        # and may NOT include mediaStatus at all for upsampled media.
        poll_interval = 10
        max_polls = timeout // poll_interval
        upscaled_data = None
        
        for attempt in range(max_polls):
            await asyncio.sleep(poll_interval)
            
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    status_resp = await client.get(
                        f"{self.base_url}/api/flow/media/{upsampled_media_id}"
                    )
                if status_resp.status_code == 200:
                    data = status_resp.json()
                    
                    # Check 1: video.encodedVideo present = READY (primary check)
                    encoded_video = data.get("video", {}).get("encodedVideo", "")
                    if encoded_video and len(encoded_video) > 1000:
                        logger.info(f"FlowKit (1080p): Ready (base64 data) after {(attempt+1)*poll_interval}s!")
                        upscaled_data = data
                        break
                    
                    # Check 2: mediaStatus (may exist for some responses)
                    gen_status = data.get("mediaStatus", {}).get("mediaGenerationStatus", "")
                    if gen_status == "MEDIA_GENERATION_STATUS_SUCCESSFUL":
                        logger.info(f"FlowKit (1080p): Ready (status=SUCCESSFUL) after {(attempt+1)*poll_interval}s!")
                        upscaled_data = data
                        break
                    elif gen_status == "MEDIA_GENERATION_STATUS_FAILED":
                        logger.warning(f"FlowKit (1080p): Google upscale FAILED for {media_id[:16]}")
                        return None
                    
                    # Check 3: fifeUrl present = READY (CDN URL available)
                    if data.get("fifeUrl") or data.get("servingUri"):
                        logger.info(f"FlowKit (1080p): Ready (has URL) after {(attempt+1)*poll_interval}s!")
                        upscaled_data = data
                        break
                    
                    if attempt % 3 == 0:
                        logger.debug(f"FlowKit (1080p): Processing... ({(attempt+1)*poll_interval}s)")
                elif status_resp.status_code == 404:
                    if attempt % 3 == 0:
                        logger.debug(f"FlowKit (1080p): Not available yet ({(attempt+1)*poll_interval}s)")
            except Exception as e:
                logger.debug(f"FlowKit (1080p): Poll error (attempt {attempt}): {e}")
        
        if not upscaled_data:
            logger.warning(f"FlowKit (1080p): Timeout after {timeout}s, using 720p fallback")
            return None
        
        # Step 3: Save 1080p video — prefer base64 data (already in response), fallback to CDN
        from pixelle_video.utils.os_util import get_output_path
        abs_output_dir = os.path.dirname(get_output_path("dummy.mp4"))
        os.makedirs(abs_output_dir, exist_ok=True)
        cdn_filename = f"flowkit_{media_id[:16]}_1080p.mp4"
        local_path = os.path.join(abs_output_dir, cdn_filename)
        
        # Try base64 first (fastest — data already in memory)
        encoded_video = upscaled_data.get("video", {}).get("encodedVideo", "")
        if encoded_video and len(encoded_video) > 1000:
            try:
                import base64
                video_bytes = base64.b64decode(encoded_video)
                with open(local_path, "wb") as f:
                    f.write(video_bytes)
                file_size = os.path.getsize(local_path)
                logger.success(f"FlowKit (1080p): Saved from base64 → {local_path} ({file_size / 1024 / 1024:.1f} MB)")
                return local_path
            except Exception as e:
                logger.warning(f"FlowKit (1080p): Base64 decode failed ({e}), trying CDN...")
        
        # Fallback: Download via CDN
        try:
            async with httpx.AsyncClient(timeout=180) as client:
                cdn_resp = await client.get(
                    f"{self.base_url}/api/flow/media/{upsampled_media_id}/download-cdn",
                    params={
                        "media_type": "video",
                        "output_dir": abs_output_dir,
                        "filename": cdn_filename,
                    },
                )
            if cdn_resp.status_code == 200:
                cdn_data = cdn_resp.json()
                local_path = cdn_data.get("path")
                file_size = cdn_data.get("size", 0)
                logger.success(f"FlowKit (CDN): Downloaded 1080p → {local_path} ({file_size / 1024 / 1024:.1f} MB)")
                return local_path
            else:
                logger.warning(f"FlowKit (CDN): Download failed (HTTP {cdn_resp.status_code}): {cdn_resp.text[:200]}")
        except Exception as e:
            logger.warning(f"FlowKit (CDN): Download error: {e}")
        
        return None

    async def _resolve_media_id_to_url(self, media_id: str) -> Optional[str]:
        """
        Lấy URL thực từ media_id qua FlowKit /api/flow/media/{id}.

        Args:
            media_id: Google Flow media_id (UUID)

        Returns:
            Signed URL của ảnh hoặc None nếu không lấy được
        """
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(f"{self.base_url}/api/flow/media/{media_id}")
                if resp.status_code == 200:
                    data = resp.json()
                    
                    # 0. Kiểm tra trạng thái xem đã xong chưa
                    status = data.get("mediaStatus", {}).get("mediaGenerationStatus")
                    if status == "MEDIA_GENERATION_STATUS_FAILED":
                        raise RuntimeError(f"Google báo lỗi sinh media (FAILED) cho media_id: {media_id}")
                    if status and status != "MEDIA_GENERATION_STATUS_SUCCESSFUL":
                        # Vẫn đang SCHEDULED hoặc PROCESSING
                        return None
                    
                    # 1. Trả về dạng file local nếu Veo trả về base64 (encodedVideo)
                    encoded_video = data.get("video", {}).get("encodedVideo")
                    if encoded_video and len(encoded_video) > 100000:  # Đảm bảo đây là video thật (>100KB), không phải metadata
                        import base64
                        from pixelle_video.utils.os_util import get_output_path
                        filename = f"flowkit_{media_id[:16]}.mp4"
                        output_path = get_output_path(filename)
                        os.makedirs(os.path.dirname(output_path), exist_ok=True)
                        with open(output_path, "wb") as f:
                            f.write(base64.b64decode(encoded_video))
                        logger.debug(f"Resolved media_id {media_id[:16]}... → Local Base64 File")
                        return output_path
                        
                    # 2. Trả về URL nếu ImageFX/VideoFX trả về URL (fifeUrl)
                    url = data.get("fifeUrl") or data.get("servingUri") or data.get("url")
                    if url:
                        logger.debug(f"Resolved media_id {media_id[:16]}... → URL")
                        return url
        except Exception as e:
            logger.warning(f"Không thể resolve media_id {media_id[:16]}: {e}")
        return None

    async def _download_media(self, media_url: str, output_path: Optional[str] = None, media_type: str = "image") -> str:
        """
        Download media từ URL về local file.

        Args:
            media_url: URL của file
            output_path: Đường dẫn lưu file (tự động tạo nếu None)
            media_type: "image" hoặc "video"

        Returns:
            Đường dẫn file đã download
        """
        # Tạo output path nếu chưa có
        if output_path is None:
            from pixelle_video.utils.os_util import get_output_path
            ext = ".mp4" if media_type == "video" else ".png"
            filename = f"flowkit_{uuid.uuid4().hex[:16]}{ext}"
            output_path = get_output_path(filename)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Nếu media_url đã là file local (được lưu trước đó từ base64)
        if media_url.startswith("file://"):
            media_url = media_url.replace("file://", "")
        if os.path.isabs(media_url) and os.path.exists(media_url):
            if output_path != media_url:
                import shutil
                shutil.copy2(media_url, output_path)
            file_size = os.path.getsize(output_path)
            logger.success(f"✅ FlowKit: {media_type.capitalize()} đã lưu sẵn ({file_size // 1024}KB) → {output_path}")
            return output_path

        logger.info(f"FlowKit: Downloading {media_type} về {output_path}...")

        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            resp = await client.get(media_url)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Không thể download {media_type} từ FlowKit: HTTP {resp.status_code}"
                )
            with open(output_path, "wb") as f:
                f.write(resp.content)

        file_size = os.path.getsize(output_path)
        logger.success(f"✅ FlowKit: {media_type.capitalize()} đã lưu ({file_size // 1024}KB) → {output_path}")
        return output_path

    async def __call__(
        self,
        prompt: str,
        media_type: str = "image",
        width: Optional[int] = None,
        height: Optional[int] = None,
        output_path: Optional[str] = None,
        character_media_ids: Optional[list] = None,
        # Các tham số tương thích với MediaService interface (bỏ qua)
        workflow: Optional[str] = None,
        comfyui_url: Optional[str] = None,
        runninghub_api_key: Optional[str] = None,
        duration: Optional[float] = None,
        negative_prompt: Optional[str] = None,
        steps: Optional[int] = None,
        seed: Optional[int] = None,
        cfg: Optional[float] = None,
        sampler: Optional[str] = None,
        **kwargs,
    ) -> MediaResult:
        """
        Sinh ảnh AI thông qua FlowKit → Google Imagen 3.

        Interface tương thích với MediaService để có thể hoán đổi trực tiếp.

        Args:
            prompt: Text prompt để sinh ảnh
            media_type: Chỉ hỗ trợ "image" (FlowKit không sinh video cho Pixelle pipeline)
            width: Chiều rộng ảnh mong muốn (dùng để xác định aspect ratio)
            height: Chiều cao ảnh mong muốn (dùng để xác định aspect ratio)
            output_path: Đường dẫn lưu ảnh (tự động nếu None)
            character_media_ids: Media IDs của characters cho consistency
            workflow/comfyui_url/...: Bỏ qua (tương thích interface)

        Returns:
            MediaResult với media_type="image" và url=đường dẫn file local

        Raises:
            RuntimeError: Nếu FlowKit không khả dụng hoặc sinh ảnh thất bại
            NotImplementedError: Nếu media_type="video" (chưa hỗ trợ)
        """
        if media_type not in ("image", "video"):
            raise NotImplementedError(f"FlowKitMediaService chưa hỗ trợ media_type={media_type}")

        # 1. Kiểm tra kết nối
        if not await self.check_connection():
            raise RuntimeError(
                "FlowKit không khả dụng. Kiểm tra:\n"
                "  1. FlowKit agent đang chạy: cd /Applications/STUDY/flowkit && python -m agent.main\n"
                "  2. Chrome Extension đang kết nối đến FlowKit\n"
                f"  3. FlowKit URL: {self.base_url}"
            )

        # 2. Xác định aspect ratio
        aspect_ratio = _resolve_aspect_ratio(width, height, self.orientation)
        logger.debug(f"FlowKit: aspect_ratio={aspect_ratio} (w={width}, h={height}, orientation={self.orientation})")

        # 3. Gọi FlowKit API để sinh ảnh hoặc video
        # Merge character_media_ids: explicit arg > config default
        effective_char_ids = character_media_ids or self.default_character_media_ids or None
        if effective_char_ids:
            logger.info(f"FlowKit: Using {len(effective_char_ids)} character reference(s) for consistency")

        if media_type == "video":
            media_url = await self._generate_video_via_flowkit(
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                character_media_ids=effective_char_ids,
            )
        else:
            response_data = await self._generate_image_via_flowkit(
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                character_media_ids=effective_char_ids,
            )

            # 4. Trích xuất URL ảnh từ response
            media_url = _extract_image_url(response_data)

            if not media_url:
                logger.error(f"FlowKit response không có URL: {str(response_data)[:500]}")
                raise RuntimeError(
                    "FlowKit trả về response nhưng không tìm thấy URL ảnh. "
                    "Kiểm tra logs của FlowKit agent."
                )

            # 5. Nếu chỉ có media_id (không có URL trực tiếp), resolve sang URL
            if media_url.startswith("MEDIA_ID:"):
                media_id = media_url[len("MEDIA_ID:"):]
                logger.info(f"FlowKit: Resolving media_id={media_id[:16]}... sang URL")
                resolved_url = await self._resolve_media_id_to_url(media_id)
                if not resolved_url:
                    raise RuntimeError(
                        f"FlowKit: Không thể lấy URL từ media_id {media_id[:16]}. "
                        "Extension cần mở project trong Chrome để refresh URLs."
                    )
                media_url = resolved_url

        # 6. Download media về local
        local_path = await self._download_media(media_url, output_path, media_type=media_type)

        return MediaResult(
            media_type=media_type,
            url=local_path,
        )

    def list_workflows(self) -> list:
        """Tương thích interface MediaService — trả về danh sách rỗng."""
        return [{"key": "flowkit/google-imagen-3", "source": "flowkit", "name": "Google Imagen 3 (via FlowKit)", "display_name": "Google Imagen 3 (via FlowKit)"}]

    @property
    def default_workflow(self) -> str:
        return "flowkit/google-imagen-3"
