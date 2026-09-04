"""O contrato de plataforma precisa estar num lugar só.

Antes estava em três, e eles divergiram: `applicators.PLATAFORMAS` afirmava que
a Gupy tinha automação enquanto o applicator dela rejeitava 100% dos links; o
coletor do LinkedIn morava em `applicators/linkedin.py`, onde ninguém procura
por coletor; e "baralho ou envio automático" era decidido pela ausência de uma
entrada num dicionário — informação que não se lê, só se descobre quebrando.
"""
import pytest

from jobapplier import plataformas
from jobapplier.plataformas import Envio


def test_toda_plataforma_declara_como_envia():
    for codigo, p in plataformas.REGISTRO.items():
        assert p.codigo == codigo, "a chave tem que bater com o código"
        assert p.rotulo
        assert isinstance(p.envio, Envio)


def test_quem_nao_automatiza_diz_por_que():
    """Decisão sem motivo escrito vira folclore, e alguém a desfaz sem saber o
    custo. Foi assim que a flag anti-detecção do LinkedIn passou despercebida."""
    for p in plataformas.REGISTRO.values():
        if p.automatiza:
            continue
        assert len(p.motivo) > 60, (
            f"'{p.codigo}' não automatiza e não explica: {p.motivo!r}"
        )


def test_automatico_aponta_para_um_applicator():
    for p in plataformas.REGISTRO.values():
        if p.automatiza:
            assert p.applicator, f"'{p.codigo}' é automático e não diz qual módulo"


def test_pendente_e_diferente_de_manual():
    """MANUAL é decisão que não deve ser revertida (CAPTCHA, risco de conta).
    PENDENTE é trabalho a fazer. Confundir os dois faz alguém "consertar" a
    Gupy contornando o Turnstile.

    A inhire saiu de PENDENTE para MANUAL quando o ensaio aconteceu: a página
    traz reCAPTCHA e monta o formulário por JavaScript. Isso é o ciclo
    funcionando — PENDENTE significa "ainda não medi", e medir resolve para um
    lado ou para o outro.
    """
    assert plataformas.obter("gupy").envio is Envio.MANUAL
    assert plataformas.obter("linkedin").envio is Envio.MANUAL
    assert plataformas.obter("inhire").envio is Envio.MANUAL
    # Lever também virou MANUAL quando o formulário foi medido: o registro dizia
    # "sem CAPTCHA" e o que existe lá é hCaptcha renderizado.
    assert plataformas.obter("lever").envio is Envio.MANUAL


def test_manual_explica_a_barreira_medida():
    """MANUAL sem motivo verificável vira dogma: alguém "conserta" depois. Cada
    uma tem de dizer o que foi observado."""
    esperado = {"gupy": "turnstile", "linkedin": "user agreement",
                "inhire": "recaptcha", "lever": "hcaptcha"}
    for codigo, marca in esperado.items():
        motivo = plataformas.obter(codigo).motivo.lower()
        assert marca in motivo, f"'{codigo}' não explica a barreira ({marca})"


def test_greenhouse_e_a_unica_com_envio_automatico_hoje():
    assert plataformas.com_automacao() == ["greenhouse"]


def test_todo_coletor_declarado_existe_de_fato():
    """Nome de módulo errado no registro só apareceria em produção, no meio de
    uma coleta."""
    import importlib

    for p in plataformas.REGISTRO.values():
        if not p.coleta:
            continue
        modulo = importlib.import_module(f"jobapplier.collectors.{p.coletor}")
        classes = [
            a for a in dir(modulo)
            if a.endswith("Collector") and a != "BaseCollector"
        ]
        assert classes, f"'{p.coletor}' não expõe nenhum Collector"


def test_todo_applicator_declarado_existe_de_fato():
    import importlib

    for p in plataformas.REGISTRO.values():
        if not p.applicator:
            continue
        modulo = importlib.import_module(f"jobapplier.applicators.{p.applicator}")
        assert hasattr(modulo, "apply"), f"'{p.applicator}' não expõe apply()"


def test_plataforma_desconhecida_nao_levanta():
    assert plataformas.obter("naoexiste") is None
    assert plataformas.obter("") is None
    assert "não está no registro" in plataformas.motivo_sem_automacao("naoexiste")


def test_codigo_e_case_insensitive():
    assert plataformas.obter("GREENHOUSE").codigo == "greenhouse"


def test_motivo_vazio_para_quem_automatiza():
    assert plataformas.motivo_sem_automacao("greenhouse") == ""
    assert "Turnstile" in plataformas.motivo_sem_automacao("gupy")


@pytest.mark.parametrize("codigo", ["greenhouse", "gupy", "linkedin", "lever",
                                    "inhire"])
def test_plataformas_conhecidas_estao_no_registro(codigo):
    assert plataformas.obter(codigo) is not None


def test_registro_concorda_com_o_status_de_vaga():
    """Se uma plataforma não automatiza, o pipeline precisa ter para onde mandar
    a vaga dela — senão ela morre sem dossiê, como aconteceu com as 322 da Gupy."""
    from jobapplier import status

    assert status.de_vaga("pronta_envio_manual").exige_acao
