import hashlib
import json
import logging
import time
from datetime import datetime, timedelta

from google import genai
from google.genai import types as genai_types

from database.connection import get_session
from database.models import CacheGemini
from database.repository import CacheGeminiRepository

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_CACHE_TTL_HOURS = 24


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        cache_ttl_hours: int = DEFAULT_CACHE_TTL_HOURS,
        use_cache: bool = True,
    ):
        self.api_key = api_key
        self.model_name = model
        self.cache_ttl_hours = cache_ttl_hours
        self.use_cache = use_cache
        self._client = genai.Client(api_key=api_key)

    @staticmethod
    def _make_cache_key(model: str, prompt: str) -> str:
        return hashlib.sha256(f"{model}:{prompt}".encode("utf-8")).hexdigest()

    def _call_with_retry(self, prompt: str, temperature: float, max_retries: int = 5) -> str:
        delay = 15
        config = genai_types.GenerateContentConfig(temperature=temperature)
        for attempt in range(1, max_retries + 1):
            try:
                response = self._client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=config,
                )
                return response.text
            except Exception as exc:
                if "429" in str(exc) and attempt < max_retries:
                    logger.warning(
                        "Rate limit atingido. Aguardando %ds antes de tentar novamente (tentativa %d/%d)...",
                        delay, attempt, max_retries,
                    )
                    time.sleep(delay)
                    delay = min(delay * 2, 60)
                else:
                    raise

    def generate(self, prompt: str, temperature: float = 0.2) -> str:
        cache_key = self._make_cache_key(self.model_name, prompt)

        if self.use_cache:
            try:
                with get_session() as session:
                    repo = CacheGeminiRepository(session)
                    cached = repo.get(cache_key)
                    if cached:
                        logger.debug("Cache hit for key %s", cache_key[:8])
                        return cached.resposta
            except Exception as exc:
                logger.warning("Cache read failed: %s", exc)

        text = self._call_with_retry(prompt, temperature)

        if self.use_cache:
            try:
                with get_session() as session:
                    repo = CacheGeminiRepository(session)
                    entry = CacheGemini(
                        chave_hash=cache_key,
                        modelo=self.model_name,
                        resposta=text,
                        criado_em=datetime.utcnow(),
                        expira_em=datetime.utcnow() + timedelta(hours=self.cache_ttl_hours),
                    )
                    repo.set(entry)
            except Exception as exc:
                logger.warning("Cache write failed: %s", exc)

        return text

    def generate_json(self, prompt: str, temperature: float = 0.1) -> dict | list:
        json_prompt = (
            prompt
            + "\n\nIMPORTANTE: Responda SOMENTE com JSON válido, sem markdown, sem código, sem explicações."
        )
        raw = self.generate(json_prompt, temperature=temperature)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return json.loads(cleaned)

    @classmethod
    def test_connection(cls, api_key: str) -> tuple[bool, str]:
        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=DEFAULT_MODEL,
                contents="Responda apenas: OK",
            )
            if response.text:
                return True, f"Conectado com sucesso ({DEFAULT_MODEL})"
            return False, "Resposta vazia da API"
        except Exception as exc:
            return False, str(exc)
