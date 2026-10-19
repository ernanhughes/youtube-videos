"""Windows-friendly workflow CLI."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from youtube_videos.core.config import load_config
from youtube_videos.core.engine import Engine, validate_workflow
from youtube_videos.core.registry import Registry
from youtube_videos.core.review import snapshot, validate_drafts


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="youtube-videos", description="Evidence-linked book-to-video drafts")
    p.add_argument("--workspace", type=Path, default=Path(".ytv"))
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="Start or resume a workflow")
    mode = r.add_mutually_exclusive_group(required=True)
    mode.add_argument("--chapter", type=Path)
    mode.add_argument("--resume", metavar="RUN_ID")
    r.add_argument("--root", type=Path, default=Path.cwd())
    r.add_argument("--workflow", default="technical_lesson")
    r.add_argument("--events", choices=["local", "zmq"], default="local")
    r.add_argument("--cocoder-manifest", type=Path)
    a = sub.add_parser("approve", help="Approve exact current drafts; invalidate previous approval on changes")
    a.add_argument("run_id")
    a = sub.add_parser("reject", help="Reject current drafts and keep workflow paused")
    a.add_argument("run_id")
    a = sub.add_parser("show", help="Show run, stages and draft path")
    a.add_argument("run_id")
    a = sub.add_parser("events", help="Replay durable events")
    a.add_argument("run_id")
    sub.add_parser("plugins")
    sub.add_parser("validate")
    return p


def main(argv: list[str] | None = None):
    args = parser().parse_args(argv)
    if args.command == "plugins":
        print("\n".join(Registry().list()))
        return 0
    if args.command == "validate":
        config = load_config()
        validate_workflow(config["workflow"])
        print(json.dumps({"valid": True, "workflow": config["workflow"]["name"]}))
        return 0
    engine = Engine(args.workspace)
    try:
        if args.command == "run":
            if args.resume:
                run_id = args.resume
            else:
                config = load_config(args.workflow, args.events)
                if args.cocoder_manifest:
                    config["cocoder_manifest"] = str(args.cocoder_manifest.resolve())
                run_id = engine.new_run(args.chapter, args.root, config)
            result = engine.run(run_id)
        elif args.command in ("approve", "reject"):
            run = engine.store.get(args.run_id)
            if run["status"] not in ("waiting_review", "failed"):
                raise ValueError("Run must reach review gate before making a decision")
            if engine.store.stage(args.run_id, "storyboard") is None:
                raise ValueError("Run has no storyboard to review")
            draft_dir = Path(run["work_dir"]) / "drafts"
            validate_drafts(draft_dir)
            checksum = snapshot(draft_dir)
            engine.store.decide(args.run_id, "approval", "approved" if args.command == "approve" else "rejected", checksum)
            result = {"run_id": args.run_id, "decision": args.command, "snapshot": checksum}
        elif args.command == "show":
            run = engine.store.get(args.run_id)
            run.pop("config")
            result = {**run, "stages": sorted(engine.store.stage_outputs(args.run_id)),
                      "draft_dir": str(Path(run["work_dir"]) / "drafts")}
        elif args.command == "events":
            result = engine.store.events(args.run_id)
        else:
            raise AssertionError(args.command)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
