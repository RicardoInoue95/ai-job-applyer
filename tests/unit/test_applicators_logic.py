"""Lógica pura dos applicators — o preenchimento automático de formulário.

Estas funções decidem o que é escrito num formulário de candidatura real, em nome
do usuário. Uma resposta errada aqui vai para um recrutador. Estavam sem
cobertura nenhuma.

Não tocam Playwright nem rede: recebem dicts e devolvem valores. O teste de
seletor/DOM fica em tests/e2e.
"""
import pytest

from jobapplier.applicators.greenhouse import (
    _auto_answer,
    _is_diversidade,
    _is_yes_no,
    _no_value,
    _pick_value,
    _value_to_label,
    _yes_value,
)

RESUME = {
    "nome": "Ricardo Inoue",
    "email": "info@exemplo.com",
    "linkedin": "https://linkedin.com/in/exemplo",
    "github": "https://github.com/exemplo",
    "localizacao": "São Paulo, SP",
    "tecnologias": ["Python", "SQL", "dbt", "Snowflake", "Azure Data Factory"],
    "idiomas": [
        {"nome": "Português", "nivel": "Nativo"},
        {"nome": "Inglês", "nivel": "Avançado"},
    ],
    "experiencias": [
        {"empresa": "Empresa Atual", "cargo": "Analytics Engineer",
         "data_inicio": "01/2023", "data_fim": None},
    ],
}

SIM_NAO = [{"label": "Sim", "value": "1"}, {"label": "Não", "value": "2"}]
YES_NO = [{"label": "Yes", "value": "10"}, {"label": "No", "value": "20"}]


# ── _pick_value / _value_to_label ─────────────────────────────────────────────

def test_pick_value_por_substring_case_insensitive():
    assert _pick_value(SIM_NAO, "sim") == "1"
    assert _pick_value(SIM_NAO, "SIM") == "1"


def test_pick_value_sem_match_retorna_none():
    assert _pick_value(SIM_NAO, "talvez") is None


def test_pick_value_com_hint_vazio_retorna_none():
    assert _pick_value(SIM_NAO, "") is None


def test_pick_value_lista_vazia():
    assert _pick_value([], "sim") is None


def test_value_to_label_ida_e_volta():
    assert _value_to_label(SIM_NAO, "1") == "Sim"
    # Compara como string: o Greenhouse devolve IDs numéricos.
    assert _value_to_label(SIM_NAO, 1) == "Sim"


def test_value_to_label_desconhecido():
    assert _value_to_label(SIM_NAO, "99") is None


# ── _is_yes_no / _yes_value / _no_value ───────────────────────────────────────

def test_is_yes_no_por_tipo_de_campo():
    assert _is_yes_no("yes_no", [])
    assert _is_yes_no("boolean", [])


def test_is_yes_no_detecta_select_em_portugues():
    assert _is_yes_no("multi_value_single_select", SIM_NAO)


def test_is_yes_no_detecta_select_em_ingles():
    assert _is_yes_no("multi_value_single_select", YES_NO)


def test_is_yes_no_falso_para_select_comum():
    opcoes = [{"label": "Básico", "value": "1"}, {"label": "Avançado", "value": "2"}]
    assert not _is_yes_no("multi_value_single_select", opcoes)


def test_is_yes_no_falso_para_texto_livre():
    assert not _is_yes_no("input_text", [])


def test_yes_no_value_nos_dois_idiomas():
    assert _yes_value(SIM_NAO) == "1"
    assert _no_value(SIM_NAO) == "2"
    assert _yes_value(YES_NO) == "10"
    assert _no_value(YES_NO) == "20"


def test_yes_no_value_sem_opcoes_cai_no_literal():
    assert _yes_value([]) == "yes"
    assert _no_value([]) == "no"


# ── _is_diversidade ───────────────────────────────────────────────────────────

def test_detecta_perguntas_de_diversidade():
    for label in ("Qual seu gênero?", "Orientação sexual", "Raça/Etnia",
                  "Você tem alguma deficiência?", "Identidade de genero",
                  "Declaração de raca"):
        assert _is_diversidade(label), label


def test_pergunta_tecnica_nao_e_diversidade():
    for label in ("Anos de experiência com Python", "Pretensão salarial",
                  "Você tem CNPJ?"):
        assert not _is_diversidade(label), label


# ── _auto_answer: dados pessoais ──────────────────────────────────────────────

