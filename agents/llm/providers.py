"""Provedores concretos de LLM: Gemini, OpenAI e Anthropic.

Cada SDK é importado **dentro** do construtor, não no topo do módulo. Isso
permite ao projeto rodar com apenas um provedor instalado — importar
``agents.llm`` não exige ter os três SDKs.

Nota: os nomes de módulo aqui não colidem com os pacotes ``openai`` /
``anthropic`` do site-packages porque Python 3 usa import absoluto.
"""
import logging

from .base import LLMClient, LLMDependenciaAusente, LLMRespostaVazia

logger = logging.getLogger(__name__)


def _exigir(pacote: str, pip: str):
    try:
        return __import__(pacote)
    except ImportError as exc:
        raise LLMDependenciaAusente(
            f"SDK '{pacote}' não instalado. Rode: pip install {pip}"
        ) from exc


# ── Gemini ────────────────────────────────────────────────────────────────────

class GeminiClient(LLMClient):
    provedor = "gemini"
    modelo_padrao = "gemini-2.5-flash"
    pacote_pip = "google-genai"
    env_chave = "GEMINI_API_KEY"

    def __init__(self, api_key, modelo=None, **kwargs):
        super().__init__(api_key, modelo, **kwargs)
        _exigir("google.genai", self.pacote_pip)
        from google import genai

        self._sdk = genai.Client(api_key=self.api_key)

    def _config(self, temperature: float, json_nativo: bool = False):
        from google.genai import types

        kwargs = {"temperature": temperature}
        if json_nativo:
            # Mais confiável que instruir no prompt e limpar cerca depois.
            kwargs["response_mime_type"] = "application/json"
        return types.GenerateContentConfig(**kwargs)

    def _gerar_texto(self, prompt: str, temperature: float) -> str:
        resposta = self._sdk.models.generate_content(
            model=self.modelo, contents=prompt, config=self._config(temperature),
        )
        if resposta.text is None:
            raise LLMRespostaVazia(
                f"[gemini] text=None — provável bloqueio de safety ou limite de tokens "
                f"(finish_reason={getattr(resposta, 'candidates', None) and resposta.candidates[0].finish_reason})"
            )
        return resposta.text

    def _gerar_json_nativo(self, prompt: str, temperature: float) -> str | None:
        resposta = self._sdk.models.generate_content(
            model=self.modelo,
            contents=prompt,
            config=self._config(temperature, json_nativo=True),
        )
        if resposta.text is None:
            raise LLMRespostaVazia("[gemini] modo JSON devolveu text=None")
        return resposta.text


# ── OpenAI ────────────────────────────────────────────────────────────────────

class OpenAIClient(LLMClient):
    provedor = "openai"
    # Tier de custo baixo por padrão, coerente com o resto do projeto (o
    # pipeline 4A/4B existe justamente para economizar chamada de LLM). Para
    # mais capacidade: gpt-5.6-terra (equilibrado) ou gpt-5.6-sol (frontier).
    modelo_padrao = "gpt-5.6-luna"
    pacote_pip = "openai"
    env_chave = "OPENAI_API_KEY"

    def __init__(self, api_key, modelo=None, **kwargs):
        super().__init__(api_key, modelo, **kwargs)
        _exigir("openai", self.pacote_pip)
        from openai import OpenAI

        self._sdk = OpenAI(api_key=self.api_key)

    def _chamar(self, prompt: str, temperature: float, response_format=None) -> str:
        kwargs = {
            "model": self.modelo,
            "messages": [{"role": "user", "content": prompt}],
        }
        # Modelos de raciocínio da família GPT-5 rejeitam temperature custom;
        # só envia quando não é o default.
        if temperature is not None and temperature != 1.0:
            kwargs["temperature"] = temperature
        if response_format:
            kwargs["response_format"] = response_format

        try:
            resposta = self._sdk.chat.completions.create(**kwargs)
        except Exception as exc:
            # Modelo que recusa temperature: repete sem o parâmetro em vez de
            # falhar a candidatura inteira.
            if "temperature" in str(exc).lower() and "temperature" in kwargs:
                logger.debug("[openai] %s não aceita temperature, repetindo sem.", self.modelo)
                kwargs.pop("temperature")
                resposta = self._sdk.chat.completions.create(**kwargs)
            else:
                raise

        conteudo = resposta.choices[0].message.content
        if conteudo is None:
            raise LLMRespostaVazia(
                f"[openai] content=None (finish_reason={resposta.choices[0].finish_reason})"
            )
        return conteudo

    def _gerar_texto(self, prompt: str, temperature: float) -> str:
        return self._chamar(prompt, temperature)

    def _gerar_json_nativo(self, prompt: str, temperature: float) -> str | None:
        # json_object (JSON mode) e não json_schema: o contrato interno
        # generate_json não recebe schema. Exige a palavra "JSON" no prompt, que
        # a base já garante.
        return self._chamar(prompt, temperature, response_format={"type": "json_object"})


