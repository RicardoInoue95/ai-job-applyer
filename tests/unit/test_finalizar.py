"""A sessão assistida não pode virar envio desatendido.

Ler o código do e-mail é aceitável porque o candidato está presente e aprova
cada candidatura: o controle da plataforma pergunta "há um humano decidindo
mandar isto?", e a resposta é honestamente sim. O que seria desonesto é o
sistema puxar o código e submeter a fila sozinho — e a diferença entre as duas
coisas mora inteira em duas linhas de código.

Estes testes guardam essas duas linhas.
"""
import ast
import inspect
from pathlib import Path

import pytest

from jobapplier.applicators import greenhouse
from jobapplier.applicators.base import (
    AGUARDANDO_VERIFICACAO,
    ENVIADA_CONFIRMADA,
    FALHA_AUTOMACAO,
    STATUS_BLOQUEIA_RETENTATIVA,
    STATUS_VALIDOS,
    avaliar_confirmacao,
)

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "finalizar.py"
FONTE = SCRIPT.read_text(encoding="utf-8")


def test_o_script_existe_e_e_valido():
    ast.parse(FONTE)


def test_script_nunca_clica_em_enviar():
    """O clique final é do candidato, no botão real da página. Se algum dia
    aparecer um `.click()` aqui, a sessão deixou de ser assistida."""
    arvore = ast.parse(FONTE)
    for no in ast.walk(arvore):
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute):
            assert no.func.attr not in ("click", "submit"), (
                f"linha {no.lineno}: o script não pode submeter — quem clica é o candidato")


def test_script_abre_o_navegador_na_tela():
    """Navegador invisível é envio desatendido com outro nome. Checa a chamada,
    não o texto: a docstring fala em "headless" ao explicar por que não usa."""
    arvore = ast.parse(FONTE)
    pediu_visivel = False
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        for kw in no.keywords:
            assert kw.arg != "headless", (
                f"linha {no.lineno}: o script não escolhe headless, escolhe visível")
            if kw.arg == "visivel" and getattr(kw.value, "value", None) is True:
                pediu_visivel = True
    assert pediu_visivel, "o script precisa pedir navegador visível"


def test_script_nao_imprime_o_codigo():
    """Devolver o código a quem preenche é o trabalho; imprimi-lo o deixa no
    scrollback do terminal, e às vezes em log de sessão."""
    arvore = ast.parse(FONTE)
    for no in ast.walk(arvore):
        if not (isinstance(no, ast.Call) and isinstance(no.func, ast.Name)
                and no.func.id == "print"):
            continue
        impresso = ast.dump(ast.Module(body=[ast.Expr(a) for a in no.args],
                                       type_ignores=[]))
        for suspeito in ("'codigo'", "attr='codigo'"):
            assert suspeito not in impresso, f"linha {no.lineno}: print vaza o código"


# ── O estado novo ─────────────────────────────────────────────────────────────

def test_aguardando_verificacao_e_status_valido():
    assert AGUARDANDO_VERIFICACAO in STATUS_VALIDOS


def test_aguardando_verificacao_bloqueia_retentativa():
    """A plataforma já disparou um código. Retentar sozinho repreencheria tudo e
    dispararia outro, em laço, sem nunca passar — só um humano passa dali."""
    assert AGUARDANDO_VERIFICACAO in STATUS_BLOQUEIA_RETENTATIVA


def test_verificacao_humana_nao_e_falha():
    """Confundir os dois infla a taxa de erro do funil com trabalho que deu
    certo, e esconde a única categoria que a sessão assistida resolve."""
    status, msg = avaliar_confirmacao({}, verificacao_humana=True)
    assert status == AGUARDANDO_VERIFICACAO
    assert status != FALHA_AUTOMACAO
    assert "verificação humana" in msg


def test_sem_verificacao_continua_sendo_falha():
    status, _ = avaliar_confirmacao({}, verificacao_humana=False)
    assert status == FALHA_AUTOMACAO


def test_confirmacao_vence_a_verificacao_na_tela():
    """Campo de código que sobra numa página já confirmada é resíduo; rebaixar
    um envio confirmado seria pior que ignorá-lo."""
    status, _ = avaliar_confirmacao({"url de confirmação": True},
                                    verificacao_humana=True)
    assert status == ENVIADA_CONFIRMADA


def test_pergunta_sem_resposta_ainda_vence():
    status, _ = avaliar_confirmacao({}, perguntas_manuais=["Qual seu CID?"],
                                    verificacao_humana=True)
    assert status != AGUARDANDO_VERIFICACAO


# ── Detecção na página ────────────────────────────────────────────────────────

class _PaginaFake:
    def __init__(self, com_campo: bool):
        self.com_campo = com_campo

    def query_selector(self, _seletor):
        return object() if self.com_campo else None


TEXTO_ADYEN = ("a verification code was sent to ricardo@exemplo.com. to submit "
               "your application, enter the 8-character code to confirm you're "
               "a human.")


def test_detecta_o_passo_de_verificacao():
    assert greenhouse._pede_verificacao_humana(_PaginaFake(True), TEXTO_ADYEN)


def test_texto_sem_campo_nao_conta():
    """Falso positivo aqui é caro: a vaga entraria em bloqueio de retentativa e
    nunca mais seria tentada. Página que só menciona verificação numa política
    de privacidade não tem onde digitar um código."""
    assert not greenhouse._pede_verificacao_humana(_PaginaFake(False), TEXTO_ADYEN)


def test_campo_sem_texto_nao_conta():
    assert not greenhouse._pede_verificacao_humana(
        _PaginaFake(True), "obrigado por se candidatar")


