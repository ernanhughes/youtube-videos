"""Explicit plugins; allowlist *both* external distribution name and plugin ID."""
from __future__ import annotations
from importlib.metadata import entry_points


class Registry:
    def __init__(self, allow_distributions: list[str] | None = None,
                 allow_external_ids: list[str] | None = None):
        from youtube_videos.plugins.builtin import BUILTINS
        self.plugins = dict(BUILTINS)
        distributions = set(allow_distributions or [])
        identifiers = set(allow_external_ids or [])
        if not distributions or not identifiers:
            return
        for entry in entry_points(group="youtube_videos.plugins"):
            dist = entry.dist.name if entry.dist else ""
            if entry.name in identifiers and dist in distributions:
                if entry.name in self.plugins:
                    raise ValueError(f"External plugin cannot replace builtin {entry.name}")
                self.plugins[entry.name] = entry.load()()

    def get(self, name: str):
        if name not in self.plugins:
            raise ValueError(f"Unknown or disallowed plugin: {name}")
        return self.plugins[name]

    def list(self) -> list[str]:
        return sorted(self.plugins)
