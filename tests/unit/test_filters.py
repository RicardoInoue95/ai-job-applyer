"""Testes dos Módulos 4A e 4B — filtros pré e pós-normalização.

São funções puras e decidem se uma vaga custa uma chamada Gemini ou não. Um
falso negativo aqui descarta silenciosamente vaga boa; um falso positivo gasta
token. Estavam sem cobertura nenhuma.
"""
import pytest

from jobapplier.filters import post_filter, pre_filter


class VagaFake:
    """Duplica a interface que o pre_filter consome via getattr."""

    def __init__(self, titulo="", descricao="", localizacao=""):
        self.titulo = titulo
        self.descricao = descricao
        self.localizacao = localizacao


CFG = {
    "cargos_alvo": ["Data Engineer", "Analista de Dados"],
    "palavras_bloqueadas": ["estágio", "trainee"],
}


# ── 4A: cargo alvo ────────────────────────────────────────────────────────────

def test_aceita_titulo_com_cargo_alvo():
    passou, _ = pre_filter.apply(VagaFake(titulo="Senior Data Engineer"), CFG)
    assert passou


def test_rejeita_titulo_sem_cargo_alvo():
    passou, motivo = pre_filter.apply(VagaFake(titulo="Product Designer"), CFG)
    assert not passou
    assert "cargo alvo" in motivo


def test_cargo_alvo_case_insensitive():
    passou, _ = pre_filter.apply(VagaFake(titulo="DATA ENGINEER PLENO"), CFG)
    assert passou


def test_sem_cargos_alvo_configurados_aceita_qualquer_titulo():
    passou, _ = pre_filter.apply(VagaFake(titulo="Product Designer"), {})
    assert passou


# ── 4A: palavras bloqueadas ───────────────────────────────────────────────────

def test_rejeita_palavra_bloqueada():
    passou, motivo = pre_filter.apply(
        VagaFake(titulo="Estágio em Data Engineer"), CFG
    )
    assert not passou
    assert "bloqueada" in motivo


def test_bloqueio_vence_cargo_alvo():
    # A vaga tem cargo alvo válido, mas a palavra bloqueada deve prevalecer.
    passou, motivo = pre_filter.apply(VagaFake(titulo="Trainee Data Engineer"), CFG)
    assert not passou
    assert "bloqueada" in motivo


# ── 4A: localização ───────────────────────────────────────────────────────────

def test_aceita_localizacao_brasileira():
    passou, _ = pre_filter.apply(
        VagaFake(titulo="Data Engineer", localizacao="São Paulo, Brasil"), CFG
    )
    assert passou


def test_rejeita_localizacao_estrangeira_explicita():
    passou, motivo = pre_filter.apply(
        VagaFake(titulo="Data Engineer", localizacao="Austin, USA"), CFG
    )
    assert not passou
    assert "fora do Brasil" in motivo


def test_rejeita_pais_no_fim_da_string():
    """Regressão: a lista antiga exigia vírgula/espaço após o país, então
    localização terminando no nome do país passava batido."""
    for loc in ("Austin, USA", "London, UK", "Toronto, Canada",
                "Berlin, Germany", "Bangalore, India", "Sydney, Australia",
                "Mexico City, Mexico", "Austin, U.S.", "New York, U.S.A."):
        passou, _ = pre_filter.apply(
            VagaFake(titulo="Data Engineer", localizacao=loc), CFG
        )
        assert not passou, f"deveria rejeitar {loc!r}"


def test_fronteira_de_palavra_evita_falso_positivo():
    """'Indiana' contém 'india' mas não é a Índia."""
    passou, _ = pre_filter.apply(
        VagaFake(titulo="Data Engineer", localizacao="Indianapolis"), CFG
    )
    assert passou


def test_remoto_vence_localizacao_estrangeira():
    passou, _ = pre_filter.apply(
        VagaFake(titulo="Data Engineer", localizacao="Remote, USA"), CFG
    )
    assert passou


def test_localizacao_vazia_nao_rejeita():
    # Empresa internacional que não preencheu o campo não deve ser descartada.
    passou, _ = pre_filter.apply(
        VagaFake(titulo="Data Engineer", localizacao=""), CFG
    )
    assert passou


def test_localizacao_ambigua_nao_rejeita():
    passou, _ = pre_filter.apply(
        VagaFake(titulo="Data Engineer", localizacao="LATAM"), CFG
    )
    assert passou


def test_aceita_dict_alem_de_objeto():
    """pre_filter suporta vaga como dict — usado pelos coletores."""
    passou, _ = pre_filter.apply(
        {"titulo": "Data Engineer", "descricao": "", "localizacao": "Brasil"}, CFG
    )
    assert passou


# ── 4B: tecnologias obrigatórias ──────────────────────────────────────────────

