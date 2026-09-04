"""Panorama do funil: os números que qualquer revisão precisa ter na mão.

    .venv\\Scripts\\python.exe scripts\\panorama.py

Existe porque as revisões (docs/REVISAO_*.md) começam todas
pela mesma pergunta — onde o funil vaza — e a resposta estava espalhada em
one-liners frágeis colados em documento. Um script versionado é conferível e
sobrevive a mudança de schema.

Só lê. Não altera nada, não toca a rede.
"""
import contextlib
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# O console do Windows abre em cp1252, que não codifica caixa nem bloco. Sem
# isto o script morre com UnicodeEncodeError antes de imprimir a primeira linha
# — e um relatório que só roda no terminal de quem escreveu não serve para nada.
with contextlib.suppress(Exception):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

#: Cai para ASCII quando nem o UTF-8 pegou (terminal antigo, saída redirecionada
#: para arquivo com encoding fixo). Feio é melhor que traceback.
_UTF8 = (getattr(sys.stdout, "encoding", "") or "").lower().replace("-", "") == "utf8"
LINHA = "═" if _UTF8 else "="
TRACO = "─" if _UTF8 else "-"
BLOCO = "█" if _UTF8 else "#"
SETA = "→" if _UTF8 else ">"
ALERTA = "⚠️ " if _UTF8 else "[!]"

from jobapplier import paths, status  # noqa: E402
from jobapplier.database.connection import get_session  # noqa: E402
from jobapplier.database.models import Candidatura, Vaga  # noqa: E402
from jobapplier.tempo import agora_utc  # noqa: E402


def _barra(n: int, total: int, largura: int = 28) -> str:
    if not total:
        return ""
    return BLOCO * max(1, round(n / total * largura)) if n else ""


#: Desfechos que provam que aquele board deixou a automação concluir.
_PROVA_ENVIOU = ("enviada_confirmada", "enviada")
#: Desfecho que prova o contrário: o formulário foi preenchido e a plataforma
#: exigiu um humano para submeter.
_PROVA_BLOQUEOU = ("aguardando_verificacao",)


def _funil_ate_o_fim() -> None:
    """O que aconteceu DEPOIS de candidatar.

    Era o buraco permanente do projeto, anotado no rodapé deste relatório desde
    que ele existe: o funil morria em 'candidatada', e por isso o limiar de score
    nunca foi validado contra realidade. A tabela `eventos` existe para isto, e
    enquanto estiver vazia o relatório diz **vazia**, não zero — a diferença
    entre "ninguém respondeu" e "ninguém mediu" é a coisa mais importante aqui.
    """
    from jobapplier.database.models import Evento
    from jobapplier.desfecho import Desfecho

    with get_session() as sessao:
        eventos = Counter(t for (t,) in sessao.query(Evento.tipo).all())
        enviadas = (sessao.query(Candidatura)
                    .filter(Candidatura.status.in_(
                        ("enviada_confirmada", "enviada", "revisao_manual")))
                    .count())

    print(f"\n  DESFECHO — {sum(eventos.values())} eventos registrados")
    print(f"  {TRACO * 46}")

    if not eventos:
        print("    nenhum ainda.  A tabela é nova e a leitura de e-mail exige")
        print("    AIJOB_IMAP_* no .env. Enquanto estiver vazia, este relatório")
        print("    não sabe se você foi chamado — não que você não foi.")
        return

    for tipo in (Desfecho.RECEBIDA, Desfecho.RESPOSTA, Desfecho.ENTREVISTA,
                 Desfecho.OFERTA, Desfecho.RECUSA):
        n = eventos.get(str(tipo), 0)
        taxa = f"{n / enviadas * 100:>5.1f}% das enviadas" if enviadas else ""
        print(f"    {tipo!s:<14}{n:>6}  {_barra(n, max(enviadas, 1), 18):<20}{taxa}")

    sem_retorno = enviadas - sum(
        eventos.get(str(t), 0) for t in (Desfecho.RECEBIDA, Desfecho.RESPOSTA,
                                         Desfecho.ENTREVISTA, Desfecho.OFERTA,
                                         Desfecho.RECUSA))
    if sem_retorno > 0:
        print(f"    {'sem retorno':<14}{sem_retorno:>6}")


