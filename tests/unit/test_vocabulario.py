

# ── Equivalências que a vaga pede ─────────────────────────────────────────────

def test_so_entra_o_que_a_vaga_pede_e_ele_nao_tem():
    from jobapplier.vocabulario import equivalencias_uteis

    r = equivalencias_uteis(["AWS", "Python", "Tableau"], ["Azure", "Python", "Power BI"])
    assert r == ["AWS", "Tableau"], "Python ele tem — não é ponte"


def test_sem_equivalente_nao_entra():
    """Tecnologia que ele não tem e não tem parecida vira lacuna, não ponte."""
    from jobapplier.vocabulario import equivalencias_uteis

    assert equivalencias_uteis(["Kubernetes"], ["Power BI"]) == []


def test_nao_repete():
    from jobapplier.vocabulario import equivalencias_uteis

    assert equivalencias_uteis(["AWS", "aws", "AWS"], ["Azure"]) == ["AWS"]


def test_entradas_vazias():
    from jobapplier.vocabulario import equivalencias_uteis

    assert equivalencias_uteis([], ["Azure"]) == []
    assert equivalencias_uteis(["AWS"], []) == []
    assert equivalencias_uteis(None, None) == []
