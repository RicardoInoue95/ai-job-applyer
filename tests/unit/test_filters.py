"""Testes dos Módulos 4A e 4B — filtros pré e pós-normalização.

São funções puras e decidem se uma vaga custa uma chamada Gemini ou não. Um
falso negativo aqui descarta silenciosamente vaga boa; um falso positivo gasta
token. Estavam sem cobertura nenhuma.
"""
from filters import post_filter, pre_filter


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
