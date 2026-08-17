"""Elegibilidade geográfica: descartar cedo só o comprovadamente inelegível.

O critério de sucesso não é quantas vagas o filtro elimina. É eliminar cedo
apenas as que são de fato inviáveis, preservando as brasileiras e as
internacionais que aceitam Brasil. Falso negativo aqui é caro e silencioso: a
vaga some sem deixar rastro.
"""
import pytest

from jobapplier.elegibilidade import (
    Elegibilidade,
    avaliar_normalizado,
    avaliar_texto,
)

#: Candidato brasileiro, sem autorização de trabalho nos EUA.
PERFIL = {"pais_residencia": "BR", "paises_autorizados": ["BR"]}

#: Candidato com dupla autorização.
PERFIL_COM_US = {"pais_residencia": "BR", "paises_autorizados": ["BR", "US"]}


# ── 4A: sinais explícitos DESCARTAM ───────────────────────────────────────────

@pytest.mark.parametrize("texto", [
    "Candidates must be authorized to work in the United States.",
    "Must be legally authorized to work in the US without sponsorship.",
    "US work authorization is required for this role.",
    "US citizens or permanent residents only.",
    "Security clearance required.",
    "This role is only available to candidates in the United States.",
    "US residents only. Remote within the US.",
    "Must reside in Canada.",
    "US-based candidates only.",
])
def test_sinal_explicito_torna_inelegivel(texto):
    a = avaliar_texto(texto, PERFIL)
    assert a.estado is Elegibilidade.INELEGIVEL, texto
    assert a.descarta
    assert a.evidencias


# ── 4A: sinais fracos NÃO descartam ───────────────────────────────────────────

@pytest.mark.parametrize("texto", [
    "Our headquarters are in San Francisco, United States.",
    "Salary range: $120,000 - $180,000 USD.",
    "This is a remote position.",
    "We have offices in New York, London and São Paulo.",
    "Do you require sponsorship? (optional)",
    "Join our team in Austin, Texas.",
    "The role reports to the US-based engineering manager.",
])
def test_sinal_fraco_nao_descarta(texto):
    """Menção a EUA, dólar, cidade americana ou 'remote' isolados produziriam
    falso negativo. Nenhum deles é linguagem de exigência."""
    a = avaliar_texto(texto, PERFIL)
    assert not a.descarta, texto


def test_texto_vazio_nao_descarta():
    assert avaliar_texto("", PERFIL).estado is Elegibilidade.NAO_ESPECIFICADA
    assert avaliar_texto(None, PERFIL).estado is Elegibilidade.NAO_ESPECIFICADA


# ── Contra-sinais preservam vagas boas ────────────────────────────────────────

@pytest.mark.parametrize("texto", [
    "Remote position open to candidates in Brazil.",
    "We hire across LATAM.",
    "Work from anywhere in the world.",
    "Contratação via PJ ou CLT.",
    "Vaga remota para toda a América Latina.",
])
def test_mencao_a_brasil_ou_latam_preserva(texto):
    a = avaliar_texto(texto, PERFIL)
    assert a.estado is Elegibilidade.ELEGIVEL, texto
    assert not a.descarta


def test_contra_sinal_vence_linguagem_de_autorizacao():
    """Vaga global costuma repetir cláusula de autorização por país."""
    texto = (
        "Remote across LATAM including Brazil. "
        "For US-based hires, candidates must be authorized to work in the United States."
    )
    assert not avaliar_texto(texto, PERFIL).descarta


# ── Sponsorship depende do FATO do candidato, não da vaga ─────────────────────

def test_sem_sponsorship_descarta_quem_precisaria():
    texto = "We are unable to sponsor visas for this position."
    assert avaliar_texto(texto, PERFIL).descarta