def _candidaturas_por_epoca(candidaturas: list[str]) -> None:
    """Desfechos separados por vocabulário, e **nunca somados**.

    O acervo antigo e o novo foram medidos com réguas diferentes: `enviada`
    significava "o botão foi clicado", e `enviada_confirmada` exige prova na
    página — foi essa frouxidão que produziu a taxa de 3,4% da auditoria. Somar
    os dois dá um número que não descreve nem um período nem o outro.

    Reclassificar o legado seria pior: inventaria certeza que não existe sobre
    envios que ninguém verificou.
    """
    atuais = Counter(c for c in candidaturas if not status.e_legado(c))
    legados = Counter(c for c in candidaturas if status.e_legado(c))

    print(f"\n  CANDIDATURAS — {len(candidaturas):,}")
    print(f"  {TRACO * 46}")

    print(f"    vocabulário atual{sum(atuais.values()):>29,}")
    for codigo, n in atuais.most_common():
        print(f"      {status.de_candidatura(codigo).rotulo[:28]:<32}{n:>7,}")
    if not atuais:
        print("      (nenhuma ainda)")

    if legados:
        print(f"\n    legado, régua antiga{sum(legados.values()):>26,}")
        for codigo, n in legados.most_common():
            print(f"      {status.de_candidatura(codigo).rotulo[:28]:<32}{n:>7,}")
        print(f"\n    {ALERTA} não some as duas colunas: 'enviada' do legado "
              "queria dizer\n        'o botão foi clicado', e 'enviada e "
              "confirmada' exige prova na página.")


def classificar_barreira(desfechos, na_fila):
    """(enviou, bloqueou, último envio, vagas em board não medido).

    `desfechos` é uma sequência de (empresa, status, criado_em); `na_fila` é um
    contador de vagas vivas por empresa. Separado da impressão para poder ser
    testado sem banco — a regra de precedência abaixo é a parte que importa.
    """
    enviou, bloqueou, ultimo_envio = set(), set(), None
    for empresa, st, quando in desfechos:
        if st in _PROVA_ENVIOU:
            enviou.add(empresa)
            if quando is not None:
                ultimo_envio = max(ultimo_envio or quando, quando)
        elif st in _PROVA_BLOQUEOU:
            bloqueou.add(empresa)

    # Prova de bloqueio vence a de envio: um board que enviava e passou a exigir
    # código é exatamente a mudança que este quadro existe para flagrar, e
    # deixá-lo listado como "envio ok" por causa de um sucesso antigo esconderia
    # justamente o que mudou.
    enviou -= bloqueou
    conhecidas = enviou | bloqueou
    desconhecidas = sum(n for e, n in na_fila.items() if e not in conhecidas)
    return enviou, bloqueou, ultimo_envio, desconhecidas


def _barreira_de_envio() -> None:
    """Quais boards deixam a automação concluir — medido, não estimado.

    Não existe sinal detectável antes de submeter: a página da Adyen carregada
    sem nenhuma interação não tem campo de código no DOM, e o HTML bruto dela é
    indistinguível do de um board que aceita envio. Sondar exigiria mandar
    candidaturas reais só para descobrir, o que é caro no único sentido que
    importa — cada sonda é uma candidatura de verdade numa empresa de verdade.

    reCAPTCHA foi testado como atalho e reprovado: está em 17 de 23 boards do
    acervo, **incluindo os dois onde o envio comprovadamente funcionou**. Um
    número com cara de resposta e sem conteúdo é pior que nenhum.

    Então o mapa se constrói sozinho, com os envios que você faria de qualquer
    jeito. Esta seção mostra o que já se sabe e o quanto ainda é desconhecido.
    """
    from jobapplier import empresas as mod_empresas

    with get_session() as sessao:
        desfechos = (
            # `atualizado_em`, não `criado_em`: a linha é gravada por upsert,
            # então um envio de hoje pode viver numa linha nascida semanas atrás
            # como 'simulada'. A pergunta aqui é quando o envio aconteceu.
            sessao.query(Vaga.empresa, Candidatura.status, Candidatura.atualizado_em)
            .join(Candidatura, Candidatura.vaga_id == Vaga.id)
            .filter(Vaga.plataforma == "greenhouse")
            .all()
        )
        na_fila = Counter(
            e for (e,) in sessao.query(Vaga.empresa).filter(
                Vaga.plataforma == "greenhouse",
                Vaga.status.in_(("aprovada", "pendente", "pronta_envio_manual",
                                 "pronta_para_revisao")),
            ).all()
        )

    enviou, bloqueou, ultimo_envio, vagas_desconhecidas = classificar_barreira(
        desfechos, na_fila)

    print(f"\n  BARREIRA DE ENVIO — greenhouse, {len(na_fila)} boards na fila")
    print(f"  {TRACO * 46}")
    if not (enviou or bloqueou):
        print("    nada medido ainda — o mapa começa no primeiro envio real")
    for empresa in sorted(bloqueou):
        print(f"    {mod_empresas.nome_exibicao(empresa)[:22]:<24}"
              f"exige código{na_fila.get(empresa, 0):>6} na fila")
    for empresa in sorted(enviou):
        print(f"    {mod_empresas.nome_exibicao(empresa)[:22]:<24}"
              f"envio ok    {na_fila.get(empresa, 0):>6} na fila")
    print(f"    {'(não medido)':<24}            {vagas_desconhecidas:>6} na fila")

    if ultimo_envio:
        dias = (agora_utc() - ultimo_envio).days
        print(f"\n    último envio automático concluído: "
              f"{ultimo_envio:%d/%m/%Y} ({dias} dias atrás)")
        # A hipótese que este número testa: se a verificação por e-mail passou a
        # valer para o Greenhouse todo, e não só para um board, a data do último
        # sucesso para de avançar mesmo com a fila cheia. Duas ou três sessões de
        # `scripts/finalizar.py` resolvem a dúvida com dado, não com suposição.
        if dias > 30 and vagas_desconhecidas:
            print(f"    {ALERTA} nenhum envio automático há {dias} dias — pode "
                  "não ser mais\n        uma peculiaridade de um board")