def test_cpf_vem_da_config_e_nao_do_curriculo():
    # CPF é PII que mora na config, nunca no currículo.
    assert _auto_answer("Informe seu CPF", "input_text", [], RESUME, {},
                        {"cpf": "123.456.789-00"}) == "123.456.789-00"


def test_cpf_sem_config_retorna_none():
    assert _auto_answer("CPF", "input_text", [], RESUME, {}, {}) is None


def test_cpf_sem_config_dados_nao_estoura():
    assert _auto_answer("CPF", "input_text", [], RESUME, {}, None) is None


def test_linkedin_e_github_vem_do_curriculo():
    assert _auto_answer("URL do LinkedIn", "input_text", [], RESUME, {}) == RESUME["linkedin"]
    assert _auto_answer("Perfil GitHub", "input_text", [], RESUME, {}) == RESUME["github"]


def test_campo_ausente_no_curriculo_retorna_none():
    assert _auto_answer("LinkedIn", "input_text", [], {"tecnologias": []}, {}) is None


# ── _auto_answer: cargo e empresa ─────────────────────────────────────────────

def test_cargo_atual_em_varias_redacoes():
    for label in ("Cargo atual", "Current position", "Current role", "Qual seu cargo"):
        assert _auto_answer(label, "input_text", [], RESUME, {}) == "Analytics Engineer", label


def test_empresa_atual_em_varias_redacoes():
    for label in ("Empresa atual", "Current company", "Current employer",
                  "Most recent company", "Nome da empresa"):
        assert _auto_answer(label, "input_text", [], RESUME, {}) == "Empresa Atual", label


def test_sem_experiencias_cargo_e_empresa_dao_none():
    vazio = {"tecnologias": [], "experiencias": []}
    assert _auto_answer("Cargo atual", "input_text", [], vazio, {}) is None
    assert _auto_answer("Empresa atual", "input_text", [], vazio, {}) is None


# ── _auto_answer: localização ─────────────────────────────────────────────────

def test_estado_casa_com_sao_paulo():
    opcoes = [{"label": "São Paulo (SP)", "value": "35"},
              {"label": "Rio de Janeiro (RJ)", "value": "33"}]
    assert _auto_answer("Estado de residência", "multi_value_single_select",
                        opcoes, RESUME, {}) == "35"


def test_cidade_prefere_match_exato_a_prefixo():
    opcoes = [{"label": "São Paulo - Zona Sul", "value": "2"},
              {"label": "São Paulo", "value": "1"}]
    # Match exato deve ganhar, mesmo aparecendo depois na lista.
    assert _auto_answer("Cidade onde reside", "multi_value_single_select",
                        opcoes, RESUME, {}) == "1"


def test_cidade_cai_no_prefixo_quando_nao_ha_exato():
    opcoes = [{"label": "São Paulo - Zona Sul", "value": "2"}]
    assert _auto_answer("Cidade", "multi_value_single_select",
                        opcoes, RESUME, {}) == "2"


def test_candidato_de_outro_estado_nao_responde_sao_paulo():
    outro = {**RESUME, "localizacao": "Curitiba, PR"}
    opcoes = [{"label": "São Paulo (SP)", "value": "35"}]
    assert _auto_answer("Estado de residência", "multi_value_single_select",
                        opcoes, outro, {}) is None


def test_disponibilidade_presencial_sim_para_quem_esta_em_sp():
    assert _auto_answer("Disponibilidade para trabalho presencial em São Paulo",
                        "yes_no", SIM_NAO, RESUME, {}) == "1"


def test_disponibilidade_presencial_nao_para_quem_esta_fora():
    fora = {**RESUME, "localizacao": "Recife, PE"}
    assert _auto_answer("Disponibilidade para atuar presencial",
                        "yes_no", SIM_NAO, fora, {}) == "2"


# ── _auto_answer: idioma ──────────────────────────────────────────────────────

def test_nivel_de_ingles_vem_do_curriculo():
    opcoes = [{"label": "Básico", "value": "1"},
              {"label": "Intermediário", "value": "2"},
              {"label": "Avançado", "value": "3"},
              {"label": "Fluente", "value": "4"}]
    assert _auto_answer("Nível de inglês", "multi_value_single_select",
                        opcoes, RESUME, {}) == "3"


def test_ingles_como_sim_nao_responde_sim():
    assert _auto_answer("Você fala inglês?", "yes_no", SIM_NAO, RESUME, {}) == "1"


