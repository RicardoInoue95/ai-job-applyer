"""Um perfil não pode afirmar o que o currículo mestre não afirma.

Os quatro `resume_base_*.json` eram cópias integrais do mestre, e cópia diverge.
Divergiram: quando `data/resume.json` foi reescrito, os quatro ficaram afirmando
FIAP em andamento (concluída), omitindo o telefone (que o gerador de PDF lê) e
nomeando o cliente em dois casos. Nada apareceu no score, que lê o mestre — só o
PDF lia as cópias, e ninguém confere PDF contra JSON.

Estes testes são a trava. Se um perfil ou um idioma voltar a divergir do mestre
em fato, falham aqui e não no currículo de alguém.
"""
import json

import pytest

from jobapplier import idioma, paths, perfis

#: Toda esta suíte compara perfis derivados com o currículo mestre real em
#: data/resume.json, que só existe na máquina do candidato. Fora dela (CI,
#: clone limpo) ela pula inteira em vez de falhar por dado ausente.
pytestmark = pytest.mark.pessoal

IDIOMAS = ("pt", "en")

#: Cliente nomeado nos base antigos. O mestre diz "ambiente regulado" de
#: propósito: o nome ia para o concorrente dele no currículo seguinte.
CLIENTES_PROIBIDOS = ("BCI-B3", "BCI B3")


@pytest.fixture(scope="module")
def mestres():
    return {i: perfis.carregar_mestre(i) for i in IDIOMAS}


def _montados(idioma_codigo="pt"):
    return {c: perfis.montar(c, idioma_codigo) for c in perfis.PERFIS}


# ── Fato mora num lugar só ────────────────────────────────────────────────────

@pytest.mark.parametrize("lingua", IDIOMAS)
def test_fatos_identicos_entre_perfis(lingua):
    """Empresa, cargo, data e formação não podem variar por perfil.

    Enfatizar Power BI num perfil de BI é legítimo; mudar a data de entrada na
    360BI não é. Só o resumo e a ordem das tecnologias podem diferir.
    """
    montados = _montados(lingua)
    referencia = montados[perfis.PADRAO]
    for chave, base in montados.items():
        for campo in ("experiencias", "formacao", "certificacoes", "idiomas",
                      "nome", "email", "telefone", "linkedin", "localizacao"):
            assert base[campo] == referencia[campo], (
                f"perfil '{chave}' divergiu do mestre em '{campo}'")


def test_fatos_identicos_entre_idiomas(mestres):
    """A versão em inglês traduz texto, não muda fato.

    Empresa, data e instituição são nome próprio e registro formal: divergir aqui
    seria dois currículos contando histórias diferentes para o mesmo candidato.
    """
    pt, en = mestres["pt"], mestres["en"]

    for campo in ("nome", "email", "telefone", "linkedin"):
        assert pt[campo] == en[campo], f"contato divergiu em '{campo}'"

    for campo in ("experiencias", "formacao", "certificacoes", "idiomas",
                  "tecnologias"):
        assert len(pt[campo]) == len(en[campo]), (
            f"'{campo}' tem tamanhos diferentes entre pt e en")

    for a, b in zip(pt["experiencias"], en["experiencias"], strict=True):
        assert a["empresa"] == b["empresa"]
        assert a["data_inicio"] == b["data_inicio"]
        assert a["data_fim"] == b["data_fim"]

    for a, b in zip(pt["formacao"], en["formacao"], strict=True):
        assert a["instituicao"] == b["instituicao"]
        assert a["data_conclusao"] == b["data_conclusao"]
        assert a["em_andamento"] == b["em_andamento"]


# ── Os quatro defeitos que existiram de verdade ───────────────────────────────

@pytest.mark.parametrize("lingua", IDIOMAS)
def test_telefone_presente(lingua):
    """`generators/pdf` lê `telefone`. Ausente nos quatro base antigos, todo
    currículo enviado saiu sem número de contato."""
    for chave, base in _montados(lingua).items():
        assert base.get("telefone"), f"perfil '{chave}' sem telefone"


@pytest.mark.parametrize("lingua", IDIOMAS)
def test_formacao_concluida_nao_vira_em_andamento(lingua):
    """FIAP está concluída. Os quatro base diziam 'em andamento' — currículo
    afirmando o que o candidato não afirma é a invariante 3 quebrada."""
    for chave, base in _montados(lingua).items():
        for f in base["formacao"]:
            if f["data_conclusao"] == "2025":
                assert f["em_andamento"] is False, (
                    f"perfil '{chave}' diz FIAP em andamento")


@pytest.mark.parametrize("lingua", IDIOMAS)
def test_nenhum_perfil_nomeia_cliente(lingua):
    for chave, base in _montados(lingua).items():
        bruto = json.dumps(base, ensure_ascii=False)
        for cliente in CLIENTES_PROIBIDOS:
            assert cliente not in bruto, (
                f"perfil '{chave}' nomeia o cliente '{cliente}'")


