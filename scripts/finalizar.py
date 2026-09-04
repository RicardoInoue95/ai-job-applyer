"""Sessão assistida: fecha as candidaturas que pararam em verificação humana.

    .venv\\Scripts\\python.exe scripts\\finalizar.py          # todas pendentes
    .venv\\Scripts\\python.exe scripts\\finalizar.py 10984    # uma vaga

Existe porque algumas plataformas — Adyen é o caso conhecido — só submetem
depois que o candidato digita um código de 8 caracteres enviado ao e-mail dele.
A automação preenche o formulário inteiro, o envio para ali, e o trabalho todo
se perde quando o navegador fecha: refazer à mão são 5 a 10 minutos por vaga.

**O que este script faz e o que não faz.** Ele abre um navegador VISÍVEL,
preenche o formulário, busca o código no e-mail e o preenche. Aí **para**. Quem
clica em enviar é você, no botão real da página, uma vaga por vez.

Essa divisão não é cerimônia. O controle da plataforma pergunta "há um humano
decidindo mandar esta candidatura?", e com você na frente da tela aprovando cada
uma, a resposta é honestamente sim — quem digita os oito caracteres é detalhe,
como o preenchimento de OTP que o celular faz. O que seria desonesto é submeter
a fila inteira sozinho de madrugada, e é justamente isso que não existe aqui.

Por isso o navegador nunca roda headless e não há caminho que clique em enviar.
`tests/unit/test_finalizar.py` falha se algum dos dois aparecer.
"""
import contextlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

with contextlib.suppress(Exception):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from jobapplier import verificacao
from jobapplier.applicators.base import AGUARDANDO_VERIFICACAO
from jobapplier.database.connection import get_session
from jobapplier.database.models import Candidatura, Vaga

#: Quanto esperar o e-mail chegar. A plataforma dispara o código quando o
#: formulário é submetido, então a espera começa depois do preenchimento.
ESPERA_EMAIL_S = 90
#: De quanto em quanto tempo reler a caixa. Curto demais irrita o servidor IMAP.
INTERVALO_S = 5
#: Teto de espera pelo seu clique, por vaga. Generoso: você pode estar lendo o
#: anúncio antes de decidir, que é exatamente o ponto.
ESPERA_CLIQUE_S = 600


def pendentes(ids: list[int] | None = None) -> list[Vaga]:
    """Vagas que pararam em verificação humana, da melhor para a pior."""
    with get_session() as s:
        consulta = (
            s.query(Vaga)
            .join(Candidatura, Candidatura.vaga_id == Vaga.id)
            .filter(Candidatura.status == AGUARDANDO_VERIFICACAO)
        )
        if ids:
            consulta = consulta.filter(Vaga.id.in_(ids))
        vagas = consulta.order_by(Vaga.score.desc()).all()
        for v in vagas:
            s.expunge(v)
        return vagas


def esperar_codigo(desde: float) -> str | None:
    """Relê a caixa até o código chegar ou a paciência acabar."""
    print(f"     aguardando o código no e-mail (até {ESPERA_EMAIL_S}s)...",
          flush=True)
    while time.monotonic() - desde < ESPERA_EMAIL_S:
        try:
            achado = verificacao.buscar_codigo()
        except verificacao.VerificacaoIndisponivel as exc:
            print(f"     {exc}")
            return None
        if achado:
            # O código não é impresso: o terminal costuma ficar em scrollback e
            # às vezes em log de sessão.
            print(f"     código recebido de {achado.remetente}")
            return achado.codigo
        time.sleep(INTERVALO_S)
    print("     não chegou. Digite o código à mão na janela do navegador.")
    return None


def preencher_codigo(page, codigo: str) -> bool:
    """Escreve o código no campo. Não clica em nada.

    Usa a mesma lista de seletores que a detecção, importada e não copiada: se
    o formulário mudar, os dois lugares mudam juntos. Cópia foi como a Adyen
    ficou detectando o texto e não o campo.
    """
    from jobapplier.applicators.greenhouse import _SELETORES_VERIFICACAO

    for seletor in _SELETORES_VERIFICACAO:
        campos = page.query_selector_all(seletor)
        if not campos:
            continue
        if len(campos) == 1:
            campos[0].fill(codigo)
            return True
        # A Adyen usa oito caixas de um caractere, uma por posição.
        for campo, letra in zip(campos, codigo, strict=False):
            campo.fill(letra)
        return True
    return False