def test_ingles_ausente_no_curriculo_assume_intermediario():
    sem_ingles = {**RESUME, "idiomas": [{"nome": "Português", "nivel": "Nativo"}]}
    opcoes = [{"label": "Intermediário", "value": "2"}]
    assert _auto_answer("Fluência em inglês", "multi_value_single_select",
                        opcoes, sem_ingles, {}) == "2"


def test_variacoes_de_grafia_de_ingles():
    for label in ("Nível de inglês", "Nivel de ingles", "English level",
                  "Fluência na língua inglesa"):
        assert _auto_answer(label, "yes_no", SIM_NAO, RESUME, {}) == "1", label


# ── _auto_answer: desconhecido ────────────────────────────────────────────────

def test_pergunta_desconhecida_retorna_none():
    """Invariante: o que não sabemos responder vira pergunta manual, não chute."""
    assert _auto_answer("Qual sua cor favorita?", "input_text", [], RESUME, {}) is None


def test_label_vazio_nao_estoura():
    assert _auto_answer("", "input_text", [], RESUME, {}) is None


# ── As famílias que mais bloqueiam envio ──────────────────────────────────────
# Medido sobre 61 avaliações de preenchimento reais: nenhuma vaga do acervo era
# enviável, e as perguntas obrigatórias sem resposta se repetiam. Estas são as
# que o currículo e a config já respondiam — a informação existia e não chegava
# ao formulário.

@pytest.mark.pessoal
def test_pretensao_vem_da_faixa_configurada():
    """`dados_pessoais.salario` está vazio e a faixa vive em `pretensao`. Eram
    duas fontes, e o formulário consultava a que ninguém preencheu."""
    r = _auto_answer("Qual é a sua pretensão salarial?", "input_text", [],
                     RESUME, {"senioridade": "pleno"}, {})
    assert r and "R$" in r


@pytest.mark.pessoal
def test_pretensao_pj_nao_sai_igual_a_clt():
    """PJ sem 13º, férias, FGTS e INSS patronal: igualar é aceitar ~30% a menos."""
    clt = _auto_answer("Pretensão salarial", "input_text", [], RESUME,
                       {"regime_contratacao": "CLT"}, {})
    pj = _auto_answer("Pretensão salarial", "input_text", [], RESUME,
                      {"regime_contratacao": "PJ"}, {})
    assert clt != pj
    assert "PJ" in pj


def test_salario_explicito_na_config_tem_precedencia():
    """Preferência declarada do usuário vence a faixa calculada."""
    r = _auto_answer("Salary expectation", "input_text", [], RESUME, {},
                     {"salario": "A combinar"})
    assert r == "A combinar"


def test_pretensao_em_campo_de_selecao_nao_e_chutada():
    """Não dá para escolher uma opção de lista sem saber os valores."""
    assert _auto_answer("Pretensão salarial", "multi_value_single_select",
                        SIM_NAO, RESUME, {}, {}) is None


def test_pais_de_residencia():
    assert _auto_answer("Please select the country where you currently reside.",
                        "input_text", [], RESUME, {}) == "Brazil"
    paises = [{"label": "Brazil", "value": "55"}, {"label": "Chile", "value": "56"}]
    assert _auto_answer("Country of residence", "multi_value_single_select",
                        paises, RESUME, {}) == "55"


def test_empregador_e_cargo_atual_ou_anterior():
    """A variante "current or previous" não casava com a regra de "cargo atual"."""
    assert _auto_answer("Who is your current or previous employer?",
                        "input_text", [], RESUME, {}) == "Empresa Atual"
    assert _auto_answer("What is your current or previous job title?",
                        "input_text", [], RESUME, {}) == "Analytics Engineer"


@pytest.mark.parametrize("pergunta", [
    "Have you ever been employed by Stripe or a Stripe affiliate?",
    "Você já trabalhou em algum momento no C6 Bank?",
    "Are you currently or have you ever worked for Airbnb in any capacity?",
    "Have you previously been employed at Affirm for any length of time?",
])
def test_vinculo_previo_com_a_empresa_e_nao(pergunta):
    """Derivação, não chute: o currículo lista o histórico completo, então a
    ausência da empresa nele é informação."""
    assert _auto_answer(pergunta, "multi_value_single_select", YES_NO,
                        RESUME, {"empresa": "Stripe"}) == "20"


