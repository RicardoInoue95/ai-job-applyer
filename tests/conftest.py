"""Isolamento de ambiente para toda a suíte.

Dois defeitos reais que este arquivo corrige.

**Dependência de ordem.** `config.secrets.carregar_env()` lê o `.env` uma vez e
guarda o resultado num global. Um teste que faz `monkeypatch.delenv` numa chave de
provedor funcionava apenas se algum teste anterior já tivesse disparado o
carregamento: rodando o arquivo isolado, o `delenv` acontecia primeiro e o
`carregar_env` seguinte repopulava a variável a partir do disco. Resultado: dois
testes passavam na suíte completa e falhavam sozinhos.

**Vazamento de segredo.** Como os testes liam o `.env` do desenvolvedor, o
assert que falhava imprimia a chave de API real na saída do pytest — que vai para
terminal, log de CI e transcript. Viola o invariante 11 (segredo nunca em log).

A correção fecha os dois: marca o ambiente como já carregado, para que nenhum
teste releia o disco, e remove as chaves de provedor. Quem precisa de chave a
define explicitamente com monkeypatch.
"""
import pytest

from jobapplier.config import secrets


@pytest.fixture(autouse=True, scope="session")
def _ambiente_isolado():
    """Impede a suíte de ler o .env real. Autouse: vale para todos os testes."""
    # Marca como carregado ANTES de qualquer teste, para que `_garantir_env()`
    # nunca releia o disco no meio de um teste que mexeu em os.environ.
    secrets._env_carregado = True
    yield


@pytest.fixture(autouse=True)
def _sem_chaves_de_provedor(monkeypatch):
    """Baseline sem chave de API. Teste que precisa de uma, define a sua.

    Vale para todo teste, não só os de LLM: um teste de PDF ou de coletor não
    deve nem poder alcançar a chave real, muito menos imprimi-la ao falhar.
    """
    from jobapplier.llm import PROVEDORES

    for classe in PROVEDORES.values():
        monkeypatch.delenv(f"AIJOB_{classe.env_chave}", raising=False)
    monkeypatch.delenv("AIJOB_LLM_PROVEDOR", raising=False)
    monkeypatch.delenv("AIJOB_LLM_MODELO", raising=False)
