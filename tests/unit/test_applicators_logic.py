"""Lógica pura dos applicators — o preenchimento automático de formulário.

Estas funções decidem o que é escrito num formulário de candidatura real, em nome
do usuário. Uma resposta errada aqui vai para um recrutador. Estavam sem
cobertura nenhuma.

Não tocam Playwright nem rede: recebem dicts e devolvem valores. O teste de
seletor/DOM fica em tests/e2e.
"""
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
