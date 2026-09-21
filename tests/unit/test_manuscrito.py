"""Currículo manuscrito: vale mais que o modelo, mas não pode mudar fato.

O manuscrito é texto que uma pessoa escreveu para uma vaga. Ele dispensa o
modelo nos dois geradores de documento — mas passa pela mesma trava da
invariante 3 que o modelo passa, porque mão humana inventa tecnologia com a
mesma facilidade.
"""
import copy
import json
from types import SimpleNamespace

import pytest

from jobapplier import manuscrito, paths
from jobapplier.agents import cover_letter, resume_optimizer

BASE = {
    "nome": "Fulano", "email": "f@x.com", "telefone": "11 9", "linkedin": "in/f",
    "localizacao": "São Paulo, SP",
    "resumo_profissional": "Engenheiro de dados com pipelines em Snowflake.",
    "experiencias": [
        {"empresa": "Acme", "cargo": "Engenheiro de Dados", "data_inicio": "01/2024",
         "data_fim": None, "descricao": ["Pipelines em Snowflake."],
         "tecnologias": ["Snowflake", "Python"], "conquistas": ["Custo -30%."]},
    ],
    "formacao": [{"instituicao": "FIAP", "curso": "Tec", "data_conclusao": "2025",
                  "em_andamento": False}],
    "certificacoes": [{"nome": "Power BI"}],
    "idiomas": [{"nome": "Inglês", "nivel": "Avançado"}],
    "tecnologias": ["Snowflake", "Python", "SQL", "Power BI"],
    "soft_skills": [],
}


def _vaga(id=42, **campos):
    campos.setdefault("titulo", "Engenheiro de Dados")
    campos.setdefault("empresa", "Empresa")
    campos.setdefault("descricao", "Vaga de dados em português.")
    campos.setdefault("normalizado_json", {"tecnologias": ["SQL", "Snowflake"]})
    return SimpleNamespace(id=id, **campos)


@pytest.fixture
def dossies(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DOSSIES", tmp_path)
    return tmp_path


def _gravar(dossies, vaga_id, curriculo=None, carta=None):
    p = dossies / str(vaga_id)
    p.mkdir()
    if curriculo is not None:
        (p / manuscrito.CURRICULO).write_text(
            json.dumps(curriculo, ensure_ascii=False), encoding="utf-8")
    if carta is not None:
        (p / manuscrito.CARTA).write_text(carta, encoding="utf-8")


# ── Leitura ───────────────────────────────────────────────────────────────────

def test_sem_pasta_nao_ha_manuscrito(dossies):
    assert manuscrito.curriculo(42) is None
    assert manuscrito.carta(42) is None
    assert manuscrito.curriculo(None) is None


def test_carta_vazia_conta_como_ausente(dossies):
    """Gravar "" faria o gerador devolver nada em silêncio — mesma regra das
    respostas aprendidas."""
    _gravar(dossies, 42, carta="   \n")
    assert manuscrito.carta(42) is None


def test_curriculo_que_nao_e_objeto_e_erro(dossies):
    _gravar(dossies, 42, curriculo=["lista"])
    with pytest.raises(manuscrito.FatoDivergente):
        manuscrito.curriculo(42)


# ── Invariante 3 ──────────────────────────────────────────────────────────────

def test_reescrever_resumo_bullets_e_ordem_e_permitido():
    m = copy.deepcopy(BASE)
    m["resumo_profissional"] = "Outro resumo, com o vocabulário da vaga."
    m["experiencias"][0]["descricao"] = ["Bullet novo.", "Outro bullet."]
    m["experiencias"][0]["conquistas"] = ["Conquista reformulada."]
    m["experiencias"][0]["tecnologias"] = ["Python", "Snowflake"]
    m["tecnologias"] = ["SQL", "Snowflake", "Python"]          # reordenou e omitiu
    manuscrito.conferir_fatos(m, BASE)                           # não levanta


@pytest.mark.parametrize("mexer", [
    lambda m: m.__setitem__("telefone", "outro"),
    lambda m: m["experiencias"][0].__setitem__("data_inicio", "01/2020"),
    lambda m: m["experiencias"][0].__setitem__("cargo", "Head de Dados"),
    lambda m: m["experiencias"][0].__setitem__("empresa", "Outra"),
    lambda m: m["formacao"][0].__setitem__("em_andamento", True),
    lambda m: m["certificacoes"].append({"nome": "AWS"}),
    lambda m: m["idiomas"].append({"nome": "Alemão", "nivel": "Fluente"}),
    lambda m: m["experiencias"].append(dict(m["experiencias"][0], empresa="Nova")),
    lambda m: m["experiencias"].pop(),
    lambda m: m["tecnologias"].append("Spark"),
    lambda m: m["experiencias"][0]["tecnologias"].append("Spark"),
], ids=["telefone", "data", "cargo", "empresa", "formacao", "certificacao",
        "idioma", "experiencia_nova", "experiencia_a_menos", "tecnologia_nova",
        "tecnologia_nova_na_experiencia"])
def test_mudar_fato_e_recusado(mexer):
    m = copy.deepcopy(BASE)
    mexer(m)
    with pytest.raises(manuscrito.FatoDivergente):
        manuscrito.conferir_fatos(m, BASE)


# ── Integração com os geradores ───────────────────────────────────────────────

def test_optimize_usa_o_manuscrito_e_dispensa_o_modelo(dossies):
    m = copy.deepcopy(BASE)
    m["resumo_profissional"] = "Resumo sob medida."
    m["tecnologias"] = ["SQL", "Snowflake", "Python", "Power BI"]
    _gravar(dossies, 42, curriculo=m)

    class ClienteQueNaoDeveSerChamado:
        def generate_json(self, *a, **k):
            raise AssertionError("o modelo não pode ser chamado com manuscrito")

    r = resume_optimizer.optimize(copy.deepcopy(BASE), _vaga(),
                                  ClienteQueNaoDeveSerChamado())
    assert r["perfil_otimizado"]["resumo_profissional"] == "Resumo sob medida."
    # As métricas de ATS continuam sendo calculadas sobre o resultado.
    assert r["ats_depois"] == 100.0


def test_optimize_recusa_manuscrito_que_muda_fato(dossies):
    m = copy.deepcopy(BASE)
    m["tecnologias"].append("Spark")
    _gravar(dossies, 42, curriculo=m)
    with pytest.raises(manuscrito.FatoDivergente):
        resume_optimizer.optimize(copy.deepcopy(BASE), _vaga(), None)


def test_optimize_sem_manuscrito_segue_o_caminho_normal(dossies):
    r = resume_optimizer.optimize(copy.deepcopy(BASE), _vaga(), None)
    assert r["perfil_otimizado"]["resumo_profissional"] == BASE["resumo_profissional"]


def test_manuscrito_e_por_vaga(dossies):
    m = copy.deepcopy(BASE)
    m["resumo_profissional"] = "Só para a 42."
    _gravar(dossies, 42, curriculo=m)
    r = resume_optimizer.optimize(copy.deepcopy(BASE), _vaga(id=43), None)
    assert r["perfil_otimizado"]["resumo_profissional"] == BASE["resumo_profissional"]


def test_carta_manuscrita_vence_o_gabarito(dossies):
    _gravar(dossies, 42, carta="Prezados, escrevo por esta vaga.")
    assert cover_letter.generate(BASE, _vaga(), None) == "Prezados, escrevo por esta vaga."


def test_sem_carta_manuscrita_o_gabarito_segue(dossies):
    texto = cover_letter.generate(BASE, _vaga(), None)
    assert texto and "Prezados, escrevo" not in texto