@pytest.mark.parametrize("lingua", IDIOMAS)
def test_certificacoes_seguem_a_poda_do_mestre(lingua, mestres):
    """A poda de 12 para 3 foi decisão de conteúdo. Um perfil que traga 9 de
    volta desfaz a decisão sem ninguém perceber."""
    esperado = len(mestres[lingua]["certificacoes"])
    for chave, base in _montados(lingua).items():
        assert len(base["certificacoes"]) == esperado, (
            f"perfil '{chave}' tem {len(base['certificacoes'])} certificações")


# ── Ênfase: o que o perfil pode mudar ─────────────────────────────────────────

def test_resumo_muda_por_perfil():
    """Se todos os resumos fossem iguais, o perfil não serviria para nada."""
    resumos = {b["resumo_profissional"] for b in _montados().values()}
    assert len(resumos) == len(perfis.PERFIS)


@pytest.mark.parametrize("lingua", IDIOMAS)
def test_enfase_sobe_a_primeira_tecnologia(lingua):
    for chave, spec in perfis.PERFIS.items():
        base = perfis.montar(chave, lingua)
        primeira = spec.enfase[0]
        esperada = perfis._EQUIV_EN.get(primeira, primeira) if lingua == "en" else primeira
        assert base["tecnologias"][0].lower() == esperada.lower(), (
            f"perfil '{chave}' não priorizou '{esperada}'")


@pytest.mark.parametrize("lingua", IDIOMAS)
def test_enfase_reordena_sem_remover(lingua, mestres):
    """O ATS lê a lista inteira. Esconder tecnologia real só perde casamento de
    palavra-chave — a ênfase ordena, não filtra."""
    original = set(mestres[lingua]["tecnologias"])
    for chave in perfis.PERFIS:
        assert set(perfis.montar(chave, lingua)["tecnologias"]) == original, (
            f"perfil '{chave}' alterou o conjunto de tecnologias")


@pytest.mark.parametrize("lingua", IDIOMAS)
def test_toda_enfase_existe_no_mestre(lingua, mestres):
    """Ênfase que não casa com nenhuma tecnologia é um no-op silencioso: o perfil
    parece priorizar algo e não prioriza nada. Erro de digitação cai aqui."""
    disponiveis = {t.lower() for t in mestres[lingua]["tecnologias"]}
    for chave, spec in perfis.PERFIS.items():
        for termo in spec.enfase:
            alvo = perfis._EQUIV_EN.get(termo, termo) if lingua == "en" else termo
            assert alvo.lower() in disponiveis, (
                f"perfil '{chave}' enfatiza '{alvo}', ausente do mestre {lingua}")


# ── Idioma ────────────────────────────────────────────────────────────────────

def test_mestre_pt_esta_em_portugues(mestres):
    assert idioma.detectar(mestres["pt"]["resumo_profissional"]) == "pt"


def test_mestre_en_esta_em_ingles(mestres):
    """Sem isto, `resume_en.json` poderia ser uma cópia do português e ninguém
    notaria até o recrutador abrir o PDF."""
    assert idioma.detectar(mestres["en"]["resumo_profissional"]) == "en"


def test_todo_resumo_de_perfil_esta_no_idioma_que_diz():
    for chave, spec in perfis.PERFIS.items():
        for lingua in IDIOMAS:
            assert idioma.detectar(spec.resumo[lingua]) == lingua, (
                f"resumo '{lingua}' do perfil '{chave}' não está em {lingua}")


def test_idioma_indefinido_fica_em_portugues():
    """Vaga bilíngue não vira currículo em inglês. Chutar mandaria inglês para
    recrutador brasileiro sem deixar rastro."""
    base = perfis.montar("data_engineer", "indefinido")
    assert idioma.detectar(base["resumo_profissional"]) == "pt"


def test_montar_em_ingles_troca_experiencias_tambem(mestres):
    """Resumo em inglês com bullets em português seria pior que tudo em
    português: o documento parece descuidado."""
    base = perfis.montar("data_engineer", "en")
    bullets = " ".join(base["experiencias"][0]["descricao"])
    assert idioma.detectar(bullets) == "en"


# ── Resolução de perfil ───────────────────────────────────────────────────────

def test_resolver_aceita_o_enum_inteiro():
    """O modelo às vezes ecoa o formato do prompt em vez de escolher."""
    assert perfis.resolver(
        "data_engineer|analytics_engineer|bi_analyst|cloud_data_engineer"
    ) == "data_engineer"


@pytest.mark.parametrize("entrada", [None, "", "   ", "perfil_inventado", 42, []])
def test_resolver_cai_no_padrao(entrada):
    """Perfil novo inventado pelo modelo não pode derrubar a geração inteira."""
    assert perfis.resolver(entrada) == perfis.PADRAO


