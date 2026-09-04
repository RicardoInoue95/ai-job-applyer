"""O agendador precisa conseguir serializar todo job que registra.

O jobstore do APScheduler é o Postgres — é o que faz o agendamento sobreviver a
restart. Serializar um job exige uma referência textual `módulo:função`, e
função aninhada em `main()` não tem nenhuma.

Duas estavam aninhadas. `scheduler.start()` levantava

    ValueError: This Job cannot be serialized since the reference to its
    callable (<function main.<locals>._send_daily_report>) ...

e derrubava o orquestrador inteiro. O modo de falha era enganoso: coleta e
pipeline já tinham rodado uma vez antes do `start()`, então o log terminava com
"Pipeline concluído: aprovadas=75" logo acima do traceback, e parecia sucesso
com um erro solto no fim. Nenhum agendamento existia depois disso.

Sem cobertura de `orchestrator.run_*` nem do `main()`, isto só apareceu subindo
a plataforma de verdade. O teste é de AST de propósito: não precisa de Postgres,
não precisa iniciar o agendador, e mesmo assim reprova a regressão.
"""
import ast
import inspect

import pytest
from apscheduler.util import obj_to_ref

from jobapplier import orchestrator

FONTE = inspect.getsource(orchestrator)


def _jobs_registrados() -> list[str]:
    """Nome do primeiro argumento de cada `scheduler.add_job(...)`."""
    arvore = ast.parse(FONTE)
    nomes = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        alvo = no.func
        if not (isinstance(alvo, ast.Attribute) and alvo.attr == "add_job"):
            continue
        if not no.args:
            pytest.fail("add_job sem argumento posicional — callable indefinido")
        primeiro = no.args[0]
        if isinstance(primeiro, ast.Name):
            nomes.append(primeiro.id)
        elif isinstance(primeiro, ast.Lambda):
            pytest.fail("add_job recebeu lambda: lambda nunca é serializável")
        else:
            pytest.fail(f"add_job com callable inesperado: {ast.dump(primeiro)[:80]}")
    return nomes


def test_ha_jobs_registrados():
    """Se a extração parar de achar jobs, os testes abaixo passam vazios e a
    guarda vira decoração."""
    assert len(_jobs_registrados()) >= 5


@pytest.mark.parametrize("nome", _jobs_registrados())
def test_job_e_atributo_do_modulo(nome):
    """Função aninhada em `main()` não é atributo do módulo — é exatamente esse
    o caso que o APScheduler não consegue referenciar."""
    assert hasattr(orchestrator, nome), (
        f"'{nome}' não existe no nível do módulo: se estiver dentro de main(), "
        f"o jobstore não consegue serializá-la")


@pytest.mark.parametrize("nome", _jobs_registrados())
def test_job_e_serializavel(nome):
    """A checagem real do APScheduler, sem precisar de banco nem de start()."""
    alvo = getattr(orchestrator, nome, None)
    if alvo is None:
        pytest.skip("coberto por test_job_e_atributo_do_modulo")
    try:
        referencia = obj_to_ref(alvo)
    except ValueError as exc:
        pytest.fail(f"'{nome}' não é serializável para o jobstore: {exc}")
    assert ":" in referencia


def test_nenhum_job_definido_dentro_de_main():
    """Trava a forma, não só o efeito: uma `def` dentro de `main()` que vire job
    volta a quebrar, mesmo que hoje o nome coincida com um do módulo."""
    arvore = ast.parse(FONTE)
    main = next(n for n in ast.walk(arvore)
                if isinstance(n, ast.FunctionDef) and n.name == "main")
    aninhadas = {n.name for n in ast.walk(main)
                 if isinstance(n, ast.FunctionDef) and n is not main}
    registrados = set(_jobs_registrados())
    conflito = aninhadas & registrados
    assert not conflito, (
        f"{sorted(conflito)} definidas dentro de main() e registradas como job")


# ── Dispensa do corte de score ────────────────────────────────────────────────
# `threshold_auto` é substituto de julgamento humano: o score não é
# probabilidade calibrada. Quando o julgamento aconteceu numa vaga específica, o
# substituto perde a função — mas só naquela vaga.

def test_revisado_exige_lista_explicita():
    """Sem a amarra, `revisado=True` viraria "desligar o corte" para a fila
    inteira, que é outra coisa e mandaria dezenas de vagas de uma vez."""
    import pytest as _pytest

    with _pytest.raises(ValueError, match="apenas_ids"):
        orchestrator._executar_candidaturas(revisado=True)


def test_revisado_e_desligado_por_padrao():
    """O agendador chama sem argumento; o corte tem de valer para ele."""
    import inspect

    assinatura = inspect.signature(orchestrator.run_applications)
    assert assinatura.parameters["revisado"].default is False
    assert assinatura.parameters["apenas_ids"].default is None


def test_revisado_nao_mexe_nas_outras_guardas():
    """Limite diário, duplicidade e disjuntor não são substitutos de julgamento
    — são proteção contra dano, e revisão humana não os dispensa."""
    import inspect

    fonte = inspect.getsource(orchestrator._executar_candidaturas)
    trecho = fonte[fonte.index("if abaixo_do_auto and revisado:"):]
    trecho = trecho[:trecho.index("if abaixo_do_auto and applicators.suportada")]
    for guarda in ("checar_limite", "ja_candidatado", "liberar_lease"):
        assert guarda not in trecho, (
            f"'{guarda}' não pode ser afetada por revisado=True")
