import json
from pathlib import Path
from typing import Any


DATA_DIR = Path("data")
CONFIG_PATH = DATA_DIR / "config.json"


class ConfigManager:
    def __init__(self, path: Path = CONFIG_PATH):
        self._path = path

    def load(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            # utf-8-sig lida com BOM gerado pelo PowerShell
            return json.loads(self._path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError):
            return {}

    def save(self, config: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def get(self, *keys: str, default: Any = None) -> Any:
        value = self.load()
        for key in keys:
            if not isinstance(value, dict):
                return default
            value = value.get(key)
        return value if value is not None else default

    def set(self, *keys: str, value: Any) -> None:
        config = self.load()
        d = config
        for key in keys[:-1]:
            d = d.setdefault(key, {})
        d[keys[-1]] = value
        self.save(config)

    def is_setup_complete(self) -> bool:
        return bool(self.get("setup_completed"))

    def get_gemini_key(self) -> str | None:
        return self.get("gemini", "api_key")

    def get_database_url(self) -> str:
        return self.get(
            "database_url",
            default="postgresql://jobapplier:jobapplier@localhost:5432/jobapplier",
        )

    def get_target_companies(self) -> dict:
        return {
            "greenhouse": self.get("coleta", "empresas_greenhouse", default=[]),
            "lever": self.get("coleta", "empresas_lever", default=[]),
        }

    def get_scoring_thresholds(self) -> tuple[int, int]:
        """Retorna (threshold_excelente, threshold_bom)."""
        excelente = int(self.get("scoring", "threshold_excelente", default=85))
        bom = int(self.get("scoring", "threshold_bom", default=70))
        return excelente, bom