def test_resolver_ignora_caixa():
    assert perfis.resolver("  BI_Analyst  ") == "bi_analyst"


# ── Higiene ───────────────────────────────────────────────────────────────────

def test_montar_nao_vaza_chave_interna():
    """`_nota` documenta o arquivo, não o candidato."""
    base = perfis.montar("data_engineer", "en")
    assert not [k for k in base if k.startswith("_")]


def test_montar_nao_altera_o_mestre_recebido():
    """A esteira monta um perfil por vaga a partir do mesmo dict. Mutar aqui
    contaminaria todas as vagas seguintes da rodada."""
    mestre = json.loads(paths.RESUME_JSON.read_text(encoding="utf-8"))
    copia = json.loads(json.dumps(mestre))
    perfis.montar("bi_analyst", "pt", mestre)
    assert mestre == copia


def test_montar_declara_o_perfil():
    for chave in perfis.PERFIS:
        assert perfis.montar(chave)["perfil"] == chave


def test_perfil_base_derivado_traz_o_telefone():
    """Contrato com `dossie`: era exatamente isto que faltava no PDF."""
    from types import SimpleNamespace

    from jobapplier.dossie import perfil_base

    vaga = SimpleNamespace(id=1, titulo="Engenheiro de Dados",
                           descricao="Vaga para atuar com pipelines de dados.",
                           normalizado_json={"perfil_base_sugerido": "bi_analyst"})
    perfil, base = perfil_base(vaga, {})
    assert perfil == "bi_analyst"
    assert base["telefone"]


def test_perfil_base_usa_ingles_para_vaga_em_ingles():
    from types import SimpleNamespace

    from jobapplier.dossie import perfil_base

    descricao = (
        "We are looking for a Data Engineer to join our team and help us build "
        "reliable data pipelines in the cloud. You will be responsible for "
        "integrating sources and modeling layers with the business teams."
    )
    vaga = SimpleNamespace(id=2, titulo="Data Engineer", descricao=descricao,
                           normalizado_json={})
    _, base = perfil_base(vaga, {})
    assert idioma.detectar(base["resumo_profissional"]) == "en"


# ── O perfil sugerido vem de dois lugares ─────────────────────────────────────
# `extracao` grava em `normalizado_json`, o scorer em `score_breakdown_json`. O
# orquestrador lia só o segundo e `dossie` só o primeiro: a mesma vaga escolhia
# perfis diferentes conforme o caminho, e o do orquestrador é o que envia.

def _vaga(**campos):
    from types import SimpleNamespace

    base = {"id": 7, "titulo": "Analista de BI",
            "descricao": "Vaga para atuar com dashboards e indicadores.",
            "normalizado_json": None, "score_breakdown_json": None}
    return SimpleNamespace(**{**base, **campos})


def test_perfil_vem_do_normalizado():
    from jobapplier.dossie import perfil_base

    vaga = _vaga(normalizado_json={"perfil_base_sugerido": "bi_analyst"})
    assert perfil_base(vaga, {})[0] == "bi_analyst"


def test_perfil_vem_do_breakdown_quando_normalizado_nao_tem():
    """Caminho do orquestrador: era o único campo que ele consultava."""
    from jobapplier.dossie import perfil_base

    vaga = _vaga(score_breakdown_json={"perfil_base_sugerido": "cloud_data_engineer"})
    assert perfil_base(vaga, {})[0] == "cloud_data_engineer"


def test_normalizado_tem_precedencia_sobre_o_breakdown():
    from jobapplier.dossie import perfil_base

    vaga = _vaga(normalizado_json={"perfil_base_sugerido": "bi_analyst"},
                 score_breakdown_json={"perfil_base_sugerido": "data_engineer"})
    assert perfil_base(vaga, {})[0] == "bi_analyst"


@pytest.mark.parametrize("valor", [
    '{"perfil_base_sugerido": "bi_analyst"}',   # coluna aceita texto
    {"perfil_base_sugerido": "bi_analyst"},
])
def test_campo_json_como_texto_ou_dict(valor):
    from jobapplier.dossie import perfil_base

    assert perfil_base(_vaga(normalizado_json=valor), {})[0] == "bi_analyst"


@pytest.mark.parametrize("lixo", ["nao sou json", "[1, 2, 3]", "42", "null", ""])
def test_campo_json_invalido_nao_derruba_a_geracao(lixo):
    """Uma vaga com JSON corrompido não pode parar a esteira das outras."""
    from jobapplier.dossie import perfil_base

    perfil, base = perfil_base(_vaga(normalizado_json=lixo), {})
    assert perfil == perfis.PADRAO
    assert base["telefone"]