def test_nao_responde_se_a_empresa_estiver_no_historico():
    """Quem trabalhou lá sabe responder melhor que comparação de strings — e um
    "não" errado aqui é declaração falsa num formulário."""
    ex_empregador = {**RESUME, "experiencias": [
        {"empresa": "Stripe", "cargo": "Data Engineer", "data_inicio": "01/2023"}]}
    assert _auto_answer("Have you ever been employed by Stripe?",
                        "multi_value_single_select", YES_NO,
                        ex_empregador, {"empresa": "Stripe"}) is None


@pytest.mark.parametrize("pergunta", [
    "Você se identifica com qual raça e/ou cor?",
    "Qual a sua identidade de gênero?",
    "Você possui alguma deficiência?",
    "Qual é o tipo da sua deficiência?",
])
def test_pergunta_sensivel_continua_sem_resposta(pergunta):
    """Invariante 3. Alargar o preenchimento não pode alargar isto."""
    assert _auto_answer(pergunta, "multi_value_single_select", SIM_NAO,
                        RESUME, {}) is None


# ── O que NÃO pode ser respondido, mesmo tendo o dado ─────────────────────────
# Alargar o preenchimento automático criou quatro respostas erradas de uma vez.
# Duas nasceram da própria melhoria da pretensão salarial: a palavra
# "compensation" casava também com "current compensation", e a faixa desejada
# passou a ser escrita na pergunta sobre o salário que ele RECEBE.

@pytest.mark.parametrize("pergunta", [
    "What is your current compensation?",
    "Do you currently receive any variable compensation (e.g., Annual Bonus)?",
    "Qual é o seu salário atual?",
    "What is your current salary?",
])
def test_salario_atual_nao_e_respondido_com_a_pretensao(pergunta):
    """Pretensão é o que ele quer; salário atual é um fato que o currículo não
    informa. Responder um no lugar do outro é declaração falsa, não ênfase."""
    assert _auto_answer(pergunta, "input_text", [], RESUME,
                        {"senioridade": "pleno"}, {}) is None


@pytest.mark.pessoal
def test_pretensao_continua_respondida():
    """A correção acima não pode ter desligado a melhoria."""
    assert _auto_answer("What is your salary expectation?", "input_text", [],
                        RESUME, {"senioridade": "pleno"}, {}) is not None


def test_consentimento_de_dado_sensivel_nao_e_dado_por_ele():
    """"Consentimento - Diversidade e Inclusão (D&I)" caía no sim automático de
    consentimento e entregava dado que ele talvez não quisesse dar."""
    assert _auto_answer("Consentimento - Diversidade e Inclusão (D&I)",
                        "multi_value_single_select", SIM_NAO, RESUME, {}) is None


def test_consentimento_comum_continua_automatico():
    """Consentir em processar a candidatura é formalidade sem a qual nada anda."""
    assert _auto_answer("Consentimento para tratamento dos dados da candidatura",
                        "multi_value_single_select", SIM_NAO, RESUME, {}) == "1"


def test_autorizacao_de_trabalho_so_quando_a_vaga_e_no_brasil():
    """Respondia "Sim" sempre. A pergunta é sobre o país DA VAGA, e a maioria dos
    boards do Greenhouse não é no Brasil — "sim" ali é falso numa pergunta
    eliminatória, descoberto só na entrevista."""
    fora = _auto_answer("Are you legally authorized to work in the country where "
                        "the job is located?", "multi_value_single_select", YES_NO,
                        RESUME, {"localizacao": "San Francisco, CA"})
    assert fora is None

    aqui = _auto_answer("Are you legally authorized to work in the country where "
                        "the job is located?", "multi_value_single_select", YES_NO,
                        RESUME, {"localizacao": "São Paulo, Brasil"})
    assert aqui == "10"


# ── A política de resposta agora é aplicada, não decorativa ───────────────────
# `agents/respostas.py` existia com testes e ZERO chamadores — segurança que não
# roda é pior que ausência de segurança, porque passa sensação de proteção
# (invariante 10). O encaixe é veto: as regras abaixo continuam decidindo o
# valor, mas nenhuma pode devolver o que a política proíbe.