def test_sem_sponsorship_nao_afeta_quem_ja_tem_autorizacao():
    """Autorização é fato do candidato; não deve ser inferida de endereço."""
    texto = "We are unable to sponsor visas for this position."
    a = avaliar_texto(texto, PERFIL_COM_US)
    assert not a.descarta
    assert a.categoria == "sponsorship_desnecessario"


# ── 4B: decisão estruturada ───────────────────────────────────────────────────

def test_pais_do_candidato_na_lista_de_aceitos():
    n = {"eligible_residence_countries": ["BR", "AR", "MX"]}
    assert avaliar_normalizado(n, PERFIL).estado is Elegibilidade.ELEGIVEL


def test_pais_do_candidato_fora_da_lista():
    n = {"eligible_residence_countries": ["US", "CA"]}
    a = avaliar_normalizado(n, PERFIL)
    assert a.estado is Elegibilidade.INELEGIVEL
    assert a.descarta


def test_exige_autorizacao_sem_sponsorship_e_inelegivel():
    n = {"work_authorization_required": True, "work_location_country": ["US"],
         "sponsorship_available": False}
    assert avaliar_normalizado(n, PERFIL).descarta


def test_exige_autorizacao_mas_oferece_sponsorship_e_incerta():
    """INCERTA segue para análise. Descartar seria falso negativo."""
    n = {"work_authorization_required": True, "work_location_country": ["US"],
         "sponsorship_available": True}
    a = avaliar_normalizado(n, PERFIL)
    assert a.estado is Elegibilidade.INCERTA
    assert not a.descarta


def test_autorizacao_que_o_candidato_ja_tem_nao_bloqueia():
    n = {"work_authorization_required": True, "work_location_country": ["US"]}
    assert not avaliar_normalizado(n, PERFIL_COM_US).descarta


def test_normalizado_sem_campos_geograficos():
    assert avaliar_normalizado({}, PERFIL).estado is Elegibilidade.NAO_ESPECIFICADA


def test_apenas_inelegivel_descarta():
    """Contrato do módulo: os outros três estados nunca eliminam a vaga."""
    for estado in Elegibilidade:
        from jobapplier.elegibilidade import Avaliacao

        assert Avaliacao(estado).descarta == (estado is Elegibilidade.INELEGIVEL)


def test_avaliacao_serializa_com_evidencia():
    a = avaliar_texto("US residents only.", PERFIL)
    j = a.para_json()
    assert j["geographic_eligibility"] == "ineligible"
    assert j["eligibility_evidence"]
    assert j["eligibility_category"]


# ── Integração com os filtros ─────────────────────────────────────────────────

def test_4a_descarta_vaga_us_only():
    import types

    from jobapplier.filters import pre_filter

    vaga = types.SimpleNamespace(
        titulo="Data Engineer", localizacao="Remote",
        descricao="Must be legally authorized to work in the United States.",
    )
    passou, motivo = pre_filter.apply(
        vaga, {"cargos_alvo": ["Data Engineer"], "dados_pessoais": PERFIL}
    )
    assert not passou
    assert "inelegível geograficamente" in motivo


def test_4a_preserva_vaga_brasileira():
    import types

    from jobapplier.filters import pre_filter

    vaga = types.SimpleNamespace(
        titulo="Data Engineer", localizacao="São Paulo, Brasil",
        descricao="Vaga híbrida em São Paulo. Contratação CLT.",
    )
    passou, _ = pre_filter.apply(
        vaga, {"cargos_alvo": ["Data Engineer"], "dados_pessoais": PERFIL}
    )
    assert passou


def test_4b_descarta_por_paises_aceitos():
    from jobapplier.filters import post_filter

    passou, motivo = post_filter.apply(
        {"eligible_residence_countries": ["US"]}, {"dados_pessoais": PERFIL}
    )
    assert not passou
    assert "inelegível geograficamente" in motivo


def test_4b_sem_perfil_configurado_nao_estoura():
    from jobapplier.filters import post_filter

    passou, _ = post_filter.apply({"tecnologias": ["Python"]}, {})
    assert passou