def main() -> int:
    with get_session() as sessao:
        vagas = sessao.query(Vaga.plataforma, Vaga.status, Vaga.score).all()
        candidaturas = [c for (c,) in sessao.query(Candidatura.status).all()]

    total = len(vagas)
    if not total:
        print("Banco vazio — rode uma coleta primeiro.")
        return 1

    print(f"\n{LINHA * 62}\n  PANORAMA DO FUNIL — {total:,} vagas\n{LINHA * 62}")

    # ── Por plataforma ────────────────────────────────────────────────────────
    por_plataforma = Counter(p for p, _, _ in vagas)
    vivos = {"aprovada", "pendente", "pronta_envio_manual", "pronta_para_revisao"}

    print(f"\n  {'PLATAFORMA':<14}{'TOTAL':>8}{'VIVAS':>8}{'APROVEITAMENTO':>16}")
    print(f"  {TRACO * 46}")
    for plataforma, n in por_plataforma.most_common():
        vivas = sum(1 for p, st, _ in vagas if p == plataforma and st in vivos)
        print(f"  {plataforma:<14}{n:>8,}{vivas:>8,}{vivas / n * 100:>15.1f}%")

    # ── Por status ────────────────────────────────────────────────────────────
    por_status = Counter(st for _, st, _ in vagas)
    print(f"\n  {'STATUS':<26}{'N':>7}  {'':<28}")
    print(f"  {TRACO * 62}")
    for codigo, n in por_status.most_common():
        s = status.de_vaga(codigo)
        marca = SETA if s.exige_acao else " "
        print(f"  {marca} {s.rotulo[:24]:<24}{n:>7,}  {_barra(n, total)}")

    acao = sum(n for c, n in por_status.items() if status.de_vaga(c).exige_acao)
    print(f"\n  Esperando por você: {acao:,} vagas")

    # ── Score ─────────────────────────────────────────────────────────────────
    scores = sorted(s for _, _, s in vagas if s is not None)
    if scores:
        print(f"\n  SCORE — {len(scores):,} vagas pontuadas")
        print(f"  {TRACO * 46}")
        faixas = [(0, 45, "rejeitada"), (45, 65, "pendente"), (65, 101, "aprovada")]
        for piso, teto, rotulo in faixas:
            n = sum(1 for s in scores if piso <= s < teto)
            print(f"    {piso:>3}–{teto - 1:<3} {rotulo:<12}{n:>7,}  {_barra(n, len(scores))}")
        meio = scores[len(scores) // 2]
        print(f"\n    mediana {meio:.0f} · mínimo {scores[0]:.0f} · máximo {scores[-1]:.0f}")
        # Score que não separa nada não ordena a fila, só carimba.
        largura = scores[-1] - scores[0]
        if largura < 30:
            print(f"    {ALERTA} faixa estreita: o score não está ordenando a fila")

    # ── Desfecho ──────────────────────────────────────────────────────────────
    _candidaturas_por_epoca(candidaturas)

    # ── Desfecho real ─────────────────────────────────────────────────────────
    _funil_ate_o_fim()

    # ── Barreira de envio ─────────────────────────────────────────────────────
    _barreira_de_envio()

    # ── Documentos ────────────────────────────────────────────────────────────
    pdfs = len(list(paths.RESUMES.glob("*.pdf")))
    cartas = len(list(paths.COVER_LETTERS.glob("*.txt")))
    print(f"\n  DOCUMENTOS\n  {TRACO * 46}")
    print(f"    currículos gerados{pdfs:>26,}")
    print(f"    cartas geradas{cartas:>30,}")

    # ── O buraco permanente ───────────────────────────────────────────────────
    print(f"\n{LINHA * 62}")
    print("  A tabela `eventos` existe agora, e é o que fará o limiar de score")
    print("  deixar de ser chute. Mas ela só enche com uso: cada resposta que")
    print("  chegar por e-mail vira uma linha, e em dois meses há o que medir.")
    print("  Até lá, nenhum número deste relatório diz se você é chamado.")
    print(f"{LINHA * 62}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
