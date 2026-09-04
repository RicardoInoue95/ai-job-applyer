"""O currículo sob medida é o produto; o envio automático é um extra sobre ele.

O orquestrador gerava os documentos dentro de `run_applications`, **depois** da
guarda que descarta plataforma sem automação. Uma vaga da Gupy ou da Lever virava
`sem_automacao` e não recebia nada — 322 vagas da Gupy morriam ali com o trabalho
caro (coletar, filtrar, pontuar) já pago, e sem nada que o usuário pudesse usar.

O acoplamento era invisível enquanto o objetivo era "o robô candidata".
"""
from types import SimpleNamespace

import pytest

from jobapplier import dossie, paths


def _vaga(vaga_id=1, normalizado=None):
    return SimpleNamespace(
        id=vaga_id, titulo="Engenheiro de Dados", empresa="Acme",
        plataforma="gupy", descricao="Python, SQL, Snowflake",
        normalizado_json=normalizado,
    )


# ── Escolha do perfil base ────────────────────────────────────────────────────

def test_perfil_sugerido_inexistente_cai_para_data_engineer():
    """Sugestão nova do normalizador não pode quebrar a geração inteira — no
    máximo produzir um currículo menos específico."""
    perfil, base = dossie.perfil_base(
        _vaga(normalizado={"perfil_base_sugerido": "astronauta"}),
        {"nome": "Ricardo"},
    )
    assert perfil == "data_engineer"
    assert base


def test_perfil_com_pipe_usa_a_primeira_opcao():
    """O normalizador às vezes devolve 'data_engineer|analytics_engineer'."""
    perfil, _ = dossie.perfil_base(
        _vaga(normalizado={"perfil_base_sugerido": "data_engineer|analytics"}),
        {"nome": "R"},
    )
    assert perfil == "data_engineer"


def test_normalizado_como_string_json():
    """A coluna às vezes volta serializada; tratar como dict levantaria."""
    perfil, _ = dossie.perfil_base(
        _vaga(normalizado='{"perfil_base_sugerido": "data_engineer"}'), {"nome": "R"},
    )
    assert perfil == "data_engineer"


def test_normalizado_invalido_nao_derruba():
    for ruim in (None, "", "{quebrado", "[]", 42):
        perfil, base = dossie.perfil_base(_vaga(normalizado=ruim), {"nome": "R"})
        assert perfil == "data_engineer"
        assert base


# ── Montagem ──────────────────────────────────────────────────────────────────

@pytest.fixture
def _sem_disco(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "RESUMES", tmp_path / "resumes")
    monkeypatch.setattr(paths, "COVER_LETTERS", tmp_path / "cartas")
    return tmp_path


def _instalar(monkeypatch, *, otimiza=None, pdf=None, carta=None):
    import jobapplier.agents.cover_letter as mod_carta
    import jobapplier.agents.resume_optimizer as mod_opt
    import jobapplier.generators.pdf as mod_pdf

    monkeypatch.setattr(mod_opt, "optimize", otimiza or (lambda *a, **k: {
        "perfil_otimizado": {"nome": "Ricardo"},
        "ats_antes": 60.0, "ats_depois": 82.0,
        "keywords_adicionadas": ["Snowflake", "dbt"],
    }))
    monkeypatch.setattr(mod_pdf, "generate_pdf",
                        pdf or (lambda perfil, destino, **k: destino.write_bytes(b"%PDF")))
    monkeypatch.setattr(mod_carta, "generate", carta or (lambda *a, **k: "Prezados,"))


def test_dossie_completo(monkeypatch, _sem_disco):
    _instalar(monkeypatch)
    d = dossie.montar(_vaga(7), {"nome": "Ricardo"})

    assert d.pronto
    assert d.pdf_path.exists() and d.pdf_path.name.endswith("_7.pdf")
    assert d.cover_letter_path.exists()
    assert d.ganho_ats == 22.0
    assert not d.erro


