import json
from pathlib import Path
from typing import Any

from jobapplier import paths

DATA_DIR = paths.DATA
CONFIG_PATH = paths.CONFIG_JSON


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
        # Delega para config.secrets: ambiente (.env) tem precedência sobre o
        # JSON. Import local evita ciclo — secrets importa ConfigManager para o
        # fallback. Passa self para que o fallback leia ESTE arquivo de config.
        from jobapplier.config import secrets

        return secrets.gemini_api_key(config=self)

    def get_database_url(self) -> str:
        from jobapplier.config import secrets

        return secrets.database_url(config=self)

    def empresas(self, plataforma: str) -> list:
        """Slugs de empresa da plataforma, sempre em `coleta.empresas_<p>`.

        Um padrão só para todas. Antes cada plataforma inventava o seu —
        `gupy.search_keywords` num lugar, `linkedin.search_queries` noutro,
        `get_target_companies()` só para duas — e quem adicionava plataforma
        nova copiava o padrão errado.
        """
        return self.get("coleta", f"empresas_{plataforma.lower()}", default=[]) or []

    def keywords(self, plataforma: str) -> list:
        """Palavras-chave de busca da plataforma, em `coleta.keywords_<p>`."""
        return self.get("coleta", f"keywords_{plataforma.lower()}", default=[]) or []

    def get_target_companies(self) -> dict:
        """Legado: prefira `empresas(plataforma)`."""
        return {
            "greenhouse": self.empresas("greenhouse"),
            "lever": self.empresas("lever"),
        }

    # get_scoring_thresholds() foi removido: era código morto e, pior, declarava
    # default 85/70 enquanto o orquestrador usa 65/45. Dois valores contraditórios
    # para "que score autoriza uma candidatura", sem ninguém notar, porque um
    # deles nunca era chamado.
    #
    # Os thresholds ativos vivem em orchestrator._executar_pipeline. O número NÃO
    # é calibrado — score de LLM não é probabilidade. Antes de mexer nele, rode em
    # modo sombra e compare a decisão do sistema com a sua. Ver CLAUDE.md.