#: Marcas de confirmação por plataforma. Greenhouse foi observado num envio real
#: (navega para `.../confirmation`); o do Lever é o que a documentação pública
#: descreve e **não foi verificado com um envio** — na dúvida o script diz "não
#: confirmada", que é o erro seguro: marcar como enviada o que não foi faz
#: `ja_candidatado()` bloquear a vaga para sempre.
_MARCAS_CONFIRMACAO = (
    "confirmation",           # greenhouse
    "thanks", "obrigado",     # lever e genéricos
    "application-received",
)
_SELETORES_CONFIRMACAO = (
    "#application_confirmation",
    ".application-confirmation",
    "[data-testid*='confirmation']",
    ".application-confirmation-message",
)


def barreira(page) -> str:
    """O que está travando o envio: `"codigo"`, `"captcha"` ou `""`.

    Existe porque as plataformas travam de jeitos diferentes e o remédio muda: o
    Greenhouse manda um código por e-mail, que dá para buscar e preencher; o
    Lever e a inhire mostram um desafio visual, que só o candidato resolve.
    Tratar os dois igual fazia o script esperar 90 segundos por um e-mail que
    nunca ia chegar antes de pedir o clique.
    """
    from jobapplier.applicators.greenhouse import _SELETORES_VERIFICACAO

    for seletor in _SELETORES_VERIFICACAO:
        with contextlib.suppress(Exception):
            if page.query_selector(seletor) is not None:
                return "codigo"
    for seletor in ("iframe[src*='hcaptcha']", ".h-captcha",
                    "iframe[src*='recaptcha']", ".g-recaptcha"):
        with contextlib.suppress(Exception):
            if page.query_selector(seletor) is not None:
                return "captcha"
    return ""


def esperar_seu_clique(page) -> bool:
    """Aguarda VOCÊ enviar. Devolve True se a página confirmou."""
    print("     >>> confira e clique em ENVIAR na janela do navegador.")
    print("         (Ctrl+C aqui aborta e não envia nada)")
    limite = time.monotonic() + ESPERA_CLIQUE_S
    while time.monotonic() < limite:
        try:
            url = page.url.lower()
            if any(m in url for m in _MARCAS_CONFIRMACAO):
                return True
            if any(page.query_selector(s) for s in _SELETORES_CONFIRMACAO):
                return True
        except Exception:
            # Aba fechada por você é uma decisão, não um erro.
            return False
        time.sleep(2)
    print("     tempo esgotado sem confirmação.")
    return False


def main(argv: list[str]) -> int:
    ids = [int(a) for a in argv if a.isdigit()]
    fila = pendentes(ids or None)
    if not fila:
        print("\n  Nenhuma candidatura aguardando verificação.\n")
        return 0

    if not verificacao.configurado():
        print("\n  IMAP não configurado — o código não será buscado sozinho.")
        print("  A sessão continua: você lê o código no e-mail e digita.\n")

    print(f"\n  {len(fila)} candidatura(s) para finalizar."
          f"  Você aprova uma por uma.\n")
    for i, vaga in enumerate(fila, 1):
        print(f"  [{i}/{len(fila)}] {vaga.empresa} · {(vaga.titulo or '')[:56]}")
        print(f"          fit {vaga.score or 0:.0f} · {vaga.link}")

        # Import tardio: quem só lista pendentes não precisa de navegador.
        # Via orquestrador, e não chamando o applicator direto: é ele que checa
        # duplicidade, limite diário e disjuntor, segura o lease e GRAVA a
        # candidatura. A primeira versão deste script pulava tudo isso — uma
        # candidatura foi enviada de verdade e o banco não soube (invariante 2).
        from jobapplier import orchestrator

        def ao_verificar(page, _t0=time.monotonic()):
            tipo = barreira(page)
            if tipo == "codigo":
                codigo = esperar_codigo(_t0)
                if codigo and not preencher_codigo(page, codigo):
                    print("     não achei o campo do código — digite na janela.")
            elif tipo == "captcha":
                # Nada a buscar: resolver o desafio por ele seria evasão de
                # detecção, que é a linha que este projeto não cruza.
                print("     desafio visual (CAPTCHA) na página — resolva na janela.")
            else:
                print("     nenhuma barreira detectada; confira antes de enviar.")
            return esperar_seu_clique(page)

        try:
            orchestrator.run_applications(
                apenas_ids=[vaga.id], revisado=True, visivel=True,
                ao_verificar=ao_verificar)
        except KeyboardInterrupt:
            print("\n  Interrompido. Nada foi enviado nesta vaga.\n")
            return 1
        except Exception as exc:
            print(f"     falhou: {type(exc).__name__}: {exc}\n")
            continue

        print(f"     {_desfecho(vaga.id)}\n")
    return 0


def _desfecho(vaga_id: int) -> str:
    """Lê do banco o que ficou registrado — a fonte é o registro, não a tela."""
    with get_session() as s:
        c = (s.query(Candidatura)
             .filter(Candidatura.vaga_id == vaga_id)
             .order_by(Candidatura.ciclo.desc()).first())
        return c.status if c else "sem registro"


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