@pytest.mark.parametrize("pergunta", [
    "Qual a sua identidade de gênero?",
    "Você se identifica com qual raça e/ou cor?",
    "Do you have any disability/neurodiversity?",
    "Veteran Status:",
    "Pronouns",
    "Você é uma pessoa com deficiência (PCD)?",
    "Sexual orientation",
    # O caso que escapou: consentimento SOBRE dado sensível. A regra de
    # consentimento respondia "sim" porque não sabia de diversidade.
    "Consentimento - Diversidade e Inclusão (D&I)",
])
def test_pergunta_sensivel_e_vetada_pela_politica(pergunta):
    for tipo, vals in (("multi_value_single_select", SIM_NAO), ("input_text", [])):
        assert _auto_answer(pergunta, tipo, vals, RESUME, {}) is None, (pergunta, tipo)


@pytest.mark.parametrize("pergunta", [
    "Do you have experience with Spark and Kafka?",
    "Você tem experiência com Airflow e dbt?",
    "Experience with Risk, Payments and Data?",
])
def test_pergunta_composta_nao_e_respondida(pergunta):
    """Todas as partes precisam ser verdadeiras para um "sim". Sem saber qual o
    candidato cobre, a resposta é dele."""
    assert _auto_answer(pergunta, "multi_value_single_select", YES_NO,
                        RESUME, {}) is None


def test_pergunta_simples_de_ferramenta_continua_respondida():
    """O veto de composta não pode engolir a pergunta de uma tecnologia só."""
    r = _auto_answer("Do you have experience with Python?",
                     "multi_value_single_select", YES_NO, RESUME, {})
    assert r == "10"


def test_a_politica_tem_chamador():
    """O teste que faltava: o módulo existia e nada o usava."""
    import inspect

    from jobapplier.applicators import greenhouse

    fonte = inspect.getsource(greenhouse._auto_answer)
    assert "respostas.classificar" in fonte
    assert "Classe.SENSIVEL" in fonte


# ── Identificação básica, por rótulo ──────────────────────────────────────────
# No Greenhouse nome, e-mail e telefone são preenchidos por seletor fixo e nunca
# passavam por `_auto_answer`. A extensão de navegador é o primeiro chamador que
# os manda por rótulo — e são os três campos mais comuns de qualquer formulário.
# Ficavam como pergunta manual, invisível enquanto só o Greenhouse chamava.

@pytest.mark.parametrize("label,esperado", [
    ("Nome completo", "Ricardo Inoue"),
    ("Nome", "Ricardo Inoue"),
    ("Full name", "Ricardo Inoue"),
    ("Primeiro nome", "Ricardo"),
    ("First name", "Ricardo"),
    ("Sobrenome", "Inoue"),
    ("E-mail", "info@exemplo.com"),
    ("Email de contato", "info@exemplo.com"),
])
def test_identificacao_por_rotulo(label, esperado):
    assert _auto_answer(label, "input_text", [], RESUME, {}) == esperado


def test_telefone_por_rotulo():
    com_fone = {**RESUME, "telefone": "+55 11 90000-0000"}
    for label in ("Telefone", "Celular", "Phone number", "WhatsApp"):
        assert _auto_answer(label, "input_text", [], com_fone, {}) == "+55 11 90000-0000"


def test_cidade_em_campo_de_texto():
    """A regra de cidade só sabia escolher opção numa lista. Em campo aberto
    caía fora — invisível no Greenhouse, onde o campo tem seletor próprio."""
    assert _auto_answer("Cidade onde reside", "input_text", [], RESUME,
                        {}) == "São Paulo, SP"


def test_curriculo_sem_o_dado_nao_inventa():
    vazio = {"tecnologias": [], "experiencias": []}
    for label in ("Nome completo", "E-mail", "Telefone"):
        assert _auto_answer(label, "input_text", [], vazio, {}) is None


def test_identificacao_nao_atropela_pergunta_de_verdade():
    """"Qual o nome da empresa em que você trabalhou?" contém "nome" e não é o
    nome do candidato. A regra exige rótulo curto ou frase de identificação."""
    r = _auto_answer("Qual o nome da empresa em que você trabalhou?",
                     "input_text", [], RESUME, {})
    assert r != RESUME["nome"]


@pytest.mark.parametrize("label", [
    "Onde você encontrou essa vaga? (Opcional)",
    "Como você conheceu a vaga?",
    "How did you hear about us?",
])
def test_origem_da_vaga_em_varias_redacoes(label):
    """"Onde você encontrou essa vaga?" é a redação da Gupy e não casava com
    nenhuma das variantes conhecidas — virava pergunta manual num formulário
    real, tendo resposta óbvia. Achado rodando a extensão, não lendo código."""
    assert _auto_answer(label, "input_text", [], RESUME, {}) == "LinkedIn"