# ── Contrato com o applicator ─────────────────────────────────────────────────

def test_apply_aceita_os_dois_parametros():
    p = inspect.signature(greenhouse.apply).parameters
    assert p["visivel"].default is False, "headless continua sendo o padrão"
    assert p["ao_verificar"].default is None


def test_nao_existe_apply_paralelo():
    """Uma segunda função de envio seria cópia das 279 linhas do `apply`, e cópia
    diverge: o formulário muda, uma é corrigida, a outra passa a enviar errado."""
    duplicatas = [n for n in dir(greenhouse)
                  if n.startswith("apply") and n != "apply"]
    assert not duplicatas, duplicatas


def test_gancho_recusado_nao_vira_enviada():
    """Se o candidato fechar a aba ou o tempo esgotar, o desfecho tem de ser
    'aguardando verificação' — nunca 'enviada'."""
    fonte = inspect.getsource(greenhouse.apply)
    trecho = fonte[fonte.index("if verificacao_humana and ao_verificar"):]
    trecho = trecho[:trecho.index("# Captura possíveis erros")]
    assert "if ao_verificar(page):" in trecho, (
        "o sinal forte só pode ser marcado quando o gancho confirma")


@pytest.mark.parametrize("proibido", ["click(", "submit("])
def test_modulo_de_verificacao_nao_navega(proibido):
    from jobapplier import verificacao

    assert proibido not in inspect.getsource(verificacao)


# ── O script não pode contornar o guard ───────────────────────────────────────
# A primeira versão chamava `greenhouse.apply()` direto. Uma candidatura saiu de
# verdade e o banco não soube: `ja_candidatado()` não bloquearia um reenvio, o
# funil contaria um envio a menos, e nenhum limite diário foi consultado.

def test_script_nao_chama_o_applicator_direto():
    arvore = ast.parse(FONTE)
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom) and "applicators" in (no.module or ""):
            nomes = [a.name for a in no.names]
            assert "apply" not in nomes, (
                f"linha {no.lineno}: envio tem de passar pelo orquestrador "
                "(duplicidade, limite, lease, registro)")


def test_script_envia_pelo_orquestrador():
    assert "orchestrator.run_applications(" in FONTE


def test_script_le_o_desfecho_do_banco():
    """A tela pode mentir; o registro é o que o resto do sistema consulta."""
    assert "_desfecho(" in FONTE


def test_sessao_assistida_exige_lista_explicita():
    """Navegador visível com a fila inteira é envio em lote com o candidato de
    espectador — o oposto do que a sessão assistida significa."""
    from jobapplier import orchestrator

    with pytest.raises(ValueError, match="apenas_ids"):
        orchestrator._executar_candidaturas(visivel=True)
    with pytest.raises(ValueError, match="apenas_ids"):
        orchestrator._executar_candidaturas(ao_verificar=lambda p: True)


def test_run_applications_expoe_a_sessao_assistida():
    from jobapplier import orchestrator

    p = inspect.signature(orchestrator.run_applications).parameters
    assert p["visivel"].default is False
    assert p["ao_verificar"].default is None


# ── A barreira muda por plataforma, e o remédio também ────────────────────────
# Greenhouse manda código por e-mail: dá para buscar e preencher. Lever e inhire
# mostram desafio visual: só o candidato resolve. Tratar os dois igual fazia o
# script esperar 90s por um e-mail que nunca chegaria antes de pedir o clique.

class _PaginaComSeletores:
    def __init__(self, presentes):
        self.presentes = set(presentes)

    def query_selector(self, seletor):
        return object() if seletor in self.presentes else None


def test_reconhece_barreira_de_codigo():
    import sys as _sys

    _sys.path.insert(0, str(SCRIPT.parent))
    from finalizar import barreira

    assert barreira(_PaginaComSeletores(["input[id^='security-input']"])) == "codigo"


@pytest.mark.parametrize("seletor", [
    "iframe[src*='hcaptcha']", ".h-captcha",
    "iframe[src*='recaptcha']", ".g-recaptcha",
])
def test_reconhece_desafio_visual(seletor):
    import sys as _sys

    _sys.path.insert(0, str(SCRIPT.parent))
    from finalizar import barreira

    assert barreira(_PaginaComSeletores([seletor])) == "captcha"


def test_sem_barreira_nao_inventa():
    import sys as _sys

    _sys.path.insert(0, str(SCRIPT.parent))
    from finalizar import barreira

    assert barreira(_PaginaComSeletores([])) == ""


def test_codigo_vence_captcha():
    """O Greenhouse tem reCAPTCHA v3 na página inteira. Se o campo de código
    existe, é ele que trava o envio — buscar o e-mail resolve, e pedir para o
    candidato "resolver o CAPTCHA" o mandaria procurar algo invisível."""
    import sys as _sys

    _sys.path.insert(0, str(SCRIPT.parent))
    from finalizar import barreira

    pagina = _PaginaComSeletores(["input[id^='security-input']", ".g-recaptcha"])
    assert barreira(pagina) == "codigo"


@pytest.mark.parametrize("proibido", [
    # Só nomes de serviço e chamadas de API: um termo genérico como "solver"
    # casa dentro de "resolver", que é a palavra que a explicação honesta usa —
    # o teste passaria a punir o comentário que diz que não fazemos isso.
    "2captcha", "anticaptcha", "capsolver", "deathbycaptcha",
    "hcaptcha.render", "grecaptcha.execute", "navigator.webdriver",
])
def test_nao_resolve_o_desafio_visual(proibido):
    """Buscar um código no e-mail do próprio candidato é assistência; resolver
    um CAPTCHA por ele é evasão de detecção."""
    assert proibido not in FONTE.lower()
