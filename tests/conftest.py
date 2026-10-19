from pathlib import Path
import pytest
from youtube_videos.core.config import load_config
from youtube_videos.core.engine import Engine

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def prepared(tmp_path):
    root = tmp_path / "sources"
    root.mkdir()
    chapter = root / "sample.md"
    chapter.write_bytes((ROOT / "examples" / "sample-chapter.md").read_bytes())
    config = load_config()
    engine = Engine(tmp_path / "workspace")
    run_id = engine.new_run(chapter, root, config)
    yield engine, run_id, root, chapter
    engine.close()
