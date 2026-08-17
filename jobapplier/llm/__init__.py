"""Camada de LLM com múltiplos provedores.

Ponto único de entrada para qualquer chamada de modelo no projeto. Nenhum módulo
deve instanciar SDK de provedor direto.

    from jobapplier.llm import get_client
    client = get_client()                      # resolve provedor pela config/ambiente
    texto = client.generate(prompt)
    dados = client.generate_json(prompt)

Resolução do provedor, em ordem:

1. Argumento explícito ``get_client(provedor="openai")``
2. ``AIJOB_LLM_PROVEDOR`` no ambiente
3. ``llm.provedor`` em data/config.json
4. Autodetecção: primeiro provedor com chave disponível

A autodetecção existe para o caso concreto de trocar de provedor: quem tinha
Gemini e passou a ter ChatGPT só precisa preencher AIJOB_OPENAI_API_KEY — nada
mais muda.
"""
import logging

from .base import (
    LLMClient,
    LLMDependenciaAusente,
    LLMError,
    LLMRespostaVazia,
    LLMSemChave,
    extrair_json,
)
from .providers import (
    MODELOS_SUGERIDOS,
    PROVEDORES,
    AnthropicClient,
    GeminiClient,
    OpenAIClient,
)

logger = logging.getLogger(__name__)

#: Ordem de preferência da autodetecção e do fallback.
ORDEM_PADRAO = ("openai", "gemini", "anthropic")

__all__ = [
    "MODELOS_SUGERIDOS",
    "ORDEM_PADRAO",
    "PROVEDORES",
    "AnthropicClient",
    "GeminiClient",
    "LLMClient",
    "LLMDependenciaAusente",
    "LLMError",
    "LLMRespostaVazia",
    "LLMSemChave",
    "OpenAIClient",
    "chave_do_provedor",
    "extrair_json",
    "get_client",
    "provedores_configurados",
    "testar_conexao",
]


def _caminhos_config(provedor: str) -> tuple[str, ...]:
    # Gemini mantém o caminho legado gemini.api_key; os novos ficam sob llm.
    if provedor == "gemini":
        return ("gemini", "api_key")
    return ("llm", provedor, "api_key")


def chave_do_provedor(provedor: str, config=None) -> str | None:
    """Chave de API do provedor: ambiente primeiro, config.json depois."""
    from jobapplier.config import secrets

    classe = PROVEDORES.get(provedor)
    if classe is None:
        return None
    return secrets.obter(classe.env_chave, *_caminhos_config(provedor), config=config)


def provedores_configurados(config=None) -> list[str]:
    """Provedores com chave disponível, na ordem de preferência."""
    return [p for p in ORDEM_PADRAO if chave_do_provedor(p, config=config)]


def _resolver_provedor(provedor: str | None, config) -> str:
    if provedor:
        return provedor.lower()

    from jobapplier.config import secrets

    do_ambiente = secrets.obter("LLM_PROVEDOR", "llm", "provedor", config=config)
    if do_ambiente:
        return do_ambiente.lower()

    disponiveis = provedores_configurados(config=config)
    if not disponiveis:
        raise LLMSemChave(
            "Nenhum provedor de LLM configurado. Defina uma destas no .env: "
            + ", ".join(f"AIJOB_{PROVEDORES[p].env_chave}" for p in ORDEM_PADRAO)
        )
    escolhido = disponiveis[0]
    logger.info("Provedor de LLM autodetectado: %s", escolhido)
    return escolhido


def _construir(provedor: str, config, modelo=None, use_cache=True) -> LLMClient:
    classe = PROVEDORES.get(provedor)
    if classe is None:
        raise LLMError(
            f"Provedor '{provedor}' desconhecido. Disponíveis: {', '.join(PROVEDORES)}"
        )

    chave = chave_do_provedor(provedor, config=config)
    if not chave:
        raise LLMSemChave(
            f"Provedor '{provedor}' selecionado mas sem chave. "
            f"Defina AIJOB_{classe.env_chave} no .env."
        )

    if modelo is None:
        from jobapplier.config import secrets

        modelo = secrets.obter("LLM_MODELO", "llm", "modelo", config=config)

    return classe(api_key=chave, modelo=modelo, use_cache=use_cache)


