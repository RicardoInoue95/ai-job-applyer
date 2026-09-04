"""Banco de respostas aprendidas: onde pode repetir, e onde repetir seria chute.

A memória existe para matar tédio: sem ela, "nome da mãe" é redigitado nas 230
vagas da Gupy. Mas repetir resposta **específica de contexto** em outro contexto
seria o mesmo erro que a invariante 3 proíbe, com outra roupa. A classe da
pergunta é o que separa os dois casos, e é isto que estes testes guardam.
"""
import pytest

from jobapplier import aprendizado
from jobapplier.agents.respostas import Classe

# ── Escopo: sobre você, ou sobre a empresa? ───────────────────────────────────

@pytest.mark.parametrize("classe", [
    Classe.FATO, Classe.PREFERENCIA, Classe.FERRAMENTA,
    Classe.DOMINIO, Classe.TEMPO, Classe.CONSENTIMENTO, Classe.SENSIVEL,
])
def test_resposta_sobre_voce_vale_em_qualquer_empresa(classe):
    """Seu RG não muda de empresa para empresa. Nem seu inglês."""
    assert aprendizado.escopo_de(classe) == "global"


def test_pergunta_aberta_nao_atravessa_empresa():
    """"Por que a PagBank?" não responde "por que o Nubank?". Resposta genérica
    reaproveitada é o que faz recrutador descartar — e vaga marginal enviada
    queima a empresa para a vaga certa depois."""
    assert aprendizado.escopo_de(Classe.ABERTA) == "empresa"


# ── Neutralização da empresa ─────────────────────────────────────────────────

def test_nome_da_empresa_vira_marcador():
    """"Você trabalha na empresa X?" aparece em toda Gupy mudando só o nome. Uma
    resposta cobre as 230 em vez de 230 respostas iguais."""
    pag = aprendizado.normalizar("Você trabalha na empresa PagBank?", "PagBank")
    nub = aprendizado.normalizar("Você trabalha na empresa Nubank?", "Nubank")
    assert pag == nub
    assert aprendizado.MARCADOR_EMPRESA in pag


def test_aberta_nao_neutraliza_a_empresa():
    """Em pergunta aberta o nome da empresa é o assunto, não ruído. Neutralizar
    faria a carta escrita para a PagBank ser oferecida ao Nubank."""
    _, escopo, empresa = aprendizado.chave(
        "Por que você quer trabalhar na PagBank?", "PagBank", Classe.ABERTA)
    assert escopo == "empresa"
    assert empresa == "pagbank"
    chave_pag, _, _ = aprendizado.chave(
        "Por que você quer trabalhar na PagBank?", "PagBank", Classe.ABERTA)
    chave_nub, _, _ = aprendizado.chave(
        "Por que você quer trabalhar no Nubank?", "Nubank", Classe.ABERTA)
    assert chave_pag != chave_nub


# ── Normalização: exata, nunca aproximada ────────────────────────────────────

def test_numeracao_e_asterisco_da_gupy_saem_da_chave():
    """A Gupy numera: "6. Pretensão Salarial *". A numeração muda com a ordem
    das perguntas, então mantê-la faria a mesma pergunta virar duas entradas."""
    assert (aprendizado.normalizar("6. Nome da mãe *")
            == aprendizado.normalizar("Nome da mãe"))
    assert aprendizado.normalizar("2) Nome da mãe") == aprendizado.normalizar("Nome da mãe")


def test_perguntas_parecidas_nao_se_confundem():
    """Casamento é exato sobre a forma normalizada. "Python" e "Python 3" são
    perguntas diferentes, e um casamento frouxo responderia uma com a outra."""
    a = aprendizado.normalizar("Tem experiência com Python?")
    b = aprendizado.normalizar("Tem experiência com Python 3?")
    assert a != b


def test_acento_e_caixa_nao_criam_entrada_nova():
    assert (aprendizado.normalizar("NOME DA MÃE")
            == aprendizado.normalizar("nome da mae"))