# ── Anthropic ─────────────────────────────────────────────────────────────────

class AnthropicClient(LLMClient):
    provedor = "anthropic"
    modelo_padrao = "claude-sonnet-5"
    pacote_pip = "anthropic"
    env_chave = "ANTHROPIC_API_KEY"
    max_tokens = 8192

    def __init__(self, api_key, modelo=None, **kwargs):
        super().__init__(api_key, modelo, **kwargs)
        _exigir("anthropic", self.pacote_pip)
        from anthropic import Anthropic

        self._sdk = Anthropic(api_key=self.api_key)

    def _chamar(self, prompt: str, temperature: float, prefill: str | None = None) -> str:
        mensagens = [{"role": "user", "content": prompt}]
        if prefill:
            mensagens.append({"role": "assistant", "content": prefill})

        resposta = self._sdk.messages.create(
            model=self.modelo,
            max_tokens=self.max_tokens,
            temperature=temperature,
            messages=mensagens,
        )
        partes = [b.text for b in resposta.content if getattr(b, "type", "") == "text"]
        if not partes:
            raise LLMRespostaVazia(
                f"[anthropic] nenhum bloco de texto (stop_reason={resposta.stop_reason})"
            )
        texto = "".join(partes)
        # Com prefill, a resposta continua de onde o prefill parou — recompõe.
        return (prefill + texto) if prefill else texto

    def _gerar_texto(self, prompt: str, temperature: float) -> str:
        return self._chamar(prompt, temperature)

    def _gerar_json_nativo(self, prompt: str, temperature: float) -> str | None:
        # A API não tem modo JSON; prefill com '{' é a forma canônica de impedir
        # prosa antes do objeto.
        return self._chamar(prompt, temperature, prefill="{")


# ── Catálogo ──────────────────────────────────────────────────────────────────

PROVEDORES: dict[str, type[LLMClient]] = {
    "gemini": GeminiClient,
    "openai": OpenAIClient,
    "anthropic": AnthropicClient,
}

#: Modelos sugeridos por provedor, do mais barato ao mais capaz. Só rótulos
#: para a UI — qualquer ID aceito pelo provedor funciona via llm.modelo.
MODELOS_SUGERIDOS: dict[str, list[tuple[str, str]]] = {
    "gemini": [
        ("gemini-2.5-flash", "Flash — rápido e barato (padrão)"),
        ("gemini-2.5-pro", "Pro — mais capaz"),
    ],
    "openai": [
        ("gpt-5.6-luna", "Luna — custo baixo (padrão)"),
        ("gpt-5.6-terra", "Terra — equilibrado"),
        ("gpt-5.6-sol", "Sol — frontier, trabalho complexo"),
    ],
    "anthropic": [
        ("claude-haiku-4-5-20251001", "Haiku 4.5 — rápido e barato"),
        ("claude-sonnet-5", "Sonnet 5 — equilibrado (padrão)"),
        ("claude-opus-5", "Opus 5 — mais capaz"),
    ],
}
