"""Configuration loading: settings, thresholds and the control catalog."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@dataclass
class Config:
    root: Path
    settings: dict[str, Any]
    thresholds: dict[str, Any]

    @classmethod
    def load(cls, root: Path | None = None) -> Config:
        root = root or ROOT
        return cls(
            root=root,
            settings=load_yaml(root / "config" / "settings.yaml"),
            thresholds=load_yaml(root / "config" / "thresholds.yaml"),
        )

    def path(self, key: str) -> Path:
        return self.root / self.settings["paths"][key]

    # -- threshold helpers -------------------------------------------------------------------
    def uit_by_year(self) -> dict[int, float]:
        return {int(y): float(v["value"]) for y, v in self.thresholds["uit_pen"].items()}

    def minor_limit_pen(self, year: int) -> float:
        uit = self.uit_by_year()
        year = year if year in uit else max(uit)
        return uit[year] * float(self.thresholds["minor_purchase_limit_uit"]["value"])

    def resolve(self, dotted: str) -> Any:
        """Resolve a dotted reference such as ``amendment_increase_cap.value``."""
        node: Any = self.thresholds
        for part in dotted.split("."):
            node = node[part]
        return node

    def to_verify(self) -> list[str]:
        """List every threshold entry still flagged ``to_verify``."""
        found: list[str] = []

        def walk(node: Any, trail: str) -> None:
            if isinstance(node, dict):
                if node.get("status") == "to_verify":
                    found.append(trail)
                for key, value in node.items():
                    walk(value, f"{trail}.{key}" if trail else str(key))

        walk(self.thresholds, "")
        return found