def test_normalizado_vazio_passa():
    passou, _ = post_filter.apply({}, {"palavras_obrigatorias": {"termos": ["dbt"]}})
    assert passou


def test_modo_qualquer_aceita_uma_tecnologia():
    cfg = {"palavras_obrigatorias": {"termos": ["dbt", "airflow"], "modo": "qualquer"}}
    passou, _ = post_filter.apply({"tecnologias": ["dbt", "Python"]}, cfg)
    assert passou


def test_modo_qualquer_rejeita_quando_nenhuma_presente():
    cfg = {"palavras_obrigatorias": {"termos": ["dbt", "airflow"], "modo": "qualquer"}}
    passou, motivo = post_filter.apply({"tecnologias": ["Python", "SQL"]}, cfg)
    assert not passou
    assert "nenhuma tecnologia obrigatória" in motivo


def test_modo_todas_exige_todas():
    cfg = {"palavras_obrigatorias": {"termos": ["dbt", "airflow"], "modo": "todas"}}
    passou, motivo = post_filter.apply({"tecnologias": ["dbt"]}, cfg)
    assert not passou
    assert "ausentes" in motivo


def test_modo_todas_aceita_quando_completo():
    cfg = {"palavras_obrigatorias": {"termos": ["dbt", "airflow"], "modo": "todas"}}
    passou, _ = post_filter.apply({"tecnologias": ["dbt", "Airflow", "SQL"]}, cfg)
    assert passou


def test_match_de_tecnologia_e_por_substring_case_insensitive():
    cfg = {"palavras_obrigatorias": {"termos": ["airflow"], "modo": "qualquer"}}
    passou, _ = post_filter.apply({"tecnologias": ["Apache Airflow 2.8"]}, cfg)
    assert passou


# ── 4B: anos de experiência ───────────────────────────────────────────────────

def test_rejeita_experiencia_acima_do_maximo():
    cfg = {"anos_experiencia_maximo": 5}
    passou, motivo = post_filter.apply({"anos_experiencia_minimo": 8}, cfg)
    assert not passou
    assert "acima do máximo" in motivo


def test_aceita_experiencia_dentro_do_maximo():
    cfg = {"anos_experiencia_maximo": 5}
    passou, _ = post_filter.apply({"anos_experiencia_minimo": 3}, cfg)
    assert passou


def test_aceita_experiencia_exatamente_no_limite():
    cfg = {"anos_experiencia_maximo": 5}
    passou, _ = post_filter.apply({"anos_experiencia_minimo": 5}, cfg)
    assert passou


def test_sem_maximo_configurado_nao_filtra():
    passou, _ = post_filter.apply({"anos_experiencia_minimo": 20}, {})
    assert passou


# ── Modalidade: termo negado não conta ────────────────────────────────────────
# "We do not offer remote-only roles" continha "remote" e virava Remoto. É pior
# que um erro qualquer: modalidade alimenta o filtro geográfico, então a vaga de
# Amsterdam entrava na fila como remota brasileira em vez de ser descartada — o
# erro entra para dentro.

ADYEN = ("This role is based out of our Amsterdam office. We are an office-first "
         "company and value in-person collaboration; we do not offer remote-only "
         "roles.")


def test_negacao_de_remoto_nao_vira_remoto():
    from jobapplier.vocabulario import modalidade_em

    assert modalidade_em(ADYEN) == "Presencial"


@pytest.mark.parametrize("texto", [
    "Não oferecemos trabalho remoto",
    "We do not offer remote work",
    "This is not a remote position",
    "Sem opção de home office",
])
def test_varias_formas_de_negar(texto):
    from jobapplier.vocabulario import modalidade_em

    assert modalidade_em(texto) != "Remoto", texto


def test_negacao_morre_na_fronteira_da_oracao():
    """"não oferecemos remoto; atuação presencial" tinha os dois termos negados
    pela mesma negação, e a vaga virava Desconhecida justamente quando o anúncio
    era o mais explícito possível."""
    from jobapplier.vocabulario import modalidade_em

    assert modalidade_em("Não oferecemos remoto; atuação presencial") == "Presencial"
    assert modalidade_em("Não oferecemos remoto. Atuação presencial") == "Presencial"


def test_remoto_afirmado_continua_remoto():
    """A correção não pode deixar de reconhecer vaga remota de verdade."""
    from jobapplier.vocabulario import modalidade_em

    assert modalidade_em("Vaga 100% remota para todo o Brasil") == "Remoto"
    assert modalidade_em("Fully remote position") == "Remoto"


def test_hibrido_vence_remoto():
    """Anúncio híbrido quase sempre cita "remoto" também. Com Remoto testado
    primeiro, toda vaga híbrida virava remota."""
    from jobapplier.vocabulario import modalidade_em

    assert modalidade_em("Modelo híbrido, 2 dias remotos por semana") == "Híbrido"
    assert modalidade_em("Hybrid role with remote flexibility") == "Híbrido"


