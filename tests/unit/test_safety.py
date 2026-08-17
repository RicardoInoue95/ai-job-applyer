"""Testes do Módulo 9 — Controle de Risco.

Cobre só as partes puras (resolução de limite, parsing de delay). As que tocam o
banco — checar_limite, ja_candidatado, liberar_orfaos — ficam para os testes de
integração, que exigem Postgres.
"""
import pytest

from safety import guard

# ── limite_diario ─────────────────────────────────────────────────────────────

def test_limite_padrao_por_plataforma():
    assert guard.limite_diario("linkedin") == 10
    assert guard.limite_diario("gupy") == 15
    assert guard.limite_diario("greenhouse") == 20
    assert guard.limite_diario("lever") == 20


def test_linkedin_tem_limite_mais_restritivo():
    # Invariante de produto: LinkedIn é a plataforma com detecção ativa e a
    # conta é a identidade profissional real do usuário.
    linkedin = guard.limite_diario("linkedin")
    for outra in ("gupy", "greenhouse", "lever"):
        assert linkedin < guard.limite_diario(outra)


def test_plataforma_desconhecida_usa_limite_generico():
    assert guard.limite_diario("indeed") == guard.DEFAULT_LIMITE


def test_limite_case_insensitive():
    assert guard.limite_diario("LinkedIn") == guard.limite_diario("linkedin")


def test_limite_none_nao_estoura():
    assert guard.limite_diario(None) == guard.DEFAULT_LIMITE


def test_config_sobrescreve_padrao():
    cfg = {"risco": {"limites_diarios": {"linkedin": 3}}}
    assert guard.limite_diario("linkedin", cfg) == 3


def test_config_aceita_limite_como_string():
    cfg = {"risco": {"limites_diarios": {"linkedin": "5"}}}
    assert guard.limite_diario("linkedin", cfg) == 5


def test_config_invalida_cai_no_padrao():
    cfg = {"risco": {"limites_diarios": {"linkedin": "não é número"}}}
    assert guard.limite_diario("linkedin", cfg) == 10


def test_config_vazia_ou_ausente():
    assert guard.limite_diario("linkedin", {}) == 10
    assert guard.limite_diario("linkedin", {"risco": None}) == 10
    assert guard.limite_diario("linkedin", None) == 10


def test_limite_zero_e_respeitado():
    # Zero deve desabilitar a plataforma, não cair no padrão.
    cfg = {"risco": {"limites_diarios": {"linkedin": 0}}}
    assert guard.limite_diario("linkedin", cfg) == 0


# ── espera_humana ─────────────────────────────────────────────────────────────

@pytest.fixture
def sem_sono(monkeypatch):
    """Substitui time.sleep para os testes não dormirem de verdade."""
    dormido = []
    monkeypatch.setattr(guard.time, "sleep", lambda s: dormido.append(s))
    return dormido


def test_espera_usa_faixa_padrao(sem_sono):
    segundos = guard.espera_humana()
    assert guard.DEFAULT_DELAY_MIN <= segundos <= guard.DEFAULT_DELAY_MAX
    assert sem_sono == [segundos]


def test_espera_respeita_faixa_da_config(sem_sono):
    cfg = {"risco": {"delay_min": 1, "delay_max": 2}}
    for _ in range(20):
        assert 1 <= guard.espera_humana(cfg) <= 2


def test_espera_corrige_faixa_invertida(sem_sono):
    cfg = {"risco": {"delay_min": 90, "delay_max": 10}}
    assert 10 <= guard.espera_humana(cfg) <= 90


def test_espera_config_nao_numerica_cai_no_padrao(sem_sono):
    cfg = {"risco": {"delay_min": "abc", "delay_max": None}}
    segundos = guard.espera_humana(cfg)
    assert guard.DEFAULT_DELAY_MIN <= segundos <= guard.DEFAULT_DELAY_MAX


def test_espera_faixa_fixa(sem_sono):
    cfg = {"risco": {"delay_min": 7, "delay_max": 7}}
    assert guard.espera_humana(cfg) == 7


# ── humanizar ─────────────────────────────────────────────────────────────────

def test_humanizar_nunca_propaga_excecao():
    """Jitter é best effort — não pode derrubar uma candidatura."""
    class PaginaQuebrada:
        @property
        def mouse(self):
            raise RuntimeError("browser fechou")

    guard.humanizar(PaginaQuebrada())  # não deve levantar


def test_humanizar_move_mouse_e_scrolla():
    chamadas = []

    class MouseFake:
        def move(self, x, y, steps=None):
            chamadas.append(("move", x, y))

        def wheel(self, dx, dy):
            chamadas.append(("wheel", dx, dy))

    class PaginaFake:
        mouse = MouseFake()

        def wait_for_timeout(self, ms):
            chamadas.append(("wait", ms))

    guard.humanizar(PaginaFake())

    moves = [c for c in chamadas if c[0] == "move"]
    wheels = [c for c in chamadas if c[0] == "wheel"]
    assert len(moves) >= 2
    assert len(wheels) == 1
    # Coordenadas dentro da viewport declarada
    assert all(0 < x < 1280 and 0 < y < 800 for _, x, y in moves)


# ── constantes de segurança ───────────────────────────────────────────────────

def test_disjuntor_maior_que_limite_normal():
    assert guard.FATOR_DISJUNTOR > 1


def test_erros_nao_contam_no_limite_principal():
    # Uma falha de pré-validação (CPF ausente, link inválido) nunca toca a
    # plataforma. Se contasse, queimaria a cota diária sem enviar nada.
    assert "erro" not in guard.STATUS_CONTATO_REAL
    assert "enviada" in guard.STATUS_CONTATO_REAL
    assert "perguntas_pendentes" in guard.STATUS_CONTATO_REAL
