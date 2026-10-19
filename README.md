# YouTube Videos — YT01

**Plugin-first, human-reviewed technical lesson production from Hugo book chapters.**

YT01 is a working foundation for producing evidence-linked *lesson drafts*, not audiobook narration. It reads Hugo chapter Markdown, makes a lesson plan, builds a source/evidence map, assembles storyboard scenes and editable narration/slide drafts, supports an optional CoCoder walkthrough manifest, and packages the exact human-approved materials. It does **not** execute code, verify internet citations, synthesize audio, render MP4, or upload to YouTube.

Existing `Text_to_Video.ipynb` stays untouched: extract this overlay into your current `youtube-videos` checkout.

## Install (Windows PowerShell)

```powershell
cd C:\Projects\youtube-videos
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[dev,zmq]'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\youtube-videos.exe validate
.\.venv\Scripts\youtube-videos.exe plugins
```

## First complete lesson

```powershell
.\.venv\Scripts\youtube-videos.exe run --root . --chapter examples/sample-chapter.md
# => status waiting_review, run_id yt_..., draft_dir ...\.ytv\runs\yt_...\drafts
# Edit narration.md, slides.md, storyboard.json, evidence.json, lesson.json in that directory.
.\.venv\Scripts\youtube-videos.exe approve yt_YOUR_RUN_ID
.\.venv\Scripts\youtube-videos.exe run --resume yt_YOUR_RUN_ID
# => completed, .ytv\runs\yt_...\lesson_package.zip
.\.venv\Scripts\youtube-videos.exe show yt_YOUR_RUN_ID
.\.venv\Scripts\youtube-videos.exe events yt_YOUR_RUN_ID
```

Default work data is stored in `.ytv/`. **Append `.ytv/` to the existing repository `.gitignore`** (see `GITIGNORE-YT01.additions.txt`); the overlay intentionally does not overwrite the existing `.gitignore`. Set `--workspace <path>` **before** the subcommand to redirect it.

## Process a chapter from programmer.ie

```powershell
.\.venv\Scripts\youtube-videos.exe run `
  --root C:\Projects\programmer.ie `
  --chapter content\books\pi\06-chapter.md
```

Source roots are a security boundary; the input chapter must be inside `--root`. You can add a captured CoCoder walkthrough via `--cocoder-manifest C:\Projects\programmer.ie\examples\walkthrough.json`. This file must be within the selected root and must have `{"steps": [{"id": "..."}]}`. This adapter never runs CoCoder itself.

## Workflows and plugins

`config/config.yaml` chooses Hydra config groups; override the config root with the `YTV_CONFIG_DIR` environment variable if required. `config/workflow/technical_lesson.yaml` declares stages, their plugin IDs and dependencies. Use `--workflow some_other_config` to select a new YAML workflow group under `config/workflow/`. Change `config/events/local.yaml` to `--events zmq` to enable a PUB channel (the publisher binds TCP port 5589 by default). ZeroMQ is optional; database events are always durable.

An external distribution registers plugin IDs in `youtube_videos.plugins` entry points. To load one, place its distribution name **and** plugin ID in `plugins.allow_distributions` and `plugins.allow_external_ids`. Plugin instances implement `run(StageContext) -> StageResult`. Never install untrusted plugins: they run in-process with full Python privileges.

Example external entry points:

```toml
[project.entry-points."youtube_videos.plugins"]
my_diagram = "my_plugin.diagram:DiagramPlugin"
```

```yaml
# config/config.yaml
plugins:
  allow_distributions: [my-youtube-diagrams]
  allow_external_ids: [my_diagram]
```

In your workflow, add a stage with `plugin: my_diagram` and explicit `needs: [...]`. Plugin outputs are JSON-serializable dictionaries. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/NEXT-MILESTONES.md](docs/NEXT-MILESTONES.md) for runtime contracts and the YT02–YT06 plan.

## Review and integrity rules

The approval gate computes a SHA-256 over the five editable draft files. Any edit between approval and packaging invalidates approval, and the run stops again for review. Stage results and events persist in `.ytv/state.sqlite3`; the lesson package includes its source snapshot and SHA-256 evidence manifest. This is not a fact-checking guarantee: citations remain *unverified*, and chapter code remains *unexecuted*.

The initial runner is intentionally **single-process**; it does not claim distributed retries, concurrent worker leasing, sandboxing, citation validation, or media-generation capacity. The optional ZeroMQ PUB socket is not a durable job queue. Use the SQLite event log to replay missed notifications.

## Minimum acceptance sequence

1. `pytest -q` passes.
2. `run` creates a draft bundle but no ZIP.
3. `approve` records the exact file hash; `run --resume` packages it.
4. Changing narration between approval and resume pauses review again.
5. The resulting ZIP contains `chapter_source.md`, the five editable draft files, `source_index.json`, and `manifest.json` with hashes and honest verification status.
6. Existing `Text_to_Video.ipynb` is not overwritten.

## Independently installable example plugin

See [`extensions/pace-estimator/`](extensions/pace-estimator/README.md) for a complete external distribution with a Python entry point. The workflow `technical_lesson_with_pace` inserts the stage without modifying the engine. Loading remains disabled until both the package distribution and plugin ID are explicitly allowlisted.
