"""Tempo, em um só lugar.

``datetime.utcnow()`` está deprecado desde o Python 3.12 e aparecia em ~14
pontos do projeto, mais duas cópias de um helper ``agora_utc`` privado.

As colunas de data do banco são **naive-UTC** (foram criadas com
``default=datetime.utcnow``). Trocar para tz-aware exigiria migração de schema e
de dados, então a escolha aqui é deliberada: continuar naive-UTC, mas por uma
única função que documenta isso — em vez de espalhar chamadas deprecadas.

Ao comparar com data vinda de API externa, atenção: ``data_publicacao`` do
Greenhouse chega tz-aware, e comparar aware com naive levanta TypeError. Use
``para_naive()``.
"""
from datetime import UTC, date, datetime

__all__ = ["agora_utc", "de_timestamp", "hoje", "para_naive"]


def agora_utc() -> datetime:
    """Agora em UTC, sem tzinfo — compatível com as colunas do banco."""
    return datetime.now(UTC).replace(tzinfo=None)


def hoje() -> date:
    """Data de hoje em UTC.

    UTC e não horário local: o pipeline roda sem interação e a diferença de fuso
    no Brasil (UTC-3) desloca a virada do dia, nunca a duração de um intervalo —
    que é para o que esta data é usada (cálculo de tempo de experiência).
    """
    return datetime.now(UTC).date()


def de_timestamp(segundos: float) -> datetime:
    """Epoch em segundos → datetime naive-UTC."""
    return datetime.fromtimestamp(segundos, tz=UTC).replace(tzinfo=None)


def para_naive(valor: datetime | None) -> datetime | None:
    """Converte datetime tz-aware para naive-UTC. Passa None e naive adiante."""
    if valor is None or valor.tzinfo is None:
        return valor
    return valor.astimezone(UTC).replace(tzinfo=None)
