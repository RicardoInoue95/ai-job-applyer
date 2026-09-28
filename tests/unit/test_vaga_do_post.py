"""Ler um post de recrutador: o que dá para afirmar, e o que fica em branco.

O caso de referência é um post real de LinkedIn (setembro/2026), com a
estrutura que a maioria deles tem: emoji, rótulo com dois-pontos, requisitos em
tópicos e uma linha de "enviem o currículo para X com o assunto Y".

Nada aqui toca banco nem rede: a extração é texto puro, e é justamente onde o
palpite entra se ninguém vigiar — "R$ 12.000,00" virando telefone, "Vaga para
quem quer…" virando cargo, o link do curso da autora virando canal de resposta.
"""
from types import SimpleNamespace

import pytest

from jobapplier import abordagem
from jobapplier import vaga_do_post as mod

POST = """🚀 Vaga Cientista de Dados Júnior

💎 Remuneração: R$ 12.000,00
📍 Modelo: 100% Home Office
📄 Contratação: CLT
✅ Condições: Início imediato - Prazo indeterminado
💻 THS Tecnologia - Cliente Sebrae Nacional (Sebrae-NA)

🔎 O que buscam:
- Mínimo de 2 ano de experiência na área de Dados
- Programação em R e Python e principais pacotes estatísticos
- SQL
- Análise exploratória e mineração de dados
- Inglês técnico

⭐ Diferenciais: SQL Server e PostgreSQL, shell Linux, Power BI e Qlik Sense.
Vaga para quem quer trabalhar em iniciativas estratégicas de dados do Sistema Sebrae.

👉 Interessados, enviem o currículo para contatorh@ths.inf.br com o assunto "Cientista de Dados Júnior – Sebrae-NA"

➡️ Se as stacks bateram mas o inglês ainda é uma trava, faça aulas: https://lnkd.in/deE3TwEs
"""


@pytest.fixture
def post():
    return mod.extrair(POST, autor="Júlia Argueiro")


# ── O que o post diz ─────────────────────────────────────────────────────────

def test_cargo_sai_da_linha_da_vaga_sem_emoji(post):
    assert post.titulo == "Cientista de Dados Júnior"


def test_chamada_nao_vira_cargo():
    """"Vaga para quem quer trabalhar em…" é chamada de engajamento. Sem o
    corte, o cargo sairia como "para quem quer trabalhar…" — e o currículo
    seria otimizado para um cargo que não existe."""
    p = mod.extrair("Vaga para quem quer crescer na área de dados\n"
                    "Vaga: Engenheiro de Dados Pleno\n"
                    "Envie para rh@acme.com")
    assert p.titulo == "Engenheiro de Dados Pleno"


def test_rotulos_com_dois_pontos(post):
    assert post.salario == "R$ 12.000,00"
    assert post.modalidade == "100% Home Office"
    assert post.contratacao == "CLT"


def test_empresa_vem_da_linha_do_cliente(post):
    """Sem rótulo "Empresa:", o que identifica é a menção a cliente — e só
    ela: qualquer outra linha viraria nome de empresa."""
    assert post.empresa.startswith("THS Tecnologia")


def test_empresa_cai_para_o_dominio_do_email_quando_nao_ha_nada():
    p = mod.extrair("Vaga: Analista de Dados\nEnviar para vagas@acmedata.com.br")
    assert p.empresa == "acmedata"


def test_dominio_generico_nao_vira_empresa():
    """`recrutadora@gmail.com` não diz o nome de empresa nenhuma."""
    p = mod.extrair("Vaga: Analista de Dados\nEnviar para recruta@gmail.com")
    assert p.empresa == ""
    assert "empresa" in p.incertezas


# ── Por onde responder ───────────────────────────────────────────────────────

def test_email_e_assunto_pedido(post):
    assert post.contato.emails == ["contatorh@ths.inf.br"]
    assert post.contato.assunto == "Cientista de Dados Júnior – Sebrae-NA"


def test_link_de_curso_nao_e_canal_de_resposta(post):
    """O post traz `lnkd.in/deE3TwEs`, que é o curso da autora. Canal de
    resposta é perfil (`linkedin.com/in/`), e-mail ou telefone."""
    assert post.contato.perfis_linkedin == []


def test_valor_em_reais_nao_vira_telefone(post):
    assert post.contato.telefones == []


