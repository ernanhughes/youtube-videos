import json
from pathlib import Path
import pytest
from youtube_videos.cli import main
from youtube_videos.core.registry import Registry
from youtube_videos.core.review import validate_drafts
from youtube_videos.core.events import Publisher


def test_builtin_plugin_list():
    assert len(Registry().list()) == 7


def test_validate_cli(capsys):
    assert main(["validate"]) == 0
    assert json.loads(capsys.readouterr().out)["valid"]


def test_plugins_cli(capsys):
    assert main(["plugins"]) == 0
    assert "hugo_ingest" in capsys.readouterr().out


def test_full_cli_round_trip(tmp_path, capsys):
    base = Path(__file__).resolve().parents[1]
    chapter = base / "examples" / "sample-chapter.md"
    workspace = tmp_path / "work"
    assert main(["--workspace", str(workspace), "run", "--root", str(base), "--chapter", str(chapter)]) == 0
    record = json.loads(capsys.readouterr().out)
    assert record["status"] == "waiting_review"
    rid = record["run_id"]
    assert main(["--workspace", str(workspace), "approve", rid]) == 0
    capsys.readouterr()
    assert main(["--workspace", str(workspace), "run", "--resume", rid]) == 0
    record = json.loads(capsys.readouterr().out)
    assert record["status"] == "completed"
    assert Path(record["package"]).is_file()


def test_validation_missing_storyboard(tmp_path):
    with pytest.raises(FileNotFoundError):
        validate_drafts(tmp_path)


def test_pub_disabled():
    pub = Publisher({"enabled": False})
    pub.publish({"type": "test"})
    pub.close()


def test_external_plugin_requires_both_allowlists(monkeypatch):
    from youtube_videos.core import registry

    class FakeEntry:
        name = "pace_estimator"
        dist = type("Dist", (), {"name": "ytv-pace-estimator"})()
        def load(self):
            class Plugin:
                pass
            return Plugin

    monkeypatch.setattr(registry, "entry_points", lambda group: [FakeEntry()])
    assert "pace_estimator" not in registry.Registry(["ytv-pace-estimator"], []).list()
    assert "pace_estimator" not in registry.Registry([], ["pace_estimator"]).list()
    assert "pace_estimator" in registry.Registry(["ytv-pace-estimator"], ["pace_estimator"]).list()
