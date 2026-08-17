"""Compatibilidade — use ``agents.llm`` em código novo.

Este módulo era o cliente Gemini único do projeto. A implementação foi para
``agents/llm/`` quando o projeto passou a suportar OpenAI e Anthropic. O que
resta aqui é fachada para não quebrar importação antiga.

Migração:

    from agents.gemini_client import GeminiClient        # antigo
    client = GeminiClient(api_key=key, use_cache=True)

    from agents.llm import get_client                    # novo
    client = get_client()   # resolve provedor por config/ambiente
"""
import warnings

from agents.llm import testar_conexao
from agents.llm.providers import GeminiClient as _GeminiClient

DEFAULT_MODEL = _GeminiClient.modelo_padrao
DEFAULT_CACHE_TTL_HOURS = 24


class GeminiClient(_GeminiClient):
    """Assinatura antiga (``model=``, ``cache_ttl_hours=``) sobre o cliente novo."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        cache_ttl_hours: int = DEFAULT_CACHE_TTL_HOURS,
        use_cache: bool = True,
    ):
        warnings.warn(
            "agents.gemini_client.GeminiClient está depreciado. "
            "Use agents.llm.get_client(), que respeita o provedor configurado.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(
            api_key=api_key,
            modelo=model,
            cache_ttl_horas=cache_ttl_hours,
            use_cache=use_cache,
        )

    #: Nome antigo do atributo de modelo.
    @property
    def model_name(self) -> str:
        return self.modelo

    @classmethod
    def test_connection(cls, api_key: str) -> tuple[bool, str]:
        return testar_conexao("gemini", api_key=api_key)


__all__ = ["DEFAULT_CACHE_TTL_HOURS", "DEFAULT_MODEL", "GeminiClient"]