def test_telefone_com_ddd_entre_parenteses_conta():
    p = mod.extrair("Vaga: Analista de BI\nChame no WhatsApp (11) 99999-8888")
    assert p.contato.telefones == ["(11) 99999-8888"]
    assert p.contato.whatsapp_link() == "https://wa.me/5511999998888"


def test_numero_solto_sem_contexto_nao_conta():
    """"11 99999-8888" sem nenhuma palavra por perto pode ser qualquer coisa."""
    p = mod.extrair("Vaga: Analista\nProcesso com 11 99999-8888 candidatos inscritos")
    assert p.contato.telefones == []


def test_wa_me_no_texto_vira_telefone():
    p = mod.extrair("Vaga: Analista\nhttps://wa.me/5511988887777")
    assert p.contato.whatsapp_link() == "https://wa.me/5511988887777"


def test_perfil_do_linkedin_e_canal():
    p = mod.extrair("Vaga: Cientista de Dados\n"
                    "Chame em https://www.linkedin.com/in/fulana-recrutadora/")
    assert p.contato.perfis_linkedin == [
        "https://www.linkedin.com/in/fulana-recrutadora"]


def test_sem_canal_nenhum_o_post_declara(post):
    p = mod.extrair("Vaga: Analista de Dados\nEmpresa: Acme")
    assert not p.contato.tem_canal
    assert any("canal de resposta" in i for i in p.incertezas)


# ── Identidade ───────────────────────────────────────────────────────────────

def test_paragrafo_nao_vira_cargo():
    """Sem essa trava, "Hoje o mercado de dados está aquecido…" virava o título
    de uma vaga na fila e o assunto de um e-mail."""
    p = mod.extrair("Hoje o mercado de dados está aquecido e muita gente me "
                    "pergunta como se preparar para entrar na área de dados.")
    assert p.titulo == ""
    assert "cargo" in p.incertezas


def test_mesmo_post_mesmo_hash():
    """Colar duas vezes não pode criar duas vagas: a fila encheria de cópias e
    `guard.ja_candidatado` deixaria de proteger."""
    assert mod.hash_do_post(POST) == mod.hash_do_post(POST.replace("\n\n", "\n \n"))
    assert mod.hash_do_post(POST) != mod.hash_do_post(POST + "\nOutra vaga")


def test_modalidade_canonica():
    assert mod._modalidade_canonica("100% Home Office") == "remoto"
    assert mod._modalidade_canonica("Híbrido (2x semana)") == "híbrido"
    assert mod._modalidade_canonica("Presencial - SP") == "presencial"


# ── As mensagens ─────────────────────────────────────────────────────────────

RESUME = {
    "nome": "Ricardo Inoue",
    "email": "ricardo@exemplo.com",
    "telefone": "(11) 90000-0000",
    "linkedin": "https://www.linkedin.com/in/ricardo",
    "resumo_profissional": "Coordenador de dados com experiência em pipelines.",
    "tecnologias": ["Python", "SQL", "Power BI", "Databricks"],
    "experiencias": [{"cargo": "Coordenador de Dados", "empresa": "360BI",
                      "data_fim": None}],
}


def _vaga(tecnologias, cargo="Cientista de Dados Júnior", empresa="THS Tecnologia"):
    return SimpleNamespace(
        id=1, titulo=cargo, empresa=empresa,
        normalizado_json={"cargo": cargo, "tecnologias": tecnologias},
        score_breakdown_json={})


def test_mensagem_so_cita_tecnologia_que_o_curriculo_tem(post):
    """Invariante 3 no canal de mensagem: a vaga pede R e machine learning; o
    currículo do teste não tem nenhum dos dois, e eles não podem aparecer."""
    vaga = _vaga(["Python", "SQL", "R", "Machine Learning", "Power BI"])
    msgs = abordagem.montar(post, vaga, RESUME)
    for canal in ("email", "linkedin", "whatsapp"):
        texto = msgs[canal]["corpo"] if canal == "email" else msgs[canal]["texto"]
        assert "Python" in texto and "SQL" in texto
        assert "Machine Learning" not in texto
        # "R" sozinho não é subtexto de outra palavra: confere por vírgula.
        assert ", R," not in texto and ", R e" not in texto


def test_email_usa_o_assunto_que_o_post_pediu(post):
    msgs = abordagem.montar(post, _vaga(["Python", "SQL"]), RESUME)
    assert msgs["email"]["assunto"] == "Cientista de Dados Júnior – Sebrae-NA"
    assert msgs["email"]["para"] == ["contatorh@ths.inf.br"]


