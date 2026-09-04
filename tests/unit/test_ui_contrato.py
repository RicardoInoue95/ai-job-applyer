"""As páginas do Streamlit leem colunas do banco por nome, e nada verifica isso.

A tela de aplicar quebrou em produção com `AttributeError: breakdown_json` — a
coluna se chama `score_breakdown_json`. O nome errado só aparece quando o usuário
abre a página, porque `py_compile` não resolve atributo e nenhum teste importa
as páginas (elas exigem o runtime do Streamlit).

Este teste lê o código-fonte das páginas e confere cada `v.<atributo>` contra as
colunas reais do modelo. Não substitui rodar a tela, mas pega a classe de erro
que mais quebrou aqui: campo renomeado, campo inventado, campo que nunca existiu.
"""
import re
from pathlib import Path

import pytest

from jobapplier.database.models import Candidatura, Vaga

UI = Path(__file__).resolve().parents[2] / "ui"

#: Propriedades e relacionamentos que não são colunas mas são acesso legítimo.
EXTRAS = {"metadata", "registry", "query"}


def _colunas(modelo) -> set[str]:
    nomes = {c.name for c in modelo.__table__.columns}
    nomes |= {a for a in dir(modelo) if not a.startswith("_")}
    return nomes | EXTRAS


def _acessos(fonte: str, variavel: str) -> set[str]:
    """Atributos acessados como `<variavel>.<algo>` no código."""
    return set(re.findall(rf"\b{variavel}\.([a-z_][a-z0-9_]*)", fonte))


@pytest.mark.parametrize("pagina", sorted(UI.rglob("*.py")), ids=lambda p: p.name)
def test_atributos_de_vaga_existem_no_modelo(pagina):
    """`v.breakdown_json` passou no lint, no compile e na suíte — e quebrou na
    cara do usuário."""
    fonte = pagina.read_text(encoding="utf-8")
    validas = _colunas(Vaga)

    invalidos = set()
    for variavel in ("v", "vaga"):
        invalidos |= {a for a in _acessos(fonte, variavel) if a not in validas}

    assert not invalidos, (
        f"{pagina.name} acessa atributo inexistente em Vaga: {sorted(invalidos)}. "
        f"Colunas reais: {sorted(c.name for c in Vaga.__table__.columns)}"
    )


@pytest.mark.parametrize("pagina", sorted(UI.rglob("*.py")), ids=lambda p: p.name)
def test_atributos_de_candidatura_existem_no_modelo(pagina):
    fonte = pagina.read_text(encoding="utf-8")
    validas = _colunas(Candidatura)

    invalidos = {a for a in _acessos(fonte, "cand") if a not in validas}
    assert not invalidos, (
        f"{pagina.name} acessa atributo inexistente em Candidatura: {sorted(invalidos)}"
    )


def test_status_usados_pelas_paginas_estao_catalogados():
    """Página filtrando por status que o backend não produz mostra lista vazia
    sem erro — pior que quebrar, porque parece funcionar."""
    from jobapplier import status

    catalogados = {s.codigo for s in status.VAGA} | {s.codigo for s in status.CANDIDATURA}
    fonte = (UI / "pages" / "5_Aplicar.py").read_text(encoding="utf-8")

    usados = set(re.findall(r'"(pronta_envio_manual|aprovada|pronta_para_revisao'
                            r'|enviada_manual|descartada_por_voce)"', fonte))
    assert usados, "o teste precisa encontrar os status da fila"
    assert usados <= catalogados, f"status não catalogados: {usados - catalogados}"
