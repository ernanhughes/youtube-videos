"""Review is tied to exact on-disk draft content. Any edit invalidates approval."""
from pathlib import Path
import hashlib
import json

DRAFT_FILES = ("storyboard.json", "narration.md", "slides.md", "evidence.json", "lesson.json")


def snapshot(draft_dir: Path) -> str:
    digest = hashlib.sha256()
    for name in DRAFT_FILES:
        path = draft_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"Cannot review: missing {path}")
        data = path.read_bytes()
        digest.update(name.encode() + b"\x00" + str(len(data)).encode() + b"\x00" + data)
    return digest.hexdigest()


def validate_drafts(draft_dir: Path):
    for name in ("storyboard.json", "evidence.json", "lesson.json"):
        obj = json.loads((draft_dir / name).read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            raise ValueError(f"{name} must contain a JSON object")
    scenes = json.loads((draft_dir / "storyboard.json").read_text(encoding="utf-8"))
    if not scenes.get("scenes"):
        raise ValueError("A storyboard must contain at least one scene")
    if not (draft_dir / "narration.md").read_text(encoding="utf-8").strip():
        raise ValueError("Narration cannot be empty")
