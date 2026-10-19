# Add-on example: pace estimator

This is an **independently installable Python distribution**. It demonstrates that no core code changes are needed to add a new workflow stage.

```
python -m pip install -e ./extensions/pace-estimator
```

Edit `config/config.yaml`:

```yaml
plugins:
  allow_distributions: [ytv-pace-estimator]
  allow_external_ids: [pace_estimator]
```

Run `youtube-videos run --workflow technical_lesson_with_pace --root . --chapter examples/sample-chapter.md`.

The workflow group demonstrates insertion of the `pace_estimator` stage after storyboard production. It calculates *rough* spoken-word time from current editable narration, not a final video duration. Its returned state is stored by the core executor and emitted to the durable event log. Keep new output-artifact files inside the approval snapshot or add a separate explicit gate when extending the review surface.