# ── Documentos da etapa de perguntas da empresa (Gupy) ────────────────────────

_DOCS = {"cpf": "111", "rg": "12.345.678-9", "rg_orgao_emissor": "SSP/SP",
         "nome_mae": "Maria Silva", "nome_pai": "João Silva",
         "naturalidade": "São Paulo, SP"}


@pytest.mark.parametrize("rotulo,esperado", [
    ("RG", "12.345.678-9"),
    ("Órgão e Estado de emissão do RG", "SSP/SP"),
    ("Nome da mãe", "Maria Silva"),
    ("Nome do pai", "João Silva"),
    ("Naturalidade (cidade e estado de nascimento)", "São Paulo, SP"),
])
def test_documentos_da_gupy_sao_respondidos(rotulo, esperado):
    """Estas seis perguntas travavam a etapa onde 152 candidaturas morreram."""
    assert _auto_answer(rotulo, "textarea", [], {}, {}, _DOCS) == esperado


def test_orgao_emissor_nao_recebe_o_numero_do_rg():
    """"Órgão" contém as letras "rg". Casar por substring devolvia o número do
    documento para a pergunta do órgão emissor — dado errado no campo errado."""
    resposta = _auto_answer("Órgão e Estado de emissão do RG",
                            "textarea", [], {}, {}, _DOCS)
    assert resposta == "SSP/SP"
    assert resposta != _DOCS["rg"]


@pytest.mark.parametrize("rotulo", [
    "RG", "Nome da mãe", "Nome do pai", "Naturalidade (cidade e estado)",
])
def test_documento_ausente_vira_manual_e_nunca_chute(rotulo):
    """Invariante 3: sem o dado, a pergunta é do candidato. Um RG inventado
    seria fraude em documento, não um palpite infeliz."""
    assert _auto_answer(rotulo, "textarea", [], {}, {}, {"cpf": "111"}) is None


# ── Autodeclaração: repetir o que ELE disse, nunca decidir por ele ────────────

_DIV = {"diversidade": {"genero": "Homem cisgênero", "orientacao": "Heterossexual",
                        "raca": "Amarela", "deficiencia": "Não"}}


def _ops(*labels):
    return [{"label": e, "value": str(i)} for i, e in enumerate(labels, 1)]


@pytest.mark.parametrize("rotulo,opcoes,esperado", [
    ("Você se identifica com qual raça e/ou cor?",
     ("Branca", "Preta", "Parda", "Amarela", "Indígena"), "Amarela"),
    ("Qual sua orientação sexual?",
     ("Heterossexual", "Homossexual", "Bissexual"), "Heterossexual"),
    ("Qual a sua identidade de gênero?",
     ("Homem cisgênero", "Mulher cisgênera", "Não binário"), "Homem cisgênero"),
    ("Você possui alguma deficiência?",
     ("Sim", "Não"), "Não"),
])
def test_autodeclaracao_responde_o_que_foi_declarado(rotulo, opcoes, esperado):
    """O ramo de diversidade era código MORTO: o veto de pergunta sensível
    devolvia None na linha 270 e ele estava na 698. Raça e gênero viravam
    pergunta manual em todo formulário, com o dado declarado no config."""
    ops = _ops(*opcoes)
    valor = _auto_answer(rotulo, "multi_value_single_select", ops, {}, {}, _DIV)
    assert valor == next(o["value"] for o in ops if o["label"] == esperado)


@pytest.mark.parametrize("rotulo", [
    "Você se identifica com qual raça e/ou cor?",
    "Qual a sua identidade de gênero?",
    "Você possui alguma deficiência?",
])
def test_sem_declaracao_continua_manual(rotulo):
    """Invariante 3: o sistema repete a declaração dele, não inventa uma."""
    ops = _ops("Sim", "Não", "Amarela", "Homem cisgênero")
    assert _auto_answer(rotulo, "multi_value_single_select", ops, {}, {}, {}) is None


def test_consentimento_de_diversidade_nao_vira_sim_automatico():
    """O bug que criou o veto: "Consentimento - Diversidade e Inclusão" caía no
    sim automático de consentimento porque a regra de consentimento não sabia de
    diversidade. A autodeclaração não pode reabrir essa porta."""
    valor = _auto_answer("Consentimento - Diversidade e Inclusão",
                         "yes_no", _ops("Sim", "Não"), {}, {}, _DIV)
    assert valor is None


