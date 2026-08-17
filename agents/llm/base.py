"""Contrato comum de LLM: cache, retry e JSON.

Todo provedor herda ``LLMClient`` e implementa apenas ``_gerar_texto`` e,
opcionalmente, ``_gerar_json_nativo``. Cache em banco, retry com backoff e
extração de JSON de cerca markdown ficam aqui — não devem ser reimplementados
por provedor.
"""
import hashlib
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

DEFAULT_CACHE_TTL_HORAS = 24
MAX_TENTATIVAS = 5
DELAY_INICIAL = 15
DELAY_MAXIMO = 60

# Trechos que indicam limite de taxa / sobrecarga, em qualquer provedor. Casar
# por texto evita importar as classes de exceção de cada SDK só para o retry.
_SINAIS_RATE_LIMIT = (
    "429", "529", "rate limit", "rate_limit", "quota", "resource_exhausted",
    "overloaded", "too many requests", "capacity",
)


class LLMError(Exception):
    """Erro genérico de provedor."""


class LLMSemChave(LLMError):
    """Nenhuma chave de API configurada para o provedor."""


class LLMDependenciaAusente(LLMError):
    """SDK do provedor não instalado."""


class LLMRespostaVazia(LLMError):
    """Provedor devolveu resposta vazia (bloqueio de safety, limite de tokens).

    Existe porque o código antigo fazia ``response.text.strip()`` direto: quando
    o Gemini bloqueava por safety, ``text`` vinha None e estourava
    AttributeError, engolido por ``except Exception`` genérico — a vaga era
    pulada em silêncio, sem indicação da causa.
    """


def agora_utc() -> datetime:
    """UTC naive, compatível com as colunas do banco."""
    return datetime.now(UTC).replace(tzinfo=None)


def extrair_json(texto: str):
    """Converte texto de LLM em objeto Python, tolerando cerca markdown.

    Provedores com modo JSON nativo devolvem JSON puro; os que não têm às vezes
    embrulham em ```json ... ```. Como último recurso, recorta do primeiro
    delimitador de objeto/array até o último.
    """
    if texto is None:
        raise LLMRespostaVazia("provedor devolveu None em vez de texto")

    limpo = texto.strip()
    if not limpo:
        raise LLMRespostaVazia("provedor devolveu string vazia")

    cerca = re.match(r"^```(?:json|JSON)?\s*\n(.*?)\n?```$", limpo, re.DOTALL)
    if cerca:
        limpo = cerca.group(1).strip()

    try:
        return json.loads(limpo)
    except json.JSONDecodeError:
        pass

    # Recorte entre delimitadores. Cobre o caso de o modelo prefixar prosa.
    for abre, fecha in (("{", "}"), ("[", "]")):
        inicio, fim = limpo.find(abre), limpo.rfind(fecha)
        if inicio != -1 and fim > inicio:
            try:
                return json.loads(limpo[inicio:fim + 1])
            except json.JSONDecodeError:
                continue

    raise json.JSONDecodeError("resposta não contém JSON válido", limpo, 0)