def test_email_sem_assunto_no_post_monta_um():
    p = mod.extrair("Vaga: Analista de Dados\nEnviar para rh@acme.com")
    msgs = abordagem.montar(p, _vaga(["SQL"], cargo="Analista de Dados"), RESUME)
    assert msgs["email"]["assunto"] == "Analista de Dados — Ricardo Inoue"


def test_linkedin_cabe_no_convite(post):
    """O convite do LinkedIn corta em 300 caracteres, no meio da frase."""
    vaga = _vaga(["Python", "SQL", "Power BI", "Databricks", "Spark", "dbt"])
    msgs = abordagem.montar(post, vaga, RESUME)
    assert msgs["linkedin"]["caracteres"] <= abordagem.LIMITE_LINKEDIN
    # O pedido é a última coisa a cair: sem ele a mensagem não pede nada.
    assert "currículo" in msgs["linkedin"]["texto"]


def test_saudacao_usa_o_autor_quando_informado(post):
    msgs = abordagem.montar(post, _vaga(["SQL"]), RESUME)
    assert msgs["linkedin"]["texto"].startswith("Olá, Júlia!")


def test_sem_autor_a_saudacao_e_neutra():
    """O nome de quem publicou não se adivinha pela primeira linha do post."""
    p = mod.extrair("Vaga: Analista de Dados\nEnviar para rh@acme.com")
    msgs = abordagem.montar(p, _vaga(["SQL"], cargo="Analista de Dados"), RESUME)
    assert msgs["linkedin"]["texto"].startswith("Olá!")


def test_whatsapp_traz_link_com_a_mensagem_escrita():
    p = mod.extrair("Vaga: Analista de BI\nWhatsApp (11) 99999-8888")
    msgs = abordagem.montar(p, _vaga(["SQL"], cargo="Analista de BI"), RESUME)
    assert msgs["whatsapp"]["link"].startswith("https://wa.me/5511999998888?text=")
    assert msgs["whatsapp"]["caracteres"] <= abordagem.LIMITE_WHATSAPP


def test_anexo_so_e_prometido_quando_existe(post):
    sem = abordagem.montar(post, _vaga(["SQL"]), RESUME, dossie=None)
    assert sem["email"]["anexar"] == ""
    assert "anexo" not in sem["email"]["corpo"].lower()

    com = abordagem.montar(post, _vaga(["SQL"]), RESUME,
                           dossie=SimpleNamespace(pronto=True))
    assert com["email"]["anexar"]
    assert "anexo" in com["email"]["corpo"].lower()


# ── O que o número não vê ────────────────────────────────────────────────────

def test_atencao_avisa_salario_abaixo_do_minimo(monkeypatch):
    """O score mede sobreposição de palavra-chave; salário abaixo do piso não
    aparece nele, e é o que decide se vale responder."""
    from jobapplier import salario as mod_salario

    monkeypatch.setattr(mod_salario, "carregar_faixa",
                        lambda *a, **k: mod_salario.Faixa(
                            minimo=10000, alvo=13000, maximo=16000, fator_pj=1.3))
    p = mod.extrair("Vaga: Analista de Dados\nRemuneração: R$ 4.500,00\n"
                    "Enviar para rh@acme.com")
    avisos = abordagem.pontos_de_atencao(p, {})
    assert any("abaixo do seu mínimo" in a for a in avisos), avisos


def test_atencao_nao_reclama_de_salario_dentro_da_faixa(monkeypatch, post):
    from jobapplier import salario as mod_salario

    monkeypatch.setattr(mod_salario, "carregar_faixa",
                        lambda *a, **k: mod_salario.Faixa(
                            minimo=10000, alvo=13000, maximo=16000, fator_pj=1.3))
    avisos = abordagem.pontos_de_atencao(post, {})
    assert not any("abaixo do seu mínimo" in a for a in avisos), avisos


def test_atencao_aponta_vaga_junior(post):
    avisos = abordagem.pontos_de_atencao(post, {})
    assert any("júnior" in a.lower() for a in avisos)


def test_atencao_repete_o_que_falta_no_post():
    p = mod.extrair("Vaga: Analista de Dados\nEnviar para rh@acme.com")
    avisos = abordagem.pontos_de_atencao(p, {})
    assert any("O post não diz" in a for a in avisos)
