"""Todo módulo do pacote deve importar sem efeito colateral.

Existe por causa de uma quebra real: um import de `pathlib.Path` foi removido de
`applicators/linkedin.py` enquanto `Path` seguia em uso nas anotações. A suíte
inteira passou verde, porque nenhum teste importava aquele módulo — o applicator
do LinkedIn só é carregado em tempo de execução, dentro de `run_applications`.

Este teste enumera os módulos em vez de listá-los à mão, então cobre também
qualquer arquivo novo, sem ninguém precisar lembrar de atualizá-lo.

Importar não deve abrir conexão de banco, chamar rede nem iniciar browser. Se
adicionar um módulo que quebre isso, o efeito colateral é o bug — não o teste.
"""
import importlib
import pkgutil

import pytest

import jobapplier

#: Não têm import próprio — são configuração do Alembic, executada por ele.
IGNORAR = ("jobapplier.database.migrations",)


def _modulos() -> list[str]:
    nomes = []
    for info in pkgutil.walk_packages(jobapplier.__path__, prefix="jobapplier."):
        if any(info.name.startswith(p) for p in IGNORAR):
            continue
        nomes.append(info.name)
    return sorted(nomes)


MODULOS = _modulos()


def test_encontrou_modulos():
    # Guarda contra o teste passar por não ter descoberto nada.
    assert len(MODULOS) > 20, MODULOS


@pytest.mark.parametrize("nome", MODULOS)
def test_modulo_importa(nome):
    importlib.import_module(nome)


def test_pacotes_esperados_existem():
    """Contrato de estrutura: renomear ou mover um subpacote deve ser deliberado."""
    esperados = {
        "agents", "applicators", "collectors", "config", "database",
        "filters", "generators", "llm", "notifications", "paths",
        "resume_parser", "safety", "orchestrator",
    }
    encontrados = {info.name for info in pkgutil.iter_modules(jobapplier.__path__)}
    faltando = esperados - encontrados
    assert not faltando, f"subpacotes ausentes: {faltando}"


def test_llm_nao_esta_dentro_de_agents():
    """A abstração de provedor é infraestrutura, não agente.

    Ficava em agents/llm; foi promovida a jobapplier/llm.
    """
    import jobapplier.llm  # noqa: F401

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("jobapplier.agents.llm")
