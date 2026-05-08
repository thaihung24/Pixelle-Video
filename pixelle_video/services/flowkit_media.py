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
        self.poll_interval = self._fk_config.get("poll_interval", 3)
        self.timeout = self._fk_config.get("timeout", 120)

        logger.info(
            f"FlowKitMediaService initialized: url={self.base_url}, "
            f"project_id={self.project_id[:12] if self.project_id else 'NOT SET'}, "
            f"orientation={self.orientation}"
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

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/flow/generate-image",
                json=payload,
            )

            if resp.status_code == 503:
                raise RuntimeError(
                    "FlowKit: Chrome Extension chưa kết nối (503). "
                    "Hãy mở Chrome, đảm bảo extension đang chạy và kết nối đến FlowKit."
                )

            if resp.status_code != 200:
                error_detail = resp.text[:300]
                raise RuntimeError(
                    f"FlowKit API lỗi {resp.status_code}: {error_detail}"
                )

            return resp.json()

    async def _generate_video_via_flowkit(
        self,
        prompt: str,
        aspect_ratio: str,
    ) -> str:
        """
        Gọi FlowKit API để sinh video (Veo). Trả về URL của video đã hoàn thành.
        1. Sinh ảnh mồi
        2. Sinh video từ ảnh mồi
        3. Polling cho đến khi xong
        """
        # 1. Sinh ảnh mồi
        logger.info(f"FlowKit (Video): Bắt đầu sinh ảnh mồi cho video...")
        img_resp = await self._generate_image_via_flowkit(prompt, aspect_ratio)
        
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
            
            if resp.status_code != 200:
                raise RuntimeError(f"FlowKit API lỗi {resp.status_code} khi gọi generate-video: {resp.text[:300]}")
                
            video_data = resp.json()
            
        operations = video_data.get("operations", [])
        if not operations:
            raise RuntimeError(f"FlowKit API không trả về operations cho video: {video_data}")
            
        logger.info(f"FlowKit (Video): Đã submit job video. Bắt đầu chờ (polling)...")
        
        # 3. Polling
        max_attempts = 120 # 6 phút
        for attempt in range(max_attempts):
            await asyncio.sleep(self.poll_interval)
            
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    poll_resp = await client.post(
                        f"{self.base_url}/api/flow/check-status",
                        json={"operations": operations}
                    )
                    
                    if poll_resp.status_code != 200:
                        logger.warning(f"FlowKit (Video): Lỗi HTTP {poll_resp.status_code} khi poll status")
                        continue
                        
                    poll_data = poll_resp.json()
            except Exception as e:
                logger.warning(f"FlowKit (Video): Lỗi kết nối khi poll status: {e}")
                continue

            # Unwrap nếu có wrapper {"data": ...}
            actual_data = poll_data.get("data", poll_data)
            
            # Format thực tế: {"operations": [{status: "...", operation: {metadata: {video: {fifeUrl: ...}}}}]}
            ops = actual_data.get("operations", [])
            
            if ops:
                logger.debug(f"FlowKit (Video): Poll response - {len(ops)} operations, status[0]={ops[0].get('status', 'N/A')}")
                
                all_done = True
                has_error = False
                
                for op in ops:
                    status = op.get("status", "")
                    if status == "MEDIA_GENERATION_STATUS_SUCCESSFUL":
                        continue
                    elif status == "MEDIA_GENERATION_STATUS_FAILED":
                        has_error = True
                        raise RuntimeError(f"FlowKit (Video): Google Labs báo lỗi sinh video: {op}")
                    else:
                        all_done = False  # Còn đang xử lý
                
                if all_done and not has_error:
                    # Lấy URL video từ operation đầu tiên
                    op_meta = ops[0].get("operation", {}).get("metadata", {})
                    video_meta = op_meta.get("video", {})
                    video_url = (
                        video_meta.get("fifeUrl") or
                        video_meta.get("servingUri") or
                        video_meta.get("url") or
                        ops[0].get("fifeUrl") or
                        ops[0].get("url")
                    )
                    if video_url:
                        logger.info(f"FlowKit (Video): Sinh video hoàn tất!")
                        return video_url
                    else:
                        logger.warning(f"FlowKit (Video): Status SUCCESSFUL nhưng không tìm thấy URL. Op data: {str(ops[0])[:300]}")

            if attempt % 5 == 0:
                logger.debug(f"FlowKit (Video): Đang xử lý... (chờ {attempt * self.poll_interval}s)")
                
        raise RuntimeError("FlowKit (Video): Timeout chờ sinh video.")

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
        if media_type == "video":
            media_url = await self._generate_video_via_flowkit(
                prompt=prompt,
                aspect_ratio=aspect_ratio,
            )
        else:
            response_data = await self._generate_image_via_flowkit(
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                character_media_ids=character_media_ids,
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
