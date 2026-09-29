"""Snapshot storage manager."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from kdenlive_mcp.config import get_config
from kdenlive_mcp.core.assets.model import MediaAsset, MediaIndex
from kdenlive_mcp.core.timeline.model import Project
from kdenlive_mcp.core.timeline.serialize import project_from_dict, project_to_dict
from kdenlive_mcp.errors import SnapshotNotFoundError


@dataclass
class SnapshotInfo:
    id: str
    project_id: str
    label: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SnapshotManager:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir if base_dir is not None else get_config().snapshots_dir

    def _project_dir(self, project_id: str) -> Path:
        p = self.base_dir / project_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def create_snapshot(
        self, project: Project, media_index: MediaIndex, label: str = ""
    ) -> SnapshotInfo:
        snap_id = f"snap_{uuid.uuid4().hex[:8]}"
        info = SnapshotInfo(
            id=snap_id,
            project_id=project.id,
            label=label,
            timestamp=time.time(),
        )
        p_dir = self._project_dir(project.id)
        data = {
            "info": info.to_dict(),
            "project": project_to_dict(project),
            "media_index": {k: v.to_dict() for k, v in media_index._assets.items()},
        }
        (p_dir / f"{snap_id}.json").write_text(json.dumps(data, indent=2))
        return info

    def list_snapshots(self, project_id: str) -> list[SnapshotInfo]:
        p_dir = self._project_dir(project_id)
        infos: list[SnapshotInfo] = []
        for file in p_dir.glob("*.json"):
            try:
                data = json.loads(file.read_text())
                info_dict = data.get("info", {})
                infos.append(
                    SnapshotInfo(
                        id=info_dict.get("id", file.stem),
                        project_id=info_dict.get("project_id", project_id),
                        label=info_dict.get("label", ""),
                        timestamp=info_dict.get("timestamp", 0.0),
                    )
                )
            except Exception:
                continue
        infos.sort(key=lambda s: s.timestamp, reverse=True)
        return infos

    def restore_snapshot(
        self, project_id: str, snapshot_id: str
    ) -> tuple[Project, MediaIndex]:
        p_dir = self._project_dir(project_id)
        snap_file = p_dir / f"{snapshot_id}.json"
        if not snap_file.exists():
            raise SnapshotNotFoundError(
                f"Snapshot '{snapshot_id}' not found for project '{project_id}'"
            )
        data = json.loads(snap_file.read_text())
        project = project_from_dict(data["project"])
        media_index = MediaIndex(None)
        if "media_index" in data:
            media_index._assets = {
                k: MediaAsset.from_dict(v) for k, v in data["media_index"].items()
            }
        return project, media_index

    def compare_snapshots(
        self, project_id: str, snapshot_id_a: str, snapshot_id_b: str
    ) -> dict[str, Any]:
        p_a, _ = self.restore_snapshot(project_id, snapshot_id_a)
        p_b, _ = self.restore_snapshot(project_id, snapshot_id_b)
        return {
            "snapshot_a": snapshot_id_a,
            "snapshot_b": snapshot_id_b,
            "project_id": project_id,
            "clips_a_count": sum(len(track.clips) for seq in p_a.sequences for track in seq.tracks),
            "clips_b_count": sum(len(track.clips) for seq in p_b.sequences for track in seq.tracks),
        }
