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
Asset-Based Pipeline UI

Implements the UI for generating videos from user-provided assets.
"""

import os
import time
from pathlib import Path
from typing import Any

import streamlit as st
from loguru import logger

from web.i18n import tr, get_language
from web.pipelines.base import PipelineUI, register_pipeline_ui
from web.components.content_input import render_bgm_section, render_version_info
from web.utils.async_helpers import run_async
from web.utils.streamlit_helpers import check_and_warn_selfhost_workflow
from pixelle_video.config import config_manager
from pixelle_video.models.progress import ProgressEvent


class AssetBasedPipelineUI(PipelineUI):
    """
    UI for the Asset-Based Video Generation Pipeline.
    Generates videos from user-provided assets (images/videos).
    """
    name = "custom_media"
    icon = "🎨"
    
    @property
    def display_name(self):
        return tr("pipeline.custom_media.name")
    
    @property
    def description(self):
        return tr("pipeline.custom_media.description")
    
    def render(self, pixelle_video: Any):
        # Three-column layout
        left_col, middle_col, right_col = st.columns([1, 1, 1])
        
        # ====================================================================
        # Left Column: Asset Upload & Video Info
        # ====================================================================
        with left_col:
            asset_params = self._render_asset_input()
            bgm_params = render_bgm_section(key_prefix="asset_")
            render_version_info()
        
        # ====================================================================
        # Middle Column: Video Configuration
        # ====================================================================
        with middle_col:
            config_params = self._render_video_config(pixelle_video)
        
        # ====================================================================
        # Right Column: Output Preview
        # ====================================================================
        with right_col:
            # Combine all parameters
            video_params = {
                "pipeline": self.name,
                **asset_params,
                **bgm_params,
                **config_params
            }
            
            self._render_output_preview(pixelle_video, video_params)
    
    def _render_asset_input(self) -> dict:
        """Render asset upload section"""
        with st.container(border=True):
            st.markdown(f"**{tr('asset_based.section.assets')}**")
            
            with st.expander(tr("help.feature_description"), expanded=False):
                st.markdown(f"**{tr('help.what')}**")
                st.markdown(tr("asset_based.assets.what"))
                st.markdown(f"**{tr('help.how')}**")
                st.markdown(tr("asset_based.assets.how"))
            
            # File uploader for multiple files
            uploaded_files = st.file_uploader(
                tr("asset_based.assets.upload"),
                type=["jpg", "jpeg", "png", "gif", "webp", "mp4", "mov", "avi", "mkv", "webm"],
                accept_multiple_files=True,
                help=tr("asset_based.assets.upload_help"),
                key="asset_files"
            )
            
            # Save uploaded files to temp directory with unique session ID
            asset_paths = []
            if uploaded_files:
                import uuid
                session_id = str(uuid.uuid4()).replace('-', '')[:12]
                temp_dir = Path(f"temp/assets_{session_id}")
                temp_dir.mkdir(parents=True, exist_ok=True)
                
                for uploaded_file in uploaded_files:
                    file_path = temp_dir / uploaded_file.name
                    with open(file_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    asset_paths.append(str(file_path.absolute()))
                
                st.success(tr("asset_based.assets.count", count=len(asset_paths)))
                
                # Preview uploaded assets
                with st.expander(tr("asset_based.assets.preview"), expanded=True):
                    # Show in a grid (3 columns)
                    cols = st.columns(3)
                    for i, (file, path) in enumerate(zip(uploaded_files, asset_paths)):
                        with cols[i % 3]:
                            # Check if image or video
                            ext = Path(path).suffix.lower()
                            if ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
                                st.image(file, caption=file.name, use_container_width=True)
                            elif ext in [".mp4", ".mov", ".avi", ".mkv", ".webm"]:
                                st.video(file)
                                st.caption(file.name)
            else:
                st.info(tr("asset_based.assets.empty_hint"))
        
        # Video title & intent
        with st.container(border=True):
            st.markdown(f"**{tr('asset_based.section.video_info')}**")
            
            video_title = st.text_input(
                tr("asset_based.video_title"),
                placeholder=tr("asset_based.video_title_placeholder"),
                help=tr("asset_based.video_title_help"),
                key="asset_video_title"
            )
            
            intent = st.text_area(
                tr("asset_based.intent"),
                placeholder=tr("asset_based.intent_placeholder"),
                help=tr("asset_based.intent_help"),
                height=100,
                key="asset_intent"
            )
        
        return {
            "assets": asset_paths,
            "video_title": video_title,
            "intent": intent if intent else None
        }
    
    def _render_video_config(self, pixelle_video: Any) -> dict:
        """Render video configuration section"""
        # Duration configuration
        with st.container(border=True):
            st.markdown(f"**{tr('video.title')}**")
            
            # Duration slider
            duration = st.slider(
                tr("asset_based.duration"),
                min_value=15,
                max_value=120,
                value=30,
                step=5,
                help=tr("asset_based.duration_help"),
                key="asset_duration"
            )
            st.caption(tr("asset_based.duration_label", seconds=duration))
        
        # Workflow source selection
        with st.container(border=True):
            st.markdown(f"**{tr('asset_based.section.source')}**")
            
            with st.expander(tr("help.feature_description"), expanded=False):
                st.markdown(f"**{tr('help.what')}**")
                st.markdown(tr("asset_based.source.what"))
                st.markdown(f"**{tr('help.how')}**")
                st.markdown(tr("asset_based.source.how"))
            
            source_options = {
                "runninghub": "☁️ RunningHub (Cloud)",
                "selfhost": "🖥️ SelfHost (Local)",
                "flowkit": "🎬 FlowKit / Google Veo 3"
            }
            
            # Check if RunningHub API key is configured
            comfyui_config = config_manager.get_comfyui_config()
            has_runninghub = bool(comfyui_config.get("runninghub_api_key"))
            has_selfhost = bool(comfyui_config.get("comfyui_url"))

            # Check if FlowKit is configured
            flowkit_config = config_manager.config.flowkit if hasattr(config_manager.config, 'flowkit') else {}
            has_flowkit = bool(
                (flowkit_config.get("base_url") if isinstance(flowkit_config, dict) else getattr(flowkit_config, 'base_url', None))
            )
            
            # Default to runninghub always
            default_source_index = 0
            
            source = st.radio(
                tr("asset_based.source.select"),
                options=list(source_options.keys()),
                format_func=lambda x: source_options[x],
                index=default_source_index,
                horizontal=True,
                key="asset_source",
                label_visibility="collapsed"
            )
            
            # Show hint based on selection
            if source == "runninghub":
                if not has_runninghub:
                    st.warning(tr("asset_based.source.runninghub_not_configured"))
                else:
                    st.info(tr("asset_based.source.runninghub_hint"))
            elif source == "flowkit":
                st.info("🎬 Google Veo 3 qua FlowKit — sinh video chuyển động AI cho từng cảnh.")
                if not has_flowkit:
                    st.warning("⚠️ FlowKit chưa được cấu hình. Vào System Configuration để nhập FlowKit URL.")
                # Workflow selector for FlowKit video
                all_workflows = pixelle_video.media.list_workflows()
                veo_workflows = [
                    wf for wf in all_workflows
                    if "flowkit" in wf["key"].lower() or "veo" in wf["key"].lower() or "video" in wf["key"].lower()
                ]
                if not veo_workflows:
                    # Fallback: add default FlowKit workflow
                    veo_workflows = [{"key": "flowkit/google-veo", "display_name": "Google Veo (FlowKit)"}]
                
                veo_wf_labels = [wf["display_name"] for wf in veo_workflows]
                veo_wf_keys   = [wf["key"]          for wf in veo_workflows]
                selected_veo_wf = st.selectbox(
                    "Video Workflow",
                    veo_wf_labels,
                    index=0,
                    key="asset_veo_workflow"
                )
                veo_workflow_key = veo_wf_keys[veo_wf_labels.index(selected_veo_wf)]
                st.session_state["asset_flowkit_workflow"] = veo_workflow_key
            else:
                if not has_selfhost:
                    st.warning(tr("asset_based.source.selfhost_not_configured"))
                else:
                    st.info(tr("asset_based.source.selfhost_hint"))
                    # Check and warn for selfhost mode (auto popup if not confirmed)
                    # Use analyse_image.json as representative workflow
                    check_and_warn_selfhost_workflow("selfhost/analyse_image.json")
        
        # TTS configuration
        with st.container(border=True):
            st.markdown(f"**{tr('section.tts')}**")

            # TTS Mode selector
            tts_mode = st.radio(
                "Synthesis Mode",
                options=["local", "omnivoice"],
                format_func=lambda x: {
                    "local": "🔊 Local Synthesis (Edge TTS)",
                    "omnivoice": "🎙️ OmniVoice (AI Clone)"
                }[x],
                horizontal=True,
                key="asset_tts_mode"
            )

            # Import voice configuration
            from pixelle_video.tts_voices import EDGE_TTS_VOICES, get_voice_display_name

            # Get saved voice from config
            comfyui_config = config_manager.get_comfyui_config()
            tts_config = comfyui_config.get("tts", {})
            local_config = tts_config.get("local", {})
            saved_voice = local_config.get("voice", "zh-CN-YunjianNeural")
            saved_speed = local_config.get("speed", 1.2)

            # Defaults
            voice_id = saved_voice
            tts_speed = saved_speed
            ref_audio_path = None
            ref_text = None

            if tts_mode == "local":
                # Build voice options
                voice_options = []
                voice_ids = []
                default_voice_index = 0
                for idx, vc in enumerate(EDGE_TTS_VOICES):
                    vid = vc["id"]
                    display_name = get_voice_display_name(vid, tr, get_language())
                    voice_options.append(display_name)
                    voice_ids.append(vid)
                    if vid == saved_voice:
                        default_voice_index = idx

                voice_col, speed_col = st.columns([1, 1])
                with voice_col:
                    selected_voice_display = st.selectbox(
                        tr("tts.voice_selector"),
                        voice_options,
                        index=default_voice_index,
                        key="asset_tts_voice"
                    )
                    voice_id = voice_ids[voice_options.index(selected_voice_display)]
                with speed_col:
                    tts_speed = st.slider(
                        tr("tts.speed"),
                        min_value=0.5, max_value=2.0,
                        value=saved_speed, step=0.1,
                        format="%.1fx",
                        key="asset_tts_speed"
                    )
                    st.caption(tr("tts.speed_label", speed=f"{tts_speed:.1f}"))

            else:  # omnivoice
                st.info("🎙️ OmniVoice: Upload a reference audio to clone the voice for all narrations.")
                ref_audio_file = st.file_uploader(
                    "Reference Audio (Required)",
                    type=["mp3", "wav", "flac", "m4a", "aac", "ogg"],
                    help="Upload a clear ~10s audio sample of the target voice.",
                    key="asset_omnivoice_ref_audio"
                )
                if ref_audio_file is not None:
                    st.audio(ref_audio_file)
                    temp_dir = Path("temp")
                    temp_dir.mkdir(exist_ok=True)
                    ref_audio_path = temp_dir / f"ref_audio_{ref_audio_file.name}"
                    with open(ref_audio_path, "wb") as f:
                        f.write(ref_audio_file.getbuffer())

                ref_text = st.text_area(
                    "Reference Text (Required)",
                    placeholder="The exact transcript of the reference audio.",
                    height=80,
                    key="asset_omnivoice_ref_text"
                )
                tts_speed = st.slider(
                    tr("tts.speed"),
                    min_value=0.5, max_value=2.0,
                    value=1.0, step=0.1,
                    format="%.1fx",
                    key="asset_omnivoice_speed"
                )
                voice_id = None  # Not used in OmniVoice mode

        # Resolve media_workflow for FlowKit source
        media_workflow = None
        tts_inference_mode = tts_mode  # "local" or "omnivoice"
        if source == "flowkit":
            media_workflow = st.session_state.get("asset_flowkit_workflow", "flowkit/google-veo")

        return {
            "duration": duration,
            "source": source,
            "voice_id": voice_id,
            "tts_speed": tts_speed,
            "tts_inference_mode": tts_inference_mode,
            "ref_audio": str(ref_audio_path) if ref_audio_path else None,
            "ref_text": ref_text if ref_text else None,
            "media_workflow": media_workflow,
        }
    
    def _render_output_preview(self, pixelle_video: Any, video_params: dict):
        """Render output preview section"""
        with st.container(border=True):
            st.markdown(f"**{tr('section.video_generation')}**")
            
            # Check configuration
            if not config_manager.validate():
                st.warning(tr("settings.not_configured"))
            
            # Check if assets are provided
            assets = video_params.get("assets", [])
            if not assets:
                st.info(tr("asset_based.output.no_assets"))
                st.button(
                    tr("btn.generate"),
                    type="primary",
                    use_container_width=True,
                    disabled=True,
                    key="asset_generate_disabled"
                )
                return
            
            # Show asset summary
            st.info(tr("asset_based.output.ready", count=len(assets)))
            
            # Generate button
            if st.button(tr("btn.generate"), type="primary", use_container_width=True, key="asset_generate"):
                # Validate
                if not config_manager.validate():
                    st.error(tr("settings.not_configured"))
                    st.stop()
                
                # Show progress
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                start_time = time.time()
                
                try:
                    # Import pipeline
                    from pixelle_video.pipelines.asset_based import AssetBasedPipeline
                    
                    # Create pipeline
                    pipeline = AssetBasedPipeline(pixelle_video)
                    
                    # Progress callback
                    def update_progress(event: ProgressEvent):
                        if event.event_type == "analyzing_assets":
                            if event.extra_info == "start":
                                message = tr("asset_based.progress.analyzing_start", total=event.frame_total)
                            else:
                                message = tr("asset_based.progress.analyzing_complete", count=event.frame_total)
                        elif event.event_type == "analyzing_asset":
                            message = tr(
                                "asset_based.progress.analyzing_asset",
                                current=event.frame_current,
                                total=event.frame_total,
                                name=event.extra_info or ""
                            )
                        elif event.event_type == "generating_script":
                            if event.extra_info == "complete":
                                message = tr("asset_based.progress.script_complete")
                            else:
                                message = tr("asset_based.progress.generating_script")
                        elif event.event_type == "frame_step":
                            action_key = f"progress.step_{event.action}"
                            action_text = tr(action_key)
                            message = tr(
                                "progress.frame_step",
                                current=event.frame_current,
                                total=event.frame_total,
                                step=event.step,
                                action=action_text
                            )
                        elif event.event_type == "processing_frame":
                            message = tr(
                                "progress.frame",
                                current=event.frame_current,
                                total=event.frame_total
                            )
                        elif event.event_type == "concatenating":
                            if event.extra_info == "complete":
                                message = tr("asset_based.progress.concat_complete")
                            else:
                                message = tr("progress.concatenating")
                        elif event.event_type == "completed":
                            message = tr("progress.completed")
                        else:
                            message = tr(f"progress.{event.event_type}")
                        
                        status_text.text(message)
                        progress_bar.progress(min(int(event.progress * 100), 99))
                    
                    # Execute pipeline with progress callback
                    ctx = run_async(pipeline(
                        assets=video_params["assets"],
                        video_title=video_params.get("video_title", ""),
                        intent=video_params.get("intent"),
                        duration=video_params.get("duration", 30),
                        source=video_params.get("source", "runninghub"),
                        bgm_path=video_params.get("bgm_path"),
                        bgm_volume=video_params.get("bgm_volume", 0.2),
                        bgm_mode=video_params.get("bgm_mode", "loop"),
                        voice_id=video_params.get("voice_id", "zh-CN-YunjianNeural"),
                        tts_speed=video_params.get("tts_speed", 1.2),
                        tts_inference_mode=video_params.get("tts_inference_mode", "local"),
                        ref_audio=video_params.get("ref_audio"),
                        ref_text=video_params.get("ref_text"),
                        media_workflow=video_params.get("media_workflow"),
                        progress_callback=update_progress
                    ))
                    
                    total_time = time.time() - start_time
                    
                    progress_bar.progress(100)
                    status_text.text(tr("status.success"))
                    
                    # Display result
                    st.success(tr("status.video_generated", path=ctx.final_video_path))
                    
                    st.markdown("---")
                    
                    # Video info
                    if os.path.exists(ctx.final_video_path):
                        file_size_mb = os.path.getsize(ctx.final_video_path) / (1024 * 1024)
                        n_scenes = len(ctx.storyboard.frames) if ctx.storyboard else 0
                        
                        info_text = (
                            f"⏱️ {tr('info.generation_time')} {total_time:.1f}s   "
                            f"📦 {file_size_mb:.2f}MB   "
                            f"🎬 {n_scenes}{tr('info.scenes_unit')}"
                        )
                        st.caption(info_text)
                        
                        st.markdown("---")
                        
                        # Video preview
                        st.video(ctx.final_video_path)
                        
                        # Download button
                        with open(ctx.final_video_path, "rb") as video_file:
                            video_bytes = video_file.read()
                            video_filename = os.path.basename(ctx.final_video_path)
                            st.download_button(
                                label="⬇️ 下载视频" if get_language() == "zh_CN" else "⬇️ Download Video",
                                data=video_bytes,
                                file_name=video_filename,
                                mime="video/mp4",
                                use_container_width=True
                            )
                    else:
                        st.error(tr("status.video_not_found", path=ctx.final_video_path))
                
                except Exception as e:
                    status_text.text("")
                    progress_bar.empty()
                    st.error(tr("status.error", error=str(e)))
                    logger.exception(e)
                    st.stop()


# Register self
register_pipeline_ui(AssetBasedPipelineUI)

