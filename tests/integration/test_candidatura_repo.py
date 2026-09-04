"""Modo sombra não pode impedir a candidatura real depois.

`uq_candidaturas_vaga_ciclo` existe de propósito: idempotência garantida pelo
banco, não por checagem em código. Mas a gravação era sempre `INSERT`, e o modo
sombra — que é o padrão, e que o projeto manda rodar "por algumas semanas" antes
de ligar o envio — grava uma candidatura `simulada`.

Resultado: passadas essas semanas, toda vaga tocada em sombra ficava impossível
de candidatar de verdade. O `INSERT` batia na constraint, a vaga virava `erro`, e
o tratamento de erro tentava inserir *outra* candidatura na mesma chave — falha
dupla, com a exceção original perdida atrás do IntegrityError. Havia 60 vagas
nesse estado quando isto foi descoberto, tentando enviar a primeira candidatura
de verdade.

Precisa de Postgres: a constraint é do banco, e um fake não a teria.
"""
import pytest
from sqlalchemy.exc import IntegrityError

from jobapplier.database.connection import get_session
from jobapplier.database.models import Candidatura
from jobapplier.database.repository import CandidaturaRepository

pytestmark = pytest.mark.db

#: Fora de qualquer faixa real de id de vaga, para não colidir com dado vivo.
VAGA_TESTE = 999_999_001


@pytest.fixture
def limpar():
    def _apagar():
        with get_session() as s:
            s.query(Candidatura).filter(
                Candidatura.vaga_id == VAGA_TESTE).delete()
    _apagar()
    yield
    _apagar()


def _registrar(**campos):
    with get_session() as s:
        CandidaturaRepository(s).registrar(vaga_id=VAGA_TESTE, **campos)


def _ler():
    with get_session() as s:
        linhas = s.query(Candidatura).filter(
            Candidatura.vaga_id == VAGA_TESTE).all()
        for linha in linhas:
            s.expunge(linha)
        return linhas


def test_sombra_depois_envio_real_nao_quebra(limpar):
    """O caso exato que quebrou: simulada em 18/08, envio real hoje."""
    _registrar(status="simulada", perfil_base="bi_analyst")
    _registrar(status="enviada", perfil_base="bi_analyst",
               curriculo_path="/tmp/cv.pdf")

    linhas = _ler()
    assert len(linhas) == 1, "a tentativa é a mesma, não duas"
    assert linhas[0].status == "enviada"
    assert linhas[0].curriculo_path == "/tmp/cv.pdf"


def test_registrar_duas_vezes_nao_duplica(limpar):
    for _ in range(3):
        _registrar(status="erro", erro="falhou")
    assert len(_ler()) == 1


def test_campos_nao_informados_sobrevivem_a_atualizacao(limpar):
    """Gravar um erro depois não pode apagar o currículo já produzido — é a
    evidência de que o dossiê existia."""
    _registrar(status="simulada", curriculo_path="/tmp/cv.pdf",
               perfil_base="data_engineer")
    _registrar(status="erro", erro="seletor mudou")

    linha = _ler()[0]
    assert linha.status == "erro"
    assert linha.curriculo_path == "/tmp/cv.pdf"
    assert linha.perfil_base == "data_engineer"


def test_ciclo_novo_e_registro_novo(limpar):
    """Recandidatura deliberada continua sendo outra linha — é o que `ciclo`
    significa, e a constraint segue valendo para o par."""
    _registrar(status="enviada", ciclo=1)
    _registrar(status="enviada", ciclo=2)
    assert {c.ciclo for c in _ler()} == {1, 2}


def test_a_constraint_continua_existindo(limpar):
    """Se alguém a remover para 'resolver' duplicidade, a garantia de
    idempotência sai do banco e volta para o código — que é o que a constraint
    existe para evitar. Este teste falha nesse dia."""
    with get_session() as s:
        s.add(Candidatura(vaga_id=VAGA_TESTE, ciclo=1, status="enviada"))

    with pytest.raises(IntegrityError), get_session() as s:
        s.add(Candidatura(vaga_id=VAGA_TESTE, ciclo=1, status="enviada"))
