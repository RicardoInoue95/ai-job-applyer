"""Currículo e carta escritos à mão para uma vaga específica.

Existe porque há um jeito de gerar o dossiê que não é nem o modelo nem a
reordenação determinística: alguém — o candidato, ou uma sessão de assistente
revisada por ele — lê o anúncio e escreve o resumo e os bullets sob medida. É a
mesma lógica do banco de respostas aprendidas: texto que veio de uma pessoa é a
única fonte que dispensa o modelo.

O que **não** dispensa é a invariante 3. Um texto escrito à mão pode afirmar o
que o mestre não sustenta com a mesma facilidade que um modelo, então
`conferir_fatos` compara campo a campo contra o currículo base antes de o
manuscrito valer: empresa, cargo, data, formação, certificação, contato e o
conjunto de tecnologias têm de ser os do mestre. Só resumo, bullets e ordem
podem diferir — exatamente o que o prompt do otimizador permite ao modelo.

Layout em disco, por vaga::

    data/dossies/<vaga_id>/curriculo.json    mesmo schema do mestre
    data/dossies/<vaga_id>/carta.txt         texto puro, no idioma do currículo

Sem o diretório, nada muda: `optimize` e `cover_letter.generate` seguem o
caminho de sempre. Com ele, o manuscrito vale nos dois lugares que geram
documento — o baralho (`dossie.montar`) e o envio (`run_applications`) —, e é
por isso que a leitura mora aqui e não em quem chama.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from jobapplier import paths

logger = logging.getLogger(__name__)

CURRICULO = "curriculo.json"
CARTA = "carta.txt"

#: Campos de raiz que o manuscrito tem de copiar do base, byte a byte.
_FATOS_RAIZ = ("nome", "email", "telefone", "linkedin", "localizacao",
               "formacao", "certificacoes", "idiomas")
#: Idem, dentro de cada experiência. `descricao` e `conquistas` ficam de fora
#: de propósito: são o que se reescreve.
_FATOS_EXPERIENCIA = ("empresa", "cargo", "inicio", "fim", "data_inicio",
                      "data_fim", "local", "modalidade")


class FatoDivergente(ValueError):
    """O manuscrito afirma algo que o currículo base não afirma."""


def pasta(vaga_id: int | None) -> Path | None:
    if vaga_id is None:
        return None
    return paths.DOSSIES / str(int(vaga_id))


def curriculo(vaga_id: int | None) -> dict | None:
    """Currículo manuscrito da vaga, ou ``None`` se não houver."""
    p = pasta(vaga_id)
    if p is None or not (p / CURRICULO).exists():
        return None
    dados = json.loads((p / CURRICULO).read_text(encoding="utf-8"))
    if not isinstance(dados, dict):
        raise FatoDivergente(
            f"{p / CURRICULO}: esperava um objeto JSON, veio {type(dados).__name__}")
    return dados


def carta(vaga_id: int | None) -> str | None:
    """Carta manuscrita da vaga, ou ``None``. Vazia conta como ausente."""
    p = pasta(vaga_id)
    if p is None or not (p / CARTA).exists():
        return None
    texto = (p / CARTA).read_text(encoding="utf-8").strip()
    return texto or None


def conferir_fatos(manuscrito: dict, base: dict) -> None:
    """Levanta `FatoDivergente` se o manuscrito mudar qualquer fato do base.

    Tecnologias: o manuscrito pode reordenar e até omitir, nunca acrescentar —
    tecnologia nova no currículo é a alucinação mais fácil de cometer e a mais
    fácil de pegar numa entrevista.
    """
    for campo in _FATOS_RAIZ:
        if manuscrito.get(campo) != base.get(campo):
            raise FatoDivergente(f"'{campo}' diverge do currículo base")

    exps_m = manuscrito.get("experiencias") or []
    exps_b = base.get("experiencias") or []
    if len(exps_m) != len(exps_b):
        raise FatoDivergente(
            f"{len(exps_m)} experiência(s) no manuscrito, {len(exps_b)} no base")
    for i, (m, b) in enumerate(zip(exps_m, exps_b, strict=True)):
        for campo in _FATOS_EXPERIENCIA:
            if m.get(campo) != b.get(campo):
                raise FatoDivergente(
                    f"experiência {i} ('{b.get('empresa')}'): '{campo}' diverge")
        # Tecnologia por experiência também não nasce no manuscrito.
        extras = set(m.get("tecnologias") or []) - set(b.get("tecnologias") or [])
        if extras:
            raise FatoDivergente(
                f"experiência {i} ('{b.get('empresa')}'): tecnologias que o "
                f"base não tem: {sorted(extras)}")

    extras = set(manuscrito.get("tecnologias") or []) - set(base.get("tecnologias") or [])
    if extras:
        raise FatoDivergente(
            f"tecnologias que o currículo base não tem: {sorted(extras)}")
