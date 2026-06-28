import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


_PROJECT_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")
_IMMUTABLE_FIELDS = {"id", "created_at"}


class ProjectStore:
    def __init__(self, app_data_dir: Path):
        self.app_data_dir = Path(app_data_dir)
        self.projects_dir = self.app_data_dir / "projects"
        self._last_timestamp: datetime | None = None

    def create_project(
        self,
        source_path: str,
        file_name: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        now = self._now()
        project = {
            "id": uuid.uuid4().hex,
            "file_name": file_name,
            "source_path": source_path,
            "options": options,
            "status": "created",
            "created_at": now,
            "updated_at": now,
            "edit_plan": None,
            "export_path": None,
        }
        self._write_project(project)
        return project

    def update_project(self, project_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        if not self._is_valid_project_id(project_id):
            raise KeyError(project_id)

        project = self.get_project(project_id)
        if project is None:
            raise KeyError(project_id)

        mutable_changes = {
            key: value
            for key, value in changes.items()
            if key not in _IMMUTABLE_FIELDS
        }
        project["id"] = project_id
        project.update(mutable_changes)
        project["updated_at"] = self._now()
        self._write_project(project)
        return project

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        if not self._is_valid_project_id(project_id):
            return None

        project_path = self._project_path(project_id)
        if not project_path.exists():
            return None

        try:
            with project_path.open("r", encoding="utf-8") as file:
                project = json.load(file)
        except (OSError, json.JSONDecodeError):
            return None

        if not isinstance(project, dict):
            return None
        return project

    def list_recent_projects(self, limit: int = 20) -> list[dict[str, Any]]:
        projects = []
        for project_path in self.projects_dir.glob("*/project.json"):
            try:
                with project_path.open("r", encoding="utf-8") as file:
                    project = json.load(file)
            except (OSError, json.JSONDecodeError):
                continue

            if not isinstance(project, dict):
                continue

            updated_at = self._parse_timestamp(project.get("updated_at"))
            if updated_at is None:
                continue

            projects.append((updated_at, project))

        projects.sort(key=lambda item: item[0], reverse=True)
        return [project for _, project in projects[:limit]]

    def analyze_upload_patterns(self, limit: int = 50) -> dict[str, Any]:
        """Analyze user's upload history to detect game genre patterns."""
        projects = self.list_recent_projects(limit)
        
        game_counts = {}
        style_counts = {}
        audience_usage = {}
        
        for project in projects:
            options = project.get("options", {})
            game_name = options.get("game_name", "").lower().strip()
            style = options.get("style", "").lower().strip()
            audience = options.get("audience", [])
            
            if game_name:
                game_counts[game_name] = game_counts.get(game_name, 0) + 1
            if style:
                style_counts[style] = style_counts.get(style, 0) + 1
            for creator in audience:
                audience_usage[creator] = audience_usage.get(creator, 0) + 1
        
        # Detect dominant patterns
        dominant_game = max(game_counts.items(), key=lambda x: x[1])[0] if game_counts else None
        dominant_style = max(style_counts.items(), key=lambda x: x[1])[0] if style_counts else None
        
        # Suggest creators based on patterns
        suggested_creators = self._suggest_creators_by_pattern(dominant_game, dominant_style)
        
        return {
            "total_projects": len(projects),
            "dominant_game": dominant_game,
            "dominant_style": dominant_style,
            "game_counts": game_counts,
            "style_counts": style_counts,
            "audience_usage": audience_usage,
            "suggested_creators": suggested_creators,
        }
    
    def _suggest_creators_by_pattern(self, game: str | None, style: str | None) -> list[str]:
        """Suggest creators based on detected game/style patterns."""
        # Horror games
        horror_keywords = ["horror", "scary", "resident evil", "amnesia", "outlast", "fnaf", "dead by daylight"]
        if any(keyword in (game or "") for keyword in horror_keywords) or style == "horror":
            return ["CoryxKenshin", "Markiplier"]
        
        # Simulator games
        sim_keywords = ["simulator", "sim", "farming", "flight", "truck", "euro truck", "city car"]
        if any(keyword in (game or "") for keyword in sim_keywords):
            return ["GrayStillPlays", "Drae"]
        
        # Shooters/Action
        shooter_keywords = ["warzone", "call of duty", "valorant", "overwatch", "apex", "fortnite", "cs", "counter"]
        if any(keyword in (game or "") for keyword in shooter_keywords):
            return ["Shroud", "TenZ", "NoahJ456"]
        
        # General gaming
        if game:
            return ["Markiplier", "Jacksepticeye"]
        
        return []

    def _write_project(self, project: dict[str, Any]) -> None:
        project_path = self._project_path(project["id"])
        project_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = project_path.with_suffix(".json.tmp")
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(project, file, indent=2)
        temp_path.replace(project_path)

    def _project_path(self, project_id: str) -> Path:
        if not self._is_valid_project_id(project_id):
            raise ValueError(f"Invalid project id: {project_id}")
        return self.projects_dir / project_id / "project.json"

    def _now(self) -> str:
        now = datetime.now(timezone.utc)
        if self._last_timestamp is not None and now <= self._last_timestamp:
            now = self._last_timestamp + timedelta(microseconds=1)
        self._last_timestamp = now
        return now.isoformat()

    def _parse_timestamp(self, value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None

        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None

        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed

    def _is_valid_project_id(self, project_id: str) -> bool:
        return isinstance(project_id, str) and _PROJECT_ID_PATTERN.fullmatch(project_id) is not None
