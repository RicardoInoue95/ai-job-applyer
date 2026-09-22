"""O score em uma frase — e o que ele esconde.

O cartão mostra só o nível 1: `97% · Excelente`, por quê, e o ponto de atenção.
Estes testes garantem que a conclusão nasce do breakdown, que o rótulo bate com
o número exibido, e que o ponto de atenção é o mais grave, não o primeiro.
"""
from types import SimpleNamespace

import pytest

from jobapplier import aderencia


def _vaga(score, **brk):
    dados = {"breakdown": brk.pop("eixos", {}), **brk}
    return SimpleNamespace(score=score, score_breakdown_json=dados)


def test_titulo_e_numero_e_rotulo():
    a = aderencia.analisar(_vaga(97.0, motivos_positivos=["Python", "SQL"]))
    assert a.titulo == "97% · Excelente"


@pytest.mark.parametrize("score, rotulo", [
    (84.8, "Excelente"),   # exibido como 85% — o rótulo tem de acompanhar
    (84.4, "Boa"),
    (74.6, "Boa"),
    (65.0, "Razoável"),
    (60.0, "Fraca"),
])
def test_rotulo_segue_o_numero_exibido(score, rotulo):
    assert aderencia.analisar(_vaga(score)).rotulo == rotulo


def test_porque_cita_ate_tres_tecnologias():
    a = aderencia.analisar(_vaga(90, motivos_positivos=[
        "Python", "SQL", "Databricks", "Azure", "Power BI"]))
    assert a.porque == "Forte aderência em Python, SQL e Databricks."
    assert a.cobertas == ["Python", "SQL", "Databricks", "Azure", "Power BI"]


def test_equivalente_perde_o_sufixo_na_frase():
    a = aderencia.analisar(_vaga(90, motivos_positivos=["SQL Server (equivalente)"]))
    assert a.porque == "Forte aderência em SQL Server."


def test_nenhuma_reconhecida_nao_e_motivo_positivo():
    """O scorer escreve a ausência dentro de `motivos_positivos`."""
    a = aderencia.analisar(_vaga(60, motivos_positivos=[
        "nenhuma tecnologia da vaga reconhecida"]))
    assert a.cobertas == []
    assert a.porque == "Pouca sobreposição com o seu currículo."


# ── Ponto de atenção: o mais grave, não o primeiro ────────────────────────────

def test_requisito_eliminatorio_vem_antes_de_tudo():
    a = aderencia.analisar(_vaga(
        90, missing_required=["PySpark"],
        gaps=["tecnologias da vaga ausentes no currículo: PySpark, Spark"],
        eixos={"localizacao": 0}))
    assert a.atencao == "Exige PySpark, que não está no seu currículo."


def test_plural_no_eliminatorio():
    a = aderencia.analisar(_vaga(80, missing_required=["SQL Server", "Excel"]))
    assert a.atencao == "Exige SQL Server e Excel, que não estão no seu currículo."


def test_localizacao_zerada_e_apontada():
    a = aderencia.analisar(_vaga(80, eixos={"localizacao": 0}))
    assert "não declarou aceitar" in a.atencao


def test_senioridade_baixa_e_apontada():
    a = aderencia.analisar(_vaga(80, eixos={"senioridade": 5}))
    assert "Senioridade" in a.atencao


def test_tecnologia_ausente_sem_ser_eliminatoria():
    a = aderencia.analisar(_vaga(
        88, gaps=["tecnologias da vaga ausentes no currículo: PySpark, Airflow"]))
    assert a.atencao == "Não cita PySpark, Airflow no currículo."
    assert a.faltam == ["PySpark", "Airflow"]


def test_sem_nada_contra_fica_vazio():
    a = aderencia.analisar(_vaga(
        94, motivos_positivos=["Python"],
        eixos={"skills_tecnicas": 40, "senioridade": 20, "setor": 15,
               "idioma": 15, "localizacao": 10}))
    assert a.atencao == ""


def test_eixos_em_fracao_para_as_barras():
    a = aderencia.analisar(_vaga(90, eixos={
        "skills_tecnicas": 20, "senioridade": 20, "setor": 15, "idioma": 15,
        "localizacao": 4}))
    por_nome = {e.nome: e for e in a.eixos}
    assert por_nome["Tecnologias"].fracao == 0.5
    assert por_nome["Localização"].fracao == 0.4
    assert [e.nome for e in a.eixos] == ["Tecnologias", "Senioridade", "Setor",
                                          "Idioma", "Localização"]


def test_eixo_ausente_nao_e_zero():
    """Breakdown de versão antiga sem `localizacao` não pode virar "presencial
    em cidade não aceita" — desconhecido não é zero."""
    a = aderencia.analisar(_vaga(80, eixos={"skills_tecnicas": 30}))
    assert [e.nome for e in a.eixos] == ["Tecnologias"]
    assert a.atencao == ""


def test_breakdown_como_string_ou_ausente_nao_quebra():
    assert aderencia.analisar(SimpleNamespace(score=70, score_breakdown_json='{"x":')).rotulo
    assert aderencia.analisar(SimpleNamespace(score=None, score_breakdown_json=None)).score == 0


def test_motivo_em_frase_nao_vira_chip_nem_entra_no_porque():
    """Scorer antigo escrevia motivos em frase. Frase não é tecnologia."""
    a = aderencia.analisar(SimpleNamespace(score=67, score_breakdown_json={
        "breakdown": {"skills": 20},
        "motivos_positivos": [
            "Forte alinhamento tecnológico com Databricks, SQL, Python e ferramentas de visualização.",
            "Experiência em orquestração de ETL/ELT com Azure Data Factory.",
        ]}))
    assert a.cobertas == []
    assert a.porque.startswith("Forte alinhamento tecnológico")
    assert "Forte aderência em Forte" not in a.porque


def test_e_frase_distingue_tecnologia_de_frase():
    assert not aderencia._e_frase("Python")
    assert not aderencia._e_frase("Power BI")
    assert not aderencia._e_frase("Azure Data Factory")
    assert aderencia._e_frase("Forte alinhamento tecnológico com Databricks, SQL e Python.")
    assert aderencia._e_frase("Experiência em empresas do setor de tecnologia")
