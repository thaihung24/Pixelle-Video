"""
Project profile loading for command-line episode generation.

Profiles live under projects/<project_id>/project.json by convention.
The loader is intentionally outside the pixelle_video package so simple CLI
tools can read profiles without importing PixelleVideoCore or ComfyKit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class ProjectProfile:
    project_id: str
    path: Path
    data: dict[str, Any]

    @property
    def project_dir(self) -> Path:
        return self.path.parent

    @property
    def bible_path(self) -> Path:
        return self.resolve_path(self.data.get("series_bible", "series_bible.json"))

    @property
    def output_root(self) -> Path:
        output_root = self.data.get("output_root") or f"output/series_{self.channel}"
        return self.resolve_path(output_root)

    @property
    def channel(self) -> str:
        return self.data.get("channel") or self.project_id

    @property
    def template(self) -> str:
        return self.data.get("template", "1920x1080/video_youtube.html")

    @property
    def voice(self) -> dict[str, Any]:
        return self.data.get("voice", {"tts_mode": "local", "voice": "ja-JP-NanamiNeural", "speed": 1.0})

    @property
    def template_params(self) -> dict[str, Any]:
        return self.data.get("template_params", {})

    @property
    def language(self) -> str | None:
        return self.data.get("language")

    def resolve_path(self, value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return (self.project_dir / path).resolve()

    def episode_dir(self, episode_id: str) -> Path:
        return self.output_root / normalize_episode_id(episode_id)


def normalize_episode_id(episode: str | int) -> str:
    if isinstance(episode, int):
        return f"ep{episode:02d}"
    raw = str(episode).strip().lower()
    if raw.startswith("ep"):
        num = int(raw[2:])
    else:
        num = int(raw)
    return f"ep{num:02d}"


def episode_number(episode: str | int) -> int:
    return int(normalize_episode_id(episode)[2:])


def project_profile_path(project: str) -> Path:
    candidate = Path(project)
    if candidate.suffix == ".json" or candidate.exists():
        return candidate.resolve()
    return (ROOT_DIR / "projects" / project / "project.json").resolve()


def load_project_profile(project: str = "sukoyaka_life") -> ProjectProfile:
    path = project_profile_path(project)
    if not path.exists():
        raise FileNotFoundError(f"Project profile not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    project_id = data.get("id") or path.parent.name
    return ProjectProfile(project_id=project_id, path=path, data=data)


def load_series_bible(profile: ProjectProfile) -> dict[str, Any]:
    bible_path = profile.bible_path
    if not bible_path.exists():
        raise FileNotFoundError(f"Series bible not found: {bible_path}")
    with open(bible_path, "r", encoding="utf-8") as f:
        return json.load(f)