def test_carta_ausente_nao_invalida_o_dossie(monkeypatch, _sem_disco):
    """A carta é opcional em boa parte dos formulários. Perder a otimização já
    feita por causa de um texto ausente seria desperdício."""
    _instalar(monkeypatch, carta=lambda *a, **k: "")
    d = dossie.montar(_vaga(8), {"nome": "R"})

    assert d.pronto, "o PDF é o que vai para o recrutador"
    assert d.cover_letter_path is None


def test_erro_na_carta_nao_derruba(monkeypatch, _sem_disco):
    def explode(*a, **k):
        raise RuntimeError("LLM fora do ar")

    _instalar(monkeypatch, carta=explode)
    assert dossie.montar(_vaga(9), {"nome": "R"}).pronto


def test_pdf_reprovado_no_layout_deixa_o_dossie_incompleto(monkeypatch, _sem_disco):
    """Invariante 8: falha fechada. Currículo com layout quebrado não pode virar
    um dossiê 'pronto' — foi assim que currículos saíram quebrados antes."""
    def reprova(*a, **k):
        raise ValueError("LayoutInvalidoError: sobreposição de blocos")

    _instalar(monkeypatch, pdf=reprova)
    d = dossie.montar(_vaga(10), {"nome": "R"})

    assert not d.pronto
    assert "LayoutInvalido" in d.erro


def test_falha_devolve_dossie_com_erro_em_vez_de_levantar(monkeypatch, _sem_disco):
    """A esteira processa uma fila; uma vaga problemática não pode derrubar as
    outras 321."""
    def explode(*a, **k):
        raise RuntimeError("otimizador quebrou")

    _instalar(monkeypatch, otimiza=explode)
    d = dossie.montar(_vaga(11), {"nome": "R"})

    assert not d.pronto
    assert "otimizador quebrou" in d.erro


def test_pronto_exige_arquivo_no_disco(_sem_disco):
    """Caminho preenchido não é prova de arquivo gerado."""
    d = dossie.Dossie(vaga_id=1, pdf_path=_sem_disco / "nao_existe.pdf")
    assert not d.pronto


# ── O desacoplamento ──────────────────────────────────────────────────────────

def test_montar_nao_depende_de_haver_automacao():
    """`montar` não consulta o registro de plataformas: vaga da Gupy vale tanto
    quanto vaga do Greenhouse para efeito de documento."""
    import inspect

    fonte = inspect.getsource(dossie)
    assert "suportada" not in fonte
    assert "PLATAFORMAS" not in fonte


def test_o_orquestrador_monta_o_dossie_antes_de_desistir():
    """A guarda de plataforma sem automação tem que gerar os documentos antes de
    marcar o status — era a ordem inversa que matava as vagas da Gupy."""
    import inspect

    from jobapplier import orchestrator

    # `run_applications` é só o invólucro de log; a esteira vive aqui. A âncora
    # é o `if` da guarda (não a primeira menção a `suportada`, que agora aparece
    # antes, no gate de threshold_auto).
    fonte = inspect.getsource(orchestrator._executar_candidaturas)
    guarda = fonte.index("if abaixo_do_auto or not applicators.suportada(plataforma):")
    trecho = fonte[guarda:guarda + 1600]

    assert "dossie.montar" in trecho, "a guarda precisa montar o dossiê"
    assert trecho.index("dossie.montar") < trecho.index('"status": novo_status'), \
        "o dossiê tem que ser montado ANTES de gravar o status final"


def test_status_de_envio_manual_pede_acao_do_usuario():
    """Sem status próprio, a vaga fica indistinguível de 'bloqueada' e o usuário
    nunca descobre que tem um currículo pronto esperando por ele."""
    from jobapplier import status

    s = status.de_vaga("pronta_envio_manual")
    assert s.exige_acao
    assert s.rotulo != "pronta_envio_manual"
    assert "pronta_envio_manual" in status.exigem_sua_acao()
