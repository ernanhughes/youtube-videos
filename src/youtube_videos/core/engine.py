"""Synchronous, resumable, dependency-validated workflow executor."""
from __future__ import annotations
from pathlib import Path
import uuid
from youtube_videos.core.models import StageContext, StageResult
from youtube_videos.core.storage import Store
from youtube_videos.core.events import Publisher
from youtube_videos.core.registry import Registry


def validate_workflow(workflow: dict):
    seen = set()
    for stage in workflow["stages"]:
        if stage["id"] in seen:
            raise ValueError(f"Duplicate stage: {stage['id']}")
        if not set(stage.get("needs", [])) <= seen:
            raise ValueError(f"Stage {stage['id']} has missing or forward dependency")
        seen.add(stage["id"])
    if not seen:
        raise ValueError("Workflow has no stages")


class Engine:
    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.store = Store(self.workspace / "state.sqlite3")

    def new_run(self, chapter: Path, root: Path, settings: dict) -> str:
        root = root.resolve()
        chapter = (root / chapter).resolve() if not chapter.is_absolute() else chapter.resolve()
        if not chapter.is_relative_to(root):
            raise ValueError("Chapter is outside the specified source root")
        if not chapter.is_file():
            raise FileNotFoundError(chapter)
        validate_workflow(settings["workflow"])
        run_id = "yt_" + uuid.uuid4().hex[:16]
        work = self.workspace / "runs" / run_id
        work.mkdir(parents=True)
        self.store.create(run_id, chapter, root, work, settings)
        return run_id

    def run(self, run_id: str) -> dict:
        run = self.store.get(run_id)
        if run["status"] == "completed":
            return {"run_id": run_id, "status": "completed"}
        settings = run["config"]
        validate_workflow(settings["workflow"])
        publisher = Publisher(settings.get("events", {}))
        registry = Registry(**settings.get("plugins", {}))
        outputs = self.store.stage_outputs(run_id)
        work = Path(run["work_dir"])
        try:
            self.store.set_status(run_id, "running")
            for spec in settings["workflow"]["stages"]:
                stage_id = spec["id"]
                prior = self.store.stage(run_id, stage_id)
                if prior and prior["status"] == "done":
                    continue
                if not set(spec.get("needs", [])) <= outputs.keys():
                    raise RuntimeError(f"Dependencies not satisfied: {stage_id}")
                plugin = registry.get(spec["plugin"])
                ctx = StageContext(run_id=run_id, chapter=Path(run["source"]),
                                   source_root=Path(run["source_root"]), work_dir=work,
                                   store=self.store, outputs=outputs, settings=settings,
                                   params=spec.get("params", {}))
                self._emit(publisher, run_id, "stage.started", {"stage": stage_id}, settings)
                try:
                    result = plugin.run(ctx)
                    if not isinstance(result, StageResult):
                        raise TypeError(f"Plugin {spec['plugin']} must return StageResult")
                    if result.pause:
                        self.store.save_stage(run_id, stage_id, spec["plugin"], result.status, result.output)
                        self.store.set_status(run_id, "waiting_review")
                        self._emit(publisher, run_id, "review.requested", {"stage": stage_id}, settings)
                        return {"run_id": run_id, "status": "waiting_review", "draft_dir": str(ctx.draft_dir)}
                    self.store.save_stage(run_id, stage_id, spec["plugin"], "done", result.output)
                    outputs[stage_id] = result.output
                    self._emit(publisher, run_id, "stage.completed", {"stage": stage_id}, settings)
                except Exception as exc:
                    self.store.set_status(run_id, "failed")
                    self._emit(publisher, run_id, "stage.failed", {"stage": stage_id, "error": str(exc)}, settings)
                    raise
            self.store.set_status(run_id, "completed")
            self._emit(publisher, run_id, "run.completed", {}, settings)
            result = {"run_id": run_id, "status": "completed"}
            if "package" in outputs:
                result["package"] = outputs["package"]["archive"]
            return result
        finally:
            publisher.close()

    def _emit(self, pub: Publisher, rid: str, kind: str, data: dict, settings: dict):
        evt = self.store.event(rid, kind, data, settings["limits"].get("max_events_per_run", 1000))
        pub.publish(evt)

    def close(self):
        self.store.close()
