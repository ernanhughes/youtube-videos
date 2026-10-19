import json
import zipfile
from pathlib import Path
import pytest
from youtube_videos.core.config import load_config
from youtube_videos.core.engine import Engine, validate_workflow
from youtube_videos.core.review import snapshot


def test_config_loads():
    cfg = load_config()
    assert cfg["workflow"]["name"] == "technical_lesson"
    assert cfg["events"]["enabled"] is False


def test_hydra_zmq_group_loads():
    assert load_config(events="zmq")["events"]["enabled"] is True


def test_workflow_stages_have_valid_dependencies():
    validate_workflow(load_config()["workflow"])


def test_invalid_dependency_fails():
    with pytest.raises(ValueError):
        validate_workflow({"stages": [{"id": "a", "needs": ["b"]}]})


def test_duplicate_stage_fails():
    with pytest.raises(ValueError):
        validate_workflow({"stages": [{"id": "a"}, {"id": "a"}]})


def test_run_pauses_for_review(prepared):
    eng, rid, _, _ = prepared
    result = eng.run(rid)
    assert result["status"] == "waiting_review"
    assert (Path(result["draft_dir"]) / "storyboard.json").is_file()
    assert eng.store.stage(rid, "package") is None


def test_repeated_waiting_is_idempotent(prepared):
    eng, rid, _, _ = prepared
    eng.run(rid)
    before = eng.store.stage(rid, "storyboard")["updated_at"]
    eng.run(rid)
    assert eng.store.stage(rid, "storyboard")["updated_at"] == before


def test_approval_and_package(prepared):
    eng, rid, _, _ = prepared
    eng.run(rid)
    drafts = Path(eng.store.get(rid)["work_dir"]) / "drafts"
    eng.store.decide(rid, "approval", "approved", snapshot(drafts))
    result = eng.run(rid)
    assert result["status"] == "completed"
    with zipfile.ZipFile(result["package"]) as archive:
        assert "manifest.json" in archive.namelist()
        meta = json.loads(archive.read("manifest.json"))
        assert meta["verification"]["code"] == "not_executed"
        assert archive.read("chapter_source.md")
    assert eng.store.get(rid)["status"] == "completed"


def test_approval_invalidated_by_edit(prepared):
    eng, rid, _, _ = prepared
    eng.run(rid)
    drafts = Path(eng.store.get(rid)["work_dir"]) / "drafts"
    eng.store.decide(rid, "approval", "approved", snapshot(drafts))
    with (drafts / "narration.md").open("a", encoding="utf-8") as output:
        output.write("\nNew approved? No.\n")
    result = eng.run(rid)
    assert result["status"] == "waiting_review"
    assert eng.store.stage(rid, "package") is None


def test_rejection_waits(prepared):
    eng, rid, _, _ = prepared
    eng.run(rid)
    drafts = Path(eng.store.get(rid)["work_dir"]) / "drafts"
    eng.store.decide(rid, "approval", "rejected", snapshot(drafts))
    assert eng.run(rid)["status"] == "waiting_review"


def test_events_replay(prepared):
    eng, rid, _, _ = prepared
    eng.run(rid)
    ev = eng.store.events(rid)
    assert ev[0]["type"] == "stage.started"
    assert ev[-1]["type"] == "review.requested"
    assert all(e["run_id"] == rid for e in ev)


def test_ingest_code_not_executed(prepared):
    eng, rid, _, _ = prepared
    eng.run(rid)
    ingest = eng.store.stage(rid, "ingest")["output"]
    assert ingest["code"][0]["execution"] == "not_run"
    assert ingest["links"][0]["verification"] == "not_checked"


def test_snapshot_repeatable(prepared):
    eng, rid, _, _ = prepared
    eng.run(rid)
    drafts = Path(eng.store.get(rid)["work_dir"]) / "drafts"
    assert snapshot(drafts) == snapshot(drafts)


def test_missing_chapter_fails(tmp_path):
    eng = Engine(tmp_path / "store")
    try:
        with pytest.raises(FileNotFoundError):
            eng.new_run(tmp_path / "none.md", tmp_path, load_config())
    finally:
        eng.close()


def test_escape_root_fails(tmp_path):
    eng = Engine(tmp_path / "store")
    outside = tmp_path / "outside.md"
    outside.write_text("Hello")
    root = tmp_path / "sub"
    root.mkdir()
    try:
        with pytest.raises(ValueError, match="outside"):
            eng.new_run(outside, root, load_config())
    finally:
        eng.close()


def test_unknown_run_fails(prepared):
    eng, _, _, _ = prepared
    with pytest.raises(ValueError, match="Unknown run"):
        eng.store.get("unseen")


def test_missing_plugin_fails(prepared):
    eng, rid, _, _ = prepared
    conf = eng.store.get(rid)["config"]
    conf["workflow"]["stages"][0]["plugin"] = "unknown_extension"
    # The selected workflow is immutable within a run; validate the registry explicitly.
    from youtube_videos.core.registry import Registry
    with pytest.raises(ValueError):
        Registry().get("unknown_extension")


def test_strict_chapter_size_limit(prepared):
    eng, rid, _, _ = prepared
    # Run configuration is persisted; create second run with strict limits.
    src = eng.store.get(rid)
    cfg = src["config"]
    cfg["limits"]["max_chapter_bytes"] = 10
    new_id = eng.new_run(Path(src["source"]), Path(src["source_root"]), cfg)
    with pytest.raises(ValueError, match="exceeds"):
        eng.run(new_id)
    assert eng.store.get(new_id)["status"] == "failed"


def test_cocoder_manifest(prepared):
    eng, rid, root, chapter = prepared
    cfg = eng.store.get(rid)["config"]
    manifest = root / "walkthrough.json"
    manifest.write_text('{"steps":[{"id":"explain-event"}]}')
    cfg["cocoder_manifest"] = str(manifest)
    new_id = eng.new_run(chapter, root, cfg)
    assert eng.run(new_id)["status"] == "waiting_review"
    result = eng.store.stage(new_id, "cocoder")["output"]
    assert result["steps"] == ["explain-event"]


def test_zero_side_effect_package_before_approval(prepared):
    eng, rid, _, _ = prepared
    eng.run(rid)
    assert not (Path(eng.store.get(rid)["work_dir"]) / "lesson_package.zip").exists()


def test_review_decision_is_a_durable_event(prepared):
    eng, rid, _, _ = prepared
    eng.run(rid)
    drafts = Path(eng.store.get(rid)["work_dir"]) / "drafts"
    eng.store.decide(rid, "approval", "approved", snapshot(drafts))
    assert eng.store.events(rid)[-1]["type"] == "review.decided"