class ClienteComFallback:
    """Encadeia provedores: se o primeiro falhar, tenta o próximo.

    Serve o caso real de cota estourada no meio de um ciclo — sem isso, todas as
    vagas restantes falham. Não é subclasse de LLMClient de propósito: só
    reexpõe a interface pública, sem cache nem retry próprios (cada cliente
    encadeado já tem os seus).
    """

    def __init__(self, clientes: list[LLMClient]):
        if not clientes:
            raise LLMSemChave("ClienteComFallback exige ao menos um cliente")
        self._clientes = clientes

    @property
    def primario(self) -> LLMClient:
        return self._clientes[0]

    @property
    def modelo_completo(self) -> str:
        return " → ".join(c.modelo_completo for c in self._clientes)

    def __repr__(self) -> str:
        return f"<ClienteComFallback {self.modelo_completo}>"

    def _tentar(self, metodo: str, *args, **kwargs):
        erros = []
        for i, cliente in enumerate(self._clientes):
            try:
                return getattr(cliente, metodo)(*args, **kwargs)
            except Exception as exc:
                erros.append(f"{cliente.modelo_completo}: {exc}")
                restantes = len(self._clientes) - i - 1
                if restantes:
                    logger.warning(
                        "Provedor %s falhou (%s). Caindo para o próximo.",
                        cliente.modelo_completo, exc,
                    )
        raise LLMError("Todos os provedores falharam — " + " | ".join(erros))

    def generate(self, prompt: str, temperature: float = 0.2) -> str:
        return self._tentar("generate", prompt, temperature=temperature)

    def generate_json(self, prompt: str, temperature: float = 0.1):
        return self._tentar("generate_json", prompt, temperature=temperature)


def get_client(
    config=None,
    provedor: str | None = None,
    modelo: str | None = None,
    use_cache: bool = True,
    com_fallback: bool | None = None,
):
    """Constrói o cliente de LLM conforme config/ambiente.

    ``com_fallback`` omitido usa ``llm.fallback`` da config: lista de provedores
    a tentar em sequência, ou ``true`` para usar todos os configurados.
    """
    if config is None:
        from jobapplier.config.manager import ConfigManager

        config = ConfigManager()

    principal = _resolver_provedor(provedor, config)
    cliente = _construir(principal, config, modelo=modelo, use_cache=use_cache)

    if com_fallback is False:
        return cliente

    cfg_fallback = (config.get("llm") or {}).get("fallback") if com_fallback is None else com_fallback
    if not cfg_fallback:
        return cliente

    if cfg_fallback is True:
        nomes = [p for p in provedores_configurados(config=config) if p != principal]
    else:
        nomes = [str(p).lower() for p in cfg_fallback if str(p).lower() != principal]

    cadeia = [cliente]
    for nome in nomes:
        try:
            cadeia.append(_construir(nome, config, use_cache=use_cache))
        except LLMError as exc:
            logger.debug("Fallback '%s' indisponível: %s", nome, exc)

    if len(cadeia) == 1:
        return cliente

    logger.info("Cadeia de LLM: %s", " → ".join(c.modelo_completo for c in cadeia))
    return ClienteComFallback(cadeia)


def testar_conexao(
    provedor: str, api_key: str | None = None, modelo: str | None = None
) -> tuple[bool, str]:
    """Valida chave e modelo com uma chamada mínima, sem cache."""
    classe = PROVEDORES.get((provedor or "").lower())
    if classe is None:
        return False, f"Provedor '{provedor}' desconhecido"

    chave = api_key or chave_do_provedor(provedor)
    if not chave:
        return False, f"Sem chave para '{provedor}'. Defina AIJOB_{classe.env_chave}."

    try:
        return classe(api_key=chave, modelo=modelo, use_cache=False).testar()
    except Exception as exc:
        return False, str(exc)
