"""Vínculo candidatura ↔ vaga: quem manda quando as fontes discordam.

A URL do formulário da Gupy não carrega o `jobId` — medido na página real, sem
`__NEXT_DATA__` e sem link. O vínculo é o que faz voltar por e-mail funcionar, e
errar aqui preenche o formulário de uma vaga com as respostas de outra.
"""
import pytest

from jobapplier import api
from jobapplier.database.connection import get_session
from jobapplier.database.models import VinculoCandidatura

pytestmark = pytest.mark.db

URL = "https://pagseguro.gupy.io/candidates/applications/999000111/steps/1/x"


@pytest.fixture(autouse=True)
def limpar():
    def _apagar():
        with get_session() as s:
            (s.query(VinculoCandidatura)
             .filter_by(referencia="999000111").delete(synchronize_session=False))
    _apagar()
    yield
    _apagar()


def _gravar(vaga_id, origem):
    with get_session() as s:
        api._gravar_vinculo(s, URL, vaga_id, origem)


def _lido():
    with get_session() as s:
        v = s.query(VinculoCandidatura).filter_by(referencia="999000111").one_or_none()
        return (v.vaga_id, v.origem) if v else None


def test_primeiro_encontro_grava():
    _gravar(13052, "referrer")
    assert _lido() == (13052, "referrer")


def test_inferencia_nao_sobrescreve_inferencia():
    """Duas inferências discordando: a primeira vale. Deixar a última ganhar
    faria o vínculo oscilar a cada visita, e o formulário seria preenchido com
    vagas diferentes em dias diferentes."""
    _gravar(13052, "referrer")
    _gravar(11655, "aba")
    assert _lido() == (13052, "referrer")


def test_sua_escolha_corrige_a_inferencia():
    """Você viu a tela; a inferência não."""
    _gravar(11655, "aba")
    _gravar(13052, "voce")
    assert _lido() == (13052, "voce")


def test_inferencia_nunca_sobrescreve_sua_escolha():
    """O caso que mais importa: depois de você desempatar, nenhuma heurística
    pode desfazer — senão a próxima visita reabriria a dúvida já resolvida."""
    _gravar(13052, "voce")
    _gravar(11655, "referrer")
    _gravar(11655, "aba")
    assert _lido() == (13052, "voce")


def test_url_sem_id_de_candidatura_nao_grava_nada():
    with get_session() as s:
        api._gravar_vinculo(s, "https://pagseguro.gupy.io/job/abc", 13052, "voce")
    assert _lido() is None
