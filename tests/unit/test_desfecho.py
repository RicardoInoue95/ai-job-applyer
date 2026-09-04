"""O funil morre em 'candidatada'. Este módulo é o que o deixa continuar.

Sem registro de desfecho, o corte de score nunca foi validado contra realidade:
tudo o que se ajustou no projeto — limiar 85, faixa salarial, currículo em
inglês, equivalência — foi medido contra métrica interna, nunca contra "ele foi
chamado?".

O teste que mais importa aqui não é o que reconhece uma entrevista. É o que
garante que **e-mail ambíguo vira None**: funil inflado é pior que funil vazio,
porque o vazio se reconhece e o inflado se acredita.
"""
import pytest

from jobapplier.desfecho import (
    Desfecho,
    classificar,
    e_ruido,
    empresa_do_remetente,
)


@pytest.mark.parametrize("assunto,esperado", [
    ("Convite para entrevista - Data Engineer", Desfecho.ENTREVISTA),
    ("Próxima etapa do processo seletivo", Desfecho.ENTREVISTA),
    ("Let's schedule a call about your application", Desfecho.ENTREVISTA),
    ("Carta proposta - Analista de Dados Pleno", Desfecho.OFERTA),
    ("We are pleased to offer you the position", Desfecho.OFERTA),
    ("Recebemos sua candidatura", Desfecho.RECEBIDA),
    ("Thank you for your interest in Adyen", Desfecho.RECEBIDA),
    ("Infelizmente não seguiremos com sua candidatura", Desfecho.RECUSA),
    ("We have decided to move forward with other candidates", Desfecho.RECUSA),
])
def test_classifica_desfecho_pelo_assunto(assunto, esperado):
    assert classificar(assunto) is esperado


@pytest.mark.parametrize("assunto", [
    "Desafio técnico - próxima fase",
    "Take-home assessment for your application",
])
def test_teste_tecnico_e_resposta_e_nao_entrevista(assunto):
    """Na taxonomia deste módulo RESPOSTA é "alguém leu e pediu algo". Um teste
    técnico é isso; chamá-lo de entrevista inflaria a etapa mais valiosa do
    funil, que é justamente a que se quer medir."""
    assert classificar(assunto) is Desfecho.RESPOSTA


def test_teste_tecnico_no_corpo_e_resposta():
    assert classificar(
        "Sobre sua candidatura",
        "Gostaríamos que você fizesse um teste técnico antes de seguirmos."
    ) is Desfecho.RESPOSTA


# ── A parte que protege o número ──────────────────────────────────────────────

@pytest.mark.parametrize("assunto", [
    "Vagas que combinam com você",
    "Novas vagas de Data Engineer nesta semana",
    "Job alert: 12 new roles",
    "Seu código de verificação é 7K2M9XQP",
    "Redefinir senha",
])
def test_ruido_da_mesma_caixa_nao_vira_desfecho(assunto):
    """Alerta de vaga chega do MESMO remetente que a resposta real. Sem este
    filtro, o funil ganharia uma "resposta" por semana, para sempre."""
    assert e_ruido(assunto)
    assert classificar(assunto) is None


@pytest.mark.parametrize("assunto,corpo", [
    ("Sobre a vaga", "Segue em anexo o material que conversamos."),
    ("Atualização", "Estamos revisando as candidaturas."),
    ("Olá", ""),
    ("", ""),
])
def test_email_ambiguo_vira_none(assunto, corpo):
    """None é resposta legítima e frequente. Chutar "resposta" infla o funil, e
    funil inflado é pior que vazio: o vazio se reconhece."""
    assert classificar(assunto, corpo) is None


def test_o_melhor_desfecho_vence_no_mesmo_email():
    """"Agradecemos o interesse" aparece em e-mail de entrevista também. Se a
    recusa vencesse por aparecer primeiro no texto, marcaríamos como rejeitado
    justamente quem foi chamado."""
    assert classificar(
        "Convite para entrevista",
        "Agradecemos o seu interesse. Gostaríamos de agendar uma conversa."
    ) is Desfecho.ENTREVISTA


def test_oferta_vence_entrevista():
    assert classificar(
        "Carta proposta",
        "Após a entrevista, temos uma proposta de trabalho para você."
    ) is Desfecho.OFERTA


def test_banco_de_talentos_e_recusa():
    """"Vamos manter seu currículo em nosso banco de talentos" é o não mais
    educado que existe. Contá-lo como resposta positiva mentiria no funil."""
    assert classificar(
        "Sobre seu processo",
        "Vamos manter seu perfil em nosso banco de talentos para futuras vagas."
    ) is Desfecho.RECUSA


# ── Casar o e-mail com a empresa ──────────────────────────────────────────────

@pytest.mark.parametrize("remetente,esperado", [
    ("no-reply@adyen.com", "adyen"),
    ("Recruiting <careers@c6bank.com.br>", "c6bank"),
    ("noreply@us.greenhouse-mail.io", "greenhouse-mail"),
    ("talent@stripe.com", "stripe"),
])
def test_extrai_a_empresa_do_remetente(remetente, esperado):
    assert empresa_do_remetente(remetente) == esperado


@pytest.mark.parametrize("remetente", ["", None, "sem-arroba", "@"])
def test_remetente_ilegivel_devolve_vazio(remetente):
    assert empresa_do_remetente(remetente) == ""