def test_dias_no_escritorio_e_hibrido():
    """Descreve híbrido sem usar a palavra — é como a Adyen de São Paulo escreve."""
    from jobapplier.vocabulario import modalidade_em

    assert modalidade_em("based out of our São Paulo office (3 days in person)") == "Híbrido"
    assert modalidade_em("2 dias no escritório por semana") == "Híbrido"


@pytest.mark.parametrize("texto,esperado", [
    ("Experiência com hybrid cloud e migração para nuvem", "Desconhecida"),
    ("Arquitetura de nuvem híbrida com Azure e on-premises", "Desconhecida"),
    ("Trabalho híbrido: 3 dias no escritório", "Híbrido"),
    ("Hybrid workplace, 2 days a week in the office", "Híbrido"),
])
def test_hibrido_de_arquitetura_nao_e_modalidade(texto, esperado):
    """"hybrid cloud" é arquitetura. Medido antes de decidir: em 1.684 anúncios
    com "híbrido/hybrid", o que segue é workplace, working, schedule e role —
    arquitetura nem entra nos dezesseis mais comuns. Por isso a lista de exclusão
    é curta: alargá-la descartaria vaga híbrida de verdade."""
    from jobapplier.vocabulario import modalidade_em

    assert modalidade_em(texto) == esperado


# ── cargos_alvo não pode ter termo largo ──────────────────────────────────────
# `cargos_alvo` tinha o termo solto "Analytics". Ele casava com "Marketing
# Strategy and Analytics Manager", "People Analytics Specialist", "Senior
# Software Engineer; Analytics Compute" e "Analytics Lead" — quatro cargos que
# não são o dele, todos acima de 85, todos candidatos a envio automático.
#
# O score não tinha culpa: ele não pontua cargo, e nem deveria precisar. O 4A é
# o portão, e o portão estava aberto. Estes testes usam a config REAL, então
# falham no dia em que alguém reabrir.

def _config_real():
    from jobapplier.config.manager import ConfigManager

    return ConfigManager().get("coleta") or {}


@pytest.mark.parametrize("titulo", [
    "Marketing Strategy and Analytics Manager",
    "People Analytics Specialist",
    "Senior People Analytics Analyst",
    "Senior Software Engineer; Analytics Compute Platform",
    "Analytics Lead, Strategic Insights (Compliance)",
    "Senior Revenue Analytics Analyst",
    "Treasury Finance AI and Quantitative Analytics",
    "Auxiliar Administrativo de Crédito e Recuperação",
])
@pytest.mark.pessoal
def test_cargo_alheio_nao_passa_no_4a(titulo):
    passou, _ = pre_filter.apply(
        VagaFake(titulo=titulo, localizacao="São Paulo, Brasil"), _config_real())
    assert not passou, f"{titulo!r} não é o cargo dele e passou no 4A"


@pytest.mark.parametrize("titulo", [
    # Forma feminina e neutra: o mercado brasileiro escreve assim, e a lista só
    # tinha "Engenheiro de Dados". Eram 17 títulos no acervo com "Engenheira de
    # Dados" e sem a forma masculina — o cargo dele, perdido por concordância.
    "Pessoa Engenheira de Dados Sênior",
    "Engenheira de Dados (Martech)",
    "Cientista de Dados Pleno",
    # E as formas que já funcionavam não podem ter quebrado no aperto.
    "Analytics Engineer",
    "Engenheiro de Dados Pleno",
    "Analista de BI Sênior",
    "Data Engineer",
    "Coordenador de Dados",
])
def test_cargo_dele_continua_passando(titulo):
    passou, motivo = pre_filter.apply(
        VagaFake(titulo=titulo, localizacao="São Paulo, Brasil"), _config_real())
    assert passou, f"{titulo!r} é o cargo dele e foi barrado: {motivo}"


def test_nenhum_cargo_alvo_e_curto_demais():
    """Termo de uma palavra genérica casa com qualquer coisa. "Analytics" custou
    cinco falsos positivos acima de 85; a regra impede o próximo."""
    largos = {"analytics", "analítico", "analitico", "dados", "data", "bi",
              "engenheiro", "analista", "especialista", "coordenador"}
    encontrados = [c for c in _config_real().get("cargos_alvo", [])
                   if c.lower() in largos]
    assert not encontrados, f"termo largo demais em cargos_alvo: {encontrados}"


# ── Vaga afirmativa: elegibilidade é fato, não inferência ─────────────────────
# 136 vagas do acervo são afirmativas — 119 PCD, 13 mulheres, 4 pessoas negras.
# Cinco chegaram vivas à fila e uma foi **aprovada com score 84**. O score não
# tem como pegar: mede aderência técnica, e a barreira aqui não é técnica.

