"""A no-side-effect demonstration plugin. Planning estimates are not measured duration."""
from youtube_videos.core.models import StageContext, StageResult


class PaceEstimator:
    id = "pace_estimator"

    def run(self, ctx: StageContext) -> StageResult:
        path = ctx.draft_dir / "narration.md"
        count = len(path.read_text(encoding="utf-8").split())
        wpm = max(80, min(240, int(ctx.params.get("words_per_minute", 135))))
        return StageResult({"words": count, "nominal_wpm": wpm,
                            "estimated_seconds": round(60 * count / wpm, 1),
                            "qualification": "estimate_only_unrevised_narration"})
