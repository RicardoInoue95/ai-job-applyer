"""O vocabulário de status da UI não pode ficar atrás do backend em silêncio.

A interface conhecia 8 status de vaga enquanto o orquestrador produzia 17 — e o
ausente mais importante era `pronta_para_revisao`, onde toda vaga do modo sombra
cai. O ponto do modo sombra é revisão humana, e a tela de revisão não conseguia
mostrá-las.
"""
import pytest

from jobapplier import status


def test_todo_status_de_vaga_do_backend_esta_catalogado():
    """Guarda contra a defasagem voltar: status novo no orquestrador sem
    entrada aqui quebra este teste, não a interface do usuário."""
    from jobapplier.applicators.descoberta import STATUS_TERMINAIS
    from jobapplier.orchestrator import MAPA_STATUS_VAGA

    produzidos = set(MAPA_STATUS_VAGA.values()) | set(STATUS_TERMINAIS) | {
        "nova", "filtrada_4a", "filtrada_4b", "aprovada", "pendente",
        "rejeitada", "em_andamento", "sem_automacao", "erro",
    }
    catalogados = {s.codigo for s in status.VAGA}
    faltando = produzidos - catalogados
    assert not faltando, f"status produzidos pelo backend e não catalogados: {faltando}"


def test_todo_status_de_candidatura_esta_catalogado():
    from jobapplier.applicators.base import STATUS_LEGADOS, STATUS_VALIDOS

    produzidos = set(STATUS_VALIDOS) | set(STATUS_LEGADOS)
    catalogados = {s.codigo for s in status.CANDIDATURA}
    assert not produzidos - catalogados


def test_modo_sombra_tem_status_visivel_e_exige_acao():
    """Sem isto, o usuário não vê o que o modo sombra preparou."""
    s = status.de_vaga("pronta_para_revisao")
    assert s.rotulo != "pronta_para_revisao", "precisa de rótulo legível"
    assert s.exige_acao
    assert "pronta_para_revisao" in status.exigem_sua_acao()


def test_status_desconhecido_nao_quebra_a_interface():
    """Backend pode ganhar estado novo antes da UI; a tela não pode estourar."""
    s = status.de_vaga("estado_que_ainda_nao_existe")
    assert s.codigo == "estado_que_ainda_nao_existe"
    assert s.rotulo
    assert status.de_candidatura("outro").rotulo


def test_status_vazio_ou_none():
    assert status.de_vaga("").rotulo
    assert status.de_vaga(None).rotulo


def test_grupos_separam_quem_espera_por_quem():
    """'acao' = espera por você. 'processando'/'bloqueada' = espera pelo sistema."""
    acao = set(status.exigem_sua_acao())
    assert {"pronta_para_revisao", "aguardando_configuracao"} <= acao
    # Possibilidade não é pendência: score baixo não entra na contagem de
    # "esperando por você" — inflaria o painel com 195 itens que o usuário
    # escolheu não ver por padrão.
    assert "pendente" not in acao
    # Estes esperam pelo sistema ou por código, não pelo usuário.
    assert "nova" not in acao
    assert "aprovada" not in acao
    assert "sem_automacao" not in acao


def test_codigos_unicos_por_tipo():
    codigos = [s.codigo for s in status.VAGA]
    assert len(codigos) == len(set(codigos))


@pytest.mark.parametrize("s", status.VAGA + status.CANDIDATURA, ids=lambda s: s.codigo)
def test_todo_status_tem_rotulo_descricao_e_tom_valido(s):
    assert s.rotulo and s.rotulo != s.codigo, f"{s.codigo} sem rótulo legível"
    assert s.descricao
    assert s.tom in status.TOM_ICONE


# ── A interface não pode ter import quebrado ──────────────────────────────────

def test_paginas_da_ui_nao_referenciam_modulos_antigos():
    """Quatro botões ficaram quebrados após a reestruturação — os que disparam
    coleta, pipeline e candidatura. Passou porque nenhum teste importa as
    páginas do Streamlit."""
    import re
    from pathlib import Path

    ui = Path(__file__).resolve().parents[2] / "ui"
    # Ancorado no início da linha: sem isso "from config." casa dentro de
    # "from jobapplier.config.manager", e o teste acusa o import correto.
    antigos = re.compile(
        r"^\s*(?:from|import)\s+"
        r"(orchestrator|agents|config|database|applicators|collectors|filters"
        r"|safety|generators|notifications|resume_parser)\b",
        re.MULTILINE,
    )
    quebrados = [
        f"{arquivo.name}: {m.group(0).strip()}"
        for arquivo in ui.rglob("*.py")
        for m in antigos.finditer(arquivo.read_text(encoding="utf-8"))
    ]
    assert not quebrados, f"imports pré-reestruturação na UI: {quebrados}"


def test_paginas_da_ui_compilam():
    """Não renderiza (exige runtime do Streamlit), mas pega erro de sintaxe."""
    import py_compile
    from pathlib import Path

    ui = Path(__file__).resolve().parents[2] / "ui"
    for arquivo in ui.rglob("*.py"):
        py_compile.compile(str(arquivo), doraise=True)


# ── Legado e atual não se somam ───────────────────────────────────────────────
# `enviada` do acervo antigo significava "o botão foi clicado";
# `enviada_confirmada` exige prova na página. Foi essa frouxidão que produziu a
# taxa real de 3,4% da auditoria. Somar os dois dá um número que não descreve
# nem um período nem o outro — e reclassificar inventaria certeza sobre envios
# que ninguém verificou.

@pytest.mark.parametrize("codigo", ["enviada", "perguntas_pendentes", "erro"])
def test_reconhece_status_legado(codigo):
    assert status.e_legado(codigo)


@pytest.mark.parametrize("codigo", [
    "enviada_confirmada", "revisao_manual", "falha_automacao",
    "aguardando_verificacao", "simulada",
])
def test_status_atual_nao_e_legado(codigo):
    assert not status.e_legado(codigo)


def test_a_fonte_do_legado_e_unica():
    """A lista mora em `applicators.base.STATUS_LEGADOS`, que já existia para
    leitura de linha antiga. Repeti-la em `status.py` criaria a segunda cópia."""
    import inspect

    from jobapplier.applicators.base import STATUS_LEGADOS

    assert "STATUS_LEGADOS" in inspect.getsource(status.e_legado)
    for codigo in STATUS_LEGADOS:
        assert status.e_legado(codigo)


def test_todo_legado_esta_catalogado_com_rotulo():
    """Sem o rótulo "(legado)" no relatório, os dois vocabulários parecem um só."""
    from jobapplier.applicators.base import STATUS_LEGADOS

    for codigo in STATUS_LEGADOS:
        assert "legado" in status.de_candidatura(codigo).rotulo.lower()


def test_panorama_separa_as_duas_epocas():
    import inspect
    import sys as _sys
    from pathlib import Path

    _sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import panorama

    fonte = inspect.getsource(panorama._candidaturas_por_epoca)
    assert "e_legado" in fonte
    assert "não some as duas" in fonte
