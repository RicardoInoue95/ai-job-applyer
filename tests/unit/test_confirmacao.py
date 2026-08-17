"""Confirmação de envio: sucesso exige prova, não indício.

O bug que motivou isto: o Greenhouse marcava `enviada` se a palavra "obrigado"
aparecesse em qualquer lugar da página. Um rodapé de agradecimento produzia falso
positivo — e falso `enviada` é pior que erro, porque `guard.ja_candidatado()`
passa a bloquear aquela vaga para sempre, sem nunca ter havido candidatura.
"""
import pytest

from jobapplier.applicators.base import (
    ENVIADA_CONFIRMADA,
    FALHA_AUTOMACAO,
    REVISAO_MANUAL,
    SIMULADA,
    STATUS_BLOQUEIA_RETENTATIVA,
    STATUS_LEGADOS,
    STATUS_VALIDOS,
    avaliar_confirmacao,
    obter,
    resultado,
    suportada,
)

# ── avaliar_confirmacao ───────────────────────────────────────────────────────

def test_sinal_forte_confirma():
    status, motivo = avaliar_confirmacao({"url de confirmação": True})
    assert status == ENVIADA_CONFIRMADA
    assert "url de confirmação" in motivo


def test_um_sinal_forte_basta():
    status, _ = avaliar_confirmacao(
        {"url de confirmação": False, "elemento de confirmação": True}
    )
    assert status == ENVIADA_CONFIRMADA


def test_sinal_fraco_sozinho_nunca_confirma():
    """O caso do bug: 'obrigado' na página não é prova de envio."""
    status, motivo = avaliar_confirmacao(
        {"url de confirmação": False},
        sinais_fracos={"texto de agradecimento": True},
    )
    assert status == REVISAO_MANUAL
    assert "sem confirmação" in motivo


def test_nenhum_sinal_e_falha():
    status, motivo = avaliar_confirmacao({}, sinais_fracos={})
    assert status == FALHA_AUTOMACAO
    assert "nenhum sinal" in motivo


def test_todos_fracos_falsos_e_falha():
    status, _ = avaliar_confirmacao(
        {"a": False}, sinais_fracos={"b": False, "c": False}
    )
    assert status == FALHA_AUTOMACAO


def test_pergunta_pendente_vence_sinal_forte():
    """Formulário aceito com pergunta em branco ainda pede conferência."""
    status, motivo = avaliar_confirmacao(
        {"url de confirmação": True},
        perguntas_manuais=["Pretensão salarial?"],
    )
    assert status == REVISAO_MANUAL
    assert "sem resposta automática" in motivo


def test_pergunta_pendente_com_fraco_tambem_e_revisao():
    status, _ = avaliar_confirmacao(
        {}, perguntas_manuais=["Qual seu CPF?"],
        sinais_fracos={"texto de agradecimento": True},
    )
    assert status == REVISAO_MANUAL


def test_muitas_perguntas_truncadas_na_mensagem():
    status, motivo = avaliar_confirmacao(
        {}, perguntas_manuais=[f"p{i}" for i in range(10)]
    )
    assert status == REVISAO_MANUAL
    assert "10 pergunta" in motivo


def test_none_em_vez_de_dict_nao_estoura():
    assert avaliar_confirmacao(None)[0] == FALHA_AUTOMACAO
    assert avaliar_confirmacao({}, None, None)[0] == FALHA_AUTOMACAO


# ── Invariantes do vocabulário ────────────────────────────────────────────────

def test_confirmado_e_revisao_bloqueiam_retentativa():
    """Ambos podem ter chegado à plataforma — reenviar duplicaria."""
    assert ENVIADA_CONFIRMADA in STATUS_BLOQUEIA_RETENTATIVA
    assert REVISAO_MANUAL in STATUS_BLOQUEIA_RETENTATIVA


def test_falha_e_simulada_permitem_retentativa():
    """Nada foi submetido; corrigir a causa e tentar de novo é correto."""
    assert FALHA_AUTOMACAO not in STATUS_BLOQUEIA_RETENTATIVA
    assert SIMULADA not in STATUS_BLOQUEIA_RETENTATIVA


def test_simulada_nao_consome_cota_da_plataforma():
    from jobapplier.safety import guard

    assert SIMULADA not in guard.STATUS_CONTATO_REAL
    assert FALHA_AUTOMACAO not in guard.STATUS_CONTATO_REAL
    assert ENVIADA_CONFIRMADA in guard.STATUS_CONTATO_REAL


def test_guard_reconhece_status_legados():
    """Histórico já gravado no banco não pode virar invisível."""
    from jobapplier.safety import guard

    assert "enviada" in guard.STATUS_CONTATO_REAL
    assert "perguntas_pendentes" in guard.STATUS_CONTATO_REAL


def test_mapa_de_legados_cobre_os_tres_antigos():
    assert set(STATUS_LEGADOS) == {"enviada", "perguntas_pendentes", "erro"}
    assert all(v in STATUS_VALIDOS for v in STATUS_LEGADOS.values())


def test_todo_status_do_mapa_de_vaga_e_valido():
    from jobapplier.orchestrator import MAPA_STATUS_VAGA

    assert set(MAPA_STATUS_VAGA) == set(STATUS_VALIDOS)


def test_modo_sombra_mapeia_para_pronta_para_revisao():
    from jobapplier.orchestrator import MAPA_STATUS_VAGA

    assert MAPA_STATUS_VAGA[SIMULADA] == "pronta_para_revisao"
    # Nunca 'candidatada': em sombra nada foi enviado.
    assert MAPA_STATUS_VAGA[SIMULADA] != "candidatada"


# ── resultado() ───────────────────────────────────────────────────────────────

def test_resultado_tem_todas_as_chaves():
    r = resultado(ENVIADA_CONFIRMADA, "ok")
    assert set(r) == {"status", "application_id", "mensagem",
                      "perguntas_manuais", "evidencias"}


def test_resultado_rejeita_status_invalido():
    with pytest.raises(ValueError, match="status inválido"):
        resultado("enviada", "usando nome legado")


def test_resultado_converte_evidencias_para_str(tmp_path):
    r = resultado(FALHA_AUTOMACAO, "falhou", evidencias=[tmp_path / "a.png"])
    assert r["evidencias"] == [str(tmp_path / "a.png")]


def test_resultado_nunca_compartilha_lista_mutavel():
    a = resultado(FALHA_AUTOMACAO, "x")
    a["perguntas_manuais"].append("contaminado")
    assert resultado(FALHA_AUTOMACAO, "y")["perguntas_manuais"] == []


# ── Registry ──────────────────────────────────────────────────────────────────

def test_plataformas_com_automacao():
    for p in ("greenhouse", "linkedin", "gupy"):
        assert suportada(p)


def test_lever_nao_e_suportada():
    """Módulo 14 não existe. Antes caía no applicator do Greenhouse e falhava."""
    assert not suportada("lever")


def test_suportada_e_case_insensitive():
    assert suportada("GreenHouse")


def test_suportada_tolera_none_e_vazio():
    assert not suportada(None)
    assert not suportada("")


def test_obter_plataforma_desconhecida_da_erro_util():
    with pytest.raises(KeyError, match="greenhouse"):
        obter("workday")