# ── Parentesco: resposta certa reaproveitada onde não vale é mentira ─────────

_PAR = {"parentesco_empresas": ["itau", "btg"]}


def test_parentesco_e_nao_fora_das_empresas_declaradas():
    valor = _auto_answer("Você possui grau de parentesco com algum colaborador?",
                         "yes_no", _ops("Sim", "Não"), {}, {"empresa": "c6bank"}, _PAR)
    assert valor == "2"


@pytest.mark.parametrize("empresa", ["Itau Unibanco", "BTG Pactual", "itau"])
def test_parentesco_na_empresa_declarada_e_pergunta_dele(empresa):
    """Ele tem parente no Itaú e no BTG. "Não" ali seria declaração falsa num
    formulário real — invariante 3 pelo caminho menos óbvio, o de uma resposta
    verdadeira reaproveitada onde não vale."""
    valor = _auto_answer("Você possui grau de parentesco com algum colaborador?",
                         "yes_no", _ops("Sim", "Não"), {}, {"empresa": empresa}, _PAR)
    assert valor is None


def test_indicacao_e_nao():
    valor = _auto_answer("Você é uma pessoa indicada por algum colaborador?",
                         "yes_no", _ops("Sim", "Não"), {}, {"empresa": "c6bank"}, {})
    assert valor == "2"


def test_nome_de_preferencia_e_preenchido():
    """Campo obrigatório em vários formulários Greenhouse e nunca preenchido: a
    candidatura do c6bank parou em "Nome de preferência é obrigatório" depois de
    todo o resto ter dado certo."""
    r = {"nome": "Fulano de Tal Silva"}
    assert _auto_answer("Nome de preferência", "input_text", [], r, {}, {}) == "Fulano"


def test_nome_de_preferencia_nao_e_confundido_com_nome_completo():
    """"Nome de preferência" contém "nome": sem ordem certa cairia na regra de
    nome completo e escreveria o nome inteiro num campo de apelido."""
    r = {"nome": "Fulano de Tal Silva"}
    assert _auto_answer("Nome completo", "input_text", [], r, {}, {}) == "Fulano de Tal Silva"
    assert _auto_answer("Nome de preferência", "input_text", [], r, {}, {}) == "Fulano"


def test_consentimento_longo_nao_vira_pergunta_composta():
    """"dados confidenciais E manuseados conforme a Política de Privacidade" é
    UM consentimento; o "e" é gramatical. O veto de composta travava toda
    candidatura do c6bank depois de todo o resto ter dado certo."""
    ops = _ops("Sim", "Não")
    valor = _auto_answer(
        "Você está de acordo em fornecer dados citados neste formulário sendo "
        "eles confidenciais e manuseados conforme a nossa Política de Privacidade?",
        "yes_no", ops, {}, {}, {})
    assert valor == "1"


def test_pergunta_tecnica_composta_continua_manual():
    """A exceção do consentimento não pode afrouxar o veto que ela contorna:
    "Spark e Kafka" com só uma das duas continua sendo resposta dele."""
    valor = _auto_answer("Você tem experiência com Spark e Kafka?",
                         "yes_no", _ops("Sim", "Não"), {}, {}, {})
    assert valor is None


def test_privacidade_nao_e_lida_como_cidade():
    """**"privacidade" termina em "cidade".** Casando por substring, toda
    pergunta de "Política de Privacidade" caía no ramo de cidade de residência,
    não achava São Paulo na lista e devolvia None. Todo formulário brasileiro
    tem essa frase — e a candidatura parava depois de tudo o mais ter dado
    certo. Segundo termo curto a fazer isso hoje; o primeiro foi "rg" dentro de
    "órgão"."""
    ops = _ops("Sim", "Não")
    resume = {"localizacao": "São Paulo"}
    assert _auto_answer("Aceita a Política de Privacidade?",
                        "yes_no", ops, resume, {}, {}) == "1"


def test_cidade_de_residencia_continua_funcionando():
    """A correção não pode quebrar o ramo que ela conserta."""
    resume = {"localizacao": "São Paulo"}
    assert _auto_answer("Cidade onde reside", "input_text", [], resume, {}, {}) \
        == "São Paulo"
    ops = _ops("Rio de Janeiro", "São Paulo", "Belo Horizonte")
    assert _auto_answer("Cidade", "multi_value_single_select", ops, resume, {}, {}) == "2"