class LLMClient(ABC):
    """Cliente de LLM com cache e retry.

    Subclasses definem ``provedor``, ``modelo_padrao`` e ``_gerar_texto``.
    """

    provedor: str = ""
    modelo_padrao: str = ""
    #: Nome do pacote pip, usado na mensagem de erro quando o SDK falta.
    pacote_pip: str = ""
    #: Sufixo da variável de ambiente (após AIJOB_).
    env_chave: str = ""

    def __init__(
        self,
        api_key: str,
        modelo: str | None = None,
        cache_ttl_horas: int = DEFAULT_CACHE_TTL_HORAS,
        use_cache: bool = True,
    ):
        if not api_key:
            raise LLMSemChave(
                f"Provedor '{self.provedor}' sem chave. Defina AIJOB_{self.env_chave} no .env."
            )
        self.api_key = api_key
        self.modelo = modelo or self.modelo_padrao
        self.cache_ttl_horas = cache_ttl_horas
        self.use_cache = use_cache

    # ── Identidade ────────────────────────────────────────────────────────────

    @property
    def modelo_completo(self) -> str:
        """Identificador estável para cache e log: 'provedor:modelo'."""
        return f"{self.provedor}:{self.modelo}"

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.modelo_completo}>"

    # ── A implementar por provedor ────────────────────────────────────────────

    @abstractmethod
    def _gerar_texto(self, prompt: str, temperature: float) -> str:
        """Uma chamada ao provedor. Não trata retry nem cache."""

    def _gerar_json_nativo(self, prompt: str, temperature: float) -> str | None:
        """Chamada em modo JSON nativo, se o provedor tiver.

        Retornar None faz o cliente cair no caminho genérico (instrução no
        prompt + extração tolerante).
        """
        return None

    def _e_rate_limit(self, exc: Exception) -> bool:
        return any(s in str(exc).lower() for s in _SINAIS_RATE_LIMIT)

    # ── Cache ─────────────────────────────────────────────────────────────────

    def _chave_cache(self, prompt: str, modo: str) -> str:
        # provedor e modo entram na chave: o mesmo prompt em modo JSON nativo
        # produz resposta diferente do modo texto, e provedores distintos não
        # devem compartilhar entrada.
        bruto = f"{self.modelo_completo}:{modo}:{prompt}"
        return hashlib.sha256(bruto.encode("utf-8")).hexdigest()

    def _ler_cache(self, chave: str) -> str | None:
        if not self.use_cache:
            return None
        try:
            from database.connection import get_session
            from database.repository import CacheGeminiRepository

            with get_session() as session:
                entrada = CacheGeminiRepository(session).get(chave)
                if entrada:
                    logger.debug("Cache hit %s (%s)", chave[:8], self.modelo_completo)
                    return entrada.resposta
        except Exception as exc:
            logger.warning("Leitura de cache falhou: %s", exc)
        return None

    def _gravar_cache(self, chave: str, resposta: str) -> None:
        if not self.use_cache:
            return
        try:
            from database.connection import get_session
            from database.models import CacheGemini
            from database.repository import CacheGeminiRepository

            with get_session() as session:
                CacheGeminiRepository(session).set(
                    CacheGemini(
                        chave_hash=chave,
                        # Guarda 'provedor:modelo' — o schema atual tem só a
                        # coluna 'modelo'. Fase 1 renomeia a tabela para
                        # cache_llm com coluna 'provedor' própria.
                        modelo=self.modelo_completo[:100],
                        resposta=resposta,
                        criado_em=agora_utc(),
                        expira_em=agora_utc() + timedelta(hours=self.cache_ttl_horas),
                    )
                )
        except Exception as exc:
            logger.warning("Gravação de cache falhou: %s", exc)

    # ── Retry ─────────────────────────────────────────────────────────────────

    def _com_retry(self, fn, *args) -> str:
        delay = DELAY_INICIAL
        ultimo_erro: Exception | None = None

        for tentativa in range(1, MAX_TENTATIVAS + 1):
            try:
                return fn(*args)
            except Exception as exc:
                ultimo_erro = exc
                if not self._e_rate_limit(exc) or tentativa == MAX_TENTATIVAS:
                    raise
                logger.warning(
                    "[%s] limite de taxa. Aguardando %ds (tentativa %d/%d): %s",
                    self.provedor, delay, tentativa, MAX_TENTATIVAS, exc,
                )
                time.sleep(delay)
                delay = min(delay * 2, DELAY_MAXIMO)

        # Inalcançável: o loop sempre retorna ou levanta. Presente para que
        # nenhum caminho devolva None implicitamente.
        raise LLMError(f"[{self.provedor}] falhou após {MAX_TENTATIVAS} tentativas") from ultimo_erro

    # ── API pública ───────────────────────────────────────────────────────────

    def generate(self, prompt: str, temperature: float = 0.2) -> str:
        chave = self._chave_cache(prompt, "texto")
        if (cacheado := self._ler_cache(chave)) is not None:
            return cacheado

        texto = self._com_retry(self._gerar_texto, prompt, temperature)
        if not texto:
            raise LLMRespostaVazia(f"[{self.provedor}] resposta vazia para prompt de {len(prompt)} chars")

        self._gravar_cache(chave, texto)
        return texto

    def generate_json(self, prompt: str, temperature: float = 0.1):
        chave = self._chave_cache(prompt, "json")
        if (cacheado := self._ler_cache(chave)) is not None:
            return extrair_json(cacheado)

        # Preferência pelo modo JSON nativo do provedor. A instrução no prompt
        # é mantida em ambos os caminhos porque o modo JSON da OpenAI exige a
        # palavra "JSON" no prompt.
        prompt_json = (
            prompt
            + "\n\nIMPORTANTE: Responda SOMENTE com JSON válido, sem markdown, "
              "sem blocos de código, sem explicações."
        )

        texto = self._com_retry(self._gerar_json_nativo, prompt_json, temperature)
        if texto is None:
            texto = self._com_retry(self._gerar_texto, prompt_json, temperature)

        resultado = extrair_json(texto)
        self._gravar_cache(chave, texto)
        return resultado

    # ── Teste de conexão ──────────────────────────────────────────────────────

    def testar(self) -> tuple[bool, str]:
        try:
            resposta = self._gerar_texto("Responda apenas: OK", 0.0)
            if resposta and resposta.strip():
                return True, f"Conectado ({self.modelo_completo})"
            return False, f"Resposta vazia de {self.modelo_completo}"
        except Exception as exc:
            return False, str(exc)
