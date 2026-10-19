from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class StageContext:
    run_id: str
    chapter: Path
    source_root: Path
    work_dir: Path
    store: Any
    outputs: dict[str, dict]
    settings: dict
    params: dict

    @property
    def draft_dir(self) -> Path:
        p = self.work_dir / "drafts"
        p.mkdir(parents=True, exist_ok=True)
        return p


@dataclass
class StageResult:
    output: dict
    pause: bool = False
    status: str = "done"