AFIRMATIVAS = {
    "Data Engineer Senior - Vaga afirmativa para mulheres": "mulheres",
    "Payments Performance Analyst - Affirmative Action for Women": "mulheres",
    "Analista de Dados Sênior | Afirmativa PCD": "pcd",
    "Business Analytics Junior | Vaga Afirmativa para Pessoas com Deficiência": "pcd",
    "Analista de BI | Vaga exclusiva para pessoas negras": "pessoas_negras",
}


@pytest.mark.parametrize("titulo,grupo", list(AFIRMATIVAS.items()))
def test_identifica_o_grupo_da_vaga(titulo, grupo):
    from jobapplier.elegibilidade import programa_afirmativo

    assert programa_afirmativo(titulo) == grupo


@pytest.mark.parametrize("titulo", [
    "Engenheiro de Dados Pleno",
    "Data Engineer — we value diversity and inclusion",
    "Analista de Dados | Ambiente diverso e inclusivo",
])
def test_texto_institucional_nao_e_vaga_afirmativa(titulo):
    """"diversidade" e "inclusão" aparecem no rodapé de metade dos anúncios e
    não reservam nada. Tratá-los como reserva descartaria vaga aberta."""
    from jobapplier.elegibilidade import programa_afirmativo

    assert programa_afirmativo(titulo) is None


def test_afirmativa_sem_grupo_nomeado():
    from jobapplier.elegibilidade import programa_afirmativo

    assert programa_afirmativo("Analista de BI | Vaga afirmativa") == "indeterminado"


def test_caixa_e_acento_nao_atrapalham():
    """`_sem_acento` preserva a caixa. Sem o `.lower()`, "Afirmativa PCD" e
    "Affirmative Action" não casavam — três dos quatro títulos reais passavam."""
    from jobapplier.elegibilidade import programa_afirmativo

    assert programa_afirmativo("AFIRMATIVA PCD") == "pcd"
    assert programa_afirmativo("Vaga Afirmativa para Mulheres") == "mulheres"


# ── A declaração é do candidato ───────────────────────────────────────────────

def test_sem_declaracao_nao_e_elegivel():
    """Ausência de declaração é "não", nunca "talvez": a vaga é reservada."""
    from jobapplier.elegibilidade import elegivel_ao_programa

    assert elegivel_ao_programa("pcd", {}) is False
    assert elegivel_ao_programa("pcd", None) is False


def test_declarando_o_grupo_fica_elegivel():
    """Um candidato PCD tem 119 vagas no acervo feitas para ele. Escondê-las em
    silêncio seria tão errado quanto mandar candidatura indevida."""
    from jobapplier.elegibilidade import elegivel_ao_programa

    perfil = {"programas_afirmativos": ["pcd"]}
    assert elegivel_ao_programa("pcd", perfil) is True
    assert elegivel_ao_programa("mulheres", perfil) is False


def test_grupo_indeterminado_nao_passa_nem_declarando_outro():
    from jobapplier.elegibilidade import elegivel_ao_programa

    assert elegivel_ao_programa("indeterminado", {"programas_afirmativos": ["pcd"]}) is False


def test_vaga_normal_nao_e_afetada():
    from jobapplier.elegibilidade import elegivel_ao_programa

    assert elegivel_ao_programa(None, {}) is True


# ── Contrato com o 4A ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("titulo", list(AFIRMATIVAS))
def test_4a_barra_afirmativa_nao_declarada(titulo):
    """`cargos_alvo` largo de propósito: sem isso o título é barrado antes, pelo
    cargo, e o teste passaria sem nunca exercitar a regra que quer provar."""
    passou, motivo = pre_filter.apply(
        VagaFake(titulo=titulo, localizacao="São Paulo, Brasil"),
        {**CFG, "cargos_alvo": ["Data", "Analista", "Analyst", "Business",
                                "Analytics"]})
    assert not passou
    assert "afirmativa" in motivo


def test_motivo_ensina_a_declarar():
    """Descarte silencioso esconderia de um candidato elegível as vagas feitas
    para ele. O motivo tem de dizer onde declarar."""
    _, motivo = pre_filter.apply(
        VagaFake(titulo="Analista de Dados | Afirmativa PCD",
                 localizacao="São Paulo, Brasil"), CFG)
    assert "programas_afirmativos" in motivo


def test_4a_deixa_passar_quando_declarado():
    cfg = {**CFG, "dados_pessoais": {"programas_afirmativos": ["pcd"]}}
    passou, motivo = pre_filter.apply(
        VagaFake(titulo="Analista de Dados | Afirmativa PCD",
                 localizacao="São Paulo, Brasil"), cfg)
    assert passou, motivo
