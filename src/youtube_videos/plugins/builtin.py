"""Deterministic foundation stages; no invented citations or unverified code execution."""
from __future__ import annotations
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path
from urllib.parse import urlparse
import yaml
from youtube_videos.core.models import StageResult, StageContext
from youtube_videos.core.review import snapshot, validate_drafts, DRAFT_FILES


def save_json(path: Path, value: dict):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text)).strip()


class HugoIngest:
    id = "hugo_ingest"

    def run(self, ctx: StageContext) -> StageResult:
        size = ctx.chapter.stat().st_size
        if size > ctx.settings["limits"].get("max_chapter_bytes", 1048576):
            raise ValueError(f"Chapter exceeds maximum bytes: {size}")
        data = ctx.chapter.read_bytes()
        source = data.decode("utf-8")
        # Source snapshot keeps the lesson tied to the original bytes.
        (ctx.work_dir / "chapter_source.md").write_bytes(data)
        body = source
        meta = {}
        if source.startswith("---\n"):
            closing = source.find("\n---\n", 4)
            if closing != -1:
                front = yaml.safe_load(source[4:closing]) or {}
                if isinstance(front, dict):
                    meta = front
                    body = source[closing + 5:]
        elif source.startswith("+++\n"):
            closing = source.find("\n+++\n", 4)
            if closing != -1:
                import tomllib
                meta = tomllib.loads(source[4:closing])
                body = source[closing + 5:]
        headings = []
        code = []
        links = []
        in_fence = False
        fence_char = ""
        code_lang = ""
        code_lines = []
        block_start = 0
        for number, line in enumerate(body.splitlines(), 1):
            match = re.match(r"^\s*(`{3,}|~{3,})([A-Za-z0-9_+#-]*)", line)
            if match:
                marker = match.group(1)
                if not in_fence:
                    in_fence = True
                    fence_char = marker[0]
                    code_lang = match.group(2)
                    code_lines = []
                    block_start = number
                elif marker[0] == fence_char:
                    in_fence = False
                    code.append({"id": f"code-{len(code)+1:02}", "language": code_lang or "text",
                                 "line": block_start, "text": "\n".join(code_lines), "execution": "not_run"})
                continue
            if in_fence:
                code_lines.append(line)
                continue
            heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
            if heading:
                headings.append({"id": f"section-{len(headings)+1:02}", "level": len(heading.group(1)),
                                 "text": clean_text(heading.group(2)), "line": number})
            for label, url in re.findall(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", line):
                links.append({"id": f"url-{len(links)+1:02}", "label": label, "url": url,
                              "line": number, "verification": "not_checked"})
        if in_fence:
            raise ValueError("Unclosed code fence in chapter")
        title = str(meta.get("title") or (headings[0]["text"] if headings else ctx.chapter.stem))
        artifact = {"schema": "youtube-videos.source.v1", "title": title,
                    "source_path": ctx.chapter.relative_to(ctx.source_root).as_posix(),
                    "source_sha256": sha256(data), "frontmatter": meta,
                    "headings": headings, "code": code, "links": links,
                    "body_excerpt": clean_text(re.sub(r"```.*?```", "", body, flags=re.S))[:1200]}
        save_json(ctx.work_dir / "source_index.json", artifact)
        return StageResult(artifact)


class LessonPlan:
    id = "lesson_plan"

    def run(self, ctx: StageContext) -> StageResult:
        source = ctx.outputs["ingest"]
        outline = [{"id": "hook", "purpose": "problem and outcome", "source_ref": "chapter"}]
        for heading in source["headings"][:8]:
            outline.append({"id": heading["id"], "purpose": heading["text"], "source_ref": heading["id"]})
        for code in source["code"][:8]:
            outline.append({"id": code["id"], "purpose": f"explain {code['language']} code (not executed)",
                            "source_ref": code["id"]})
        outline.append({"id": "conclusion", "purpose": "review and next experiment", "source_ref": "chapter"})
        artifact = {"schema": "youtube-videos.lesson.v1", "title": source["title"],
                    "kind": "technical_tutorial", "source_sha256": source["source_sha256"],
                    "beats": outline, "narration_policy": "Review and rewrite before approval; no AI inference performed.",
                    "code_policy": "Show code as source-only until separate execution plugin verifies it."}
        save_json(ctx.draft_dir / "lesson.json", artifact)
        return StageResult(artifact)


class EvidenceMap:
    id = "evidence_map"

    def run(self, ctx: StageContext) -> StageResult:
        source = ctx.outputs["ingest"]
        artifacts = ([{"id": "chapter", "kind": "manuscript", "reference": source["source_path"],
                       "integrity": source["source_sha256"], "status": "captured"}]
                     + [{"id": h["id"], "kind": "section", "reference": f"line:{h['line']}",
                         "status": "captured"} for h in source["headings"]]
                     + [{"id": c["id"], "kind": "code", "reference": f"line:{c['line']}",
                         "status": "unexecuted"} for c in source["code"]]
                     + [{"id": l["id"], "kind": "external_link", "reference": l["url"],
                         "status": "unverified"} for l in source["links"]])
        result = {"schema": "youtube-videos.evidence.v1", "sources": artifacts,
                  "policy": "Chapter presence is not proof of external accuracy or runnable code."}
        save_json(ctx.draft_dir / "evidence.json", result)
        return StageResult(result)


class Storyboard:
    id = "storyboard"

    def run(self, ctx: StageContext) -> StageResult:
        source = ctx.outputs["ingest"]
        lesson = ctx.outputs["plan"]
        scenes = []
        narration = [f"# Narration draft — {source['title']}", "", "> EDITORIAL DRAFT — requires fact-checking and narration review.", ""]
        slides = [f"# {source['title']}", "", "<!-- Draft slides; rendered video NOT generated. -->", ""]
        code_by_id = {block["id"]: block for block in source["code"]}
        max_scenes = ctx.settings["limits"].get("max_scenes", 35)
        for beat in lesson["beats"][:max_scenes]:
            kind = "code" if beat["source_ref"] in code_by_id else "slide"
            scene = {"id": f"scene-{len(scenes)+1:02}", "beat_id": beat["id"],
                     "kind": kind, "headline": beat["purpose"], "source_ref": beat["source_ref"],
                     "evidence_status": "unexecuted" if kind == "code" else "chapter_sourced",
                     "visual_notes": "Capture code and measured output" if kind == "code" else "Minimal concept slide"}
            scenes.append(scene)
            narration += [f"## {scene['id']}: {beat['purpose']}",
                          f"[Rewrite to explain the underlying idea; source reference: {beat['source_ref']}.]", ""]
            slides += ["---", "", f"## {beat['purpose']}", ""]
            if kind == "code":
                block = code_by_id[beat["source_ref"]]
                slides += [f"```{block['language']}", block["text"], "```", "",
                           "**Execution:** Not run. Do not present invented output.", ""]
            else:
                slides += [f"Source: {beat['source_ref']}", ""]
        artifact = {"schema": "youtube-videos.storyboard.v1", "title": source["title"], "scenes": scenes}
        save_json(ctx.draft_dir / "storyboard.json", artifact)
        (ctx.draft_dir / "narration.md").write_text("\n".join(narration), encoding="utf-8")
        (ctx.draft_dir / "slides.md").write_text("\n".join(slides), encoding="utf-8")
        return StageResult({"scene_count": len(scenes), "drafts": list(DRAFT_FILES)})


class CoCoderAdapter:
    id = "cocoder_adapter"

    def run(self, ctx: StageContext) -> StageResult:
        # This plugin ingests an OPTIONAL pre-existing CoCoder walkthrough manifest; it does not run CoCoder.
        manifest = ctx.settings.get("cocoder_manifest")
        if not manifest:
            return StageResult({"status": "not_provided", "steps": []})
        path = Path(manifest).resolve()
        if not path.is_relative_to(ctx.source_root):
            raise ValueError("CoCoder manifest is outside source root")
        obj = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(obj, dict) or not isinstance(obj.get("steps"), list):
            raise ValueError("CoCoder manifest must have an array named steps")
        for step in obj["steps"]:
            if not isinstance(step, dict) or not isinstance(step.get("id"), str):
                raise ValueError("Each CoCoder step must have an id string")
        save_json(ctx.draft_dir / "cocoder_walkthrough.json", obj)
        return StageResult({"status": "captured_not_executed", "steps": [s["id"] for s in obj["steps"]],
                            "sha256": sha256(path.read_bytes())})


class ApprovalGate:
    id = "approval_gate"

    def run(self, ctx: StageContext) -> StageResult:
        validate_drafts(ctx.draft_dir)
        checksum = snapshot(ctx.draft_dir)
        decision = ctx.store.decision(ctx.run_id, "approval")
        if decision is None or decision["decision"] != "approved":
            return StageResult({"decision": "pending_or_rejected", "snapshot": checksum},
                               pause=True, status="waiting")
        if decision["snapshot"] != checksum:
            return StageResult({"decision": "draft_changed_reapproval_required", "snapshot": checksum},
                               pause=True, status="waiting")
        return StageResult({"decision": "approved", "snapshot": checksum})


class PackageDraft:
    id = "package_draft"

    def run(self, ctx: StageContext) -> StageResult:
        approval = ctx.outputs["approval"]
        if approval["decision"] != "approved" or snapshot(ctx.draft_dir) != approval["snapshot"]:
            raise RuntimeError("Approved drafts changed; reapproval required")
        # Construct deterministic, content-addressed ZIP. No publishing side effects.
        archive = ctx.work_dir / "lesson_package.zip"
        payload = {"chapter_source.md": (ctx.work_dir / "chapter_source.md").read_bytes(),
                   "source_index.json": (ctx.work_dir / "source_index.json").read_bytes(),
                   **{f"drafts/{name}": (ctx.draft_dir / name).read_bytes() for name in DRAFT_FILES}}
        optional = ctx.draft_dir / "cocoder_walkthrough.json"
        if optional.exists():
            payload["drafts/cocoder_walkthrough.json"] = optional.read_bytes()
        manifest = {"schema": "youtube-videos.package.v1", "run_id": ctx.run_id,
                    "source_sha256": ctx.outputs["ingest"]["source_sha256"],
                    "approval_sha256": approval["snapshot"],
                    "artifacts": {k: sha256(v) for k, v in sorted(payload.items())},
                    "verification": {"citations": "unverified", "code": "not_executed", "render": "not_generated"}}
        payload["manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
        payload["README.txt"] = ("DRAFT technical lesson package. Human-approved content, not verified research.\n"
                                  "Code has not been executed. Video has not been rendered.\n").encode()
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for name, data in sorted(payload.items()):
                z.writestr(name, data)
        return StageResult({"archive": str(archive), "manifest": manifest})


BUILTINS = {
    "hugo_ingest": HugoIngest(),
    "lesson_plan": LessonPlan(),
    "evidence_map": EvidenceMap(),
    "storyboard": Storyboard(),
    "cocoder_adapter": CoCoderAdapter(),
    "approval_gate": ApprovalGate(),
    "package_draft": PackageDraft(),
}
