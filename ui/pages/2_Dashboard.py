"""Página inicial: o estado das suas vagas e por onde continuar.

Duas reescritas, e a segunda por um motivo diferente da primeira. A primeira
matou o painel técnico — 501 linhas fazendo cinco trabalhos, oito métricas em
duas fileiras, sete botões espalhados. A segunda, esta, resolve o que sobrou:
**um número gigante sozinho no meio da tela** não é página inicial, é placar.

Agora as métricas contam a história do funil em cartões compactos, e o topo é a
retomada — "continue sua revisão" leva à próxima vaga da fila, que é o que
alguém quer ao abrir isto pela segunda vez.

O que não mudou, de propósito: documento gerado NUNCA aparece como candidatura
enviada. São coisas diferentes, e misturá-las faria o sistema parecer mais
produtivo do que é — 341 currículos preparados não são 341 candidaturas.
"""
import _bootstrap  # noqa: F401, I001  # antes de qualquer import de jobapplier
import _ui

import streamlit as st

from jobapplier.config.manager import ConfigManager

config = ConfigManager()

try:
    from sqlalchemy import func

    from jobapplier import envio_automatico as ea
    from jobapplier import paths, status
    from jobapplier.database.connection import get_session
    from jobapplier.database.models import Vaga
except Exception as exc:
    st.error(f"Banco de dados indisponível: {exc}", icon=":material/error:")
    st.info("Execute `python run.py` para subir o Postgres e a aplicação.")
    st.stop()


@st.cache_data(ttl=30)
def panorama() -> dict:
    """Os números do painel numa consulta só."""
    with get_session() as sessao:
        vagas = sessao.query(Vaga.plataforma, Vaga.status).all()
        pontuadas = (sessao.query(func.count(Vaga.id))
                     .filter(Vaga.score.isnot(None)).scalar() or 0)
        enviadas = (sessao.query(func.count(Vaga.id))
                    .filter(Vaga.status.in_(("candidatada", "enviada_manual")))
                    .scalar() or 0)

    conta: dict[str, int] = {}
    por_plataforma: dict[str, dict[str, int]] = {}
    for plataforma, codigo in vagas:
        conta[codigo] = conta.get(codigo, 0) + 1
        alvo = por_plataforma.setdefault(plataforma or "?", {"total": 0, "util": 0})
        alvo["total"] += 1
        if status.de_vaga(codigo).exige_acao:
            alvo["util"] += 1

    revisar = sum(n for c, n in conta.items() if status.de_vaga(c).exige_acao)
    return {
        "total": len(vagas), "pontuadas": pontuadas, "enviadas": enviadas,
        "revisar": revisar,
        "possibilidades": conta.get("pendente", 0),
        "adiadas": conta.get("adiada", 0),
        "por_plataforma": por_plataforma,
    }


def executar(rotulo: str, funcao, mensagem: str) -> None:
    with st.spinner(mensagem):
        try:
            funcao()
        except Exception as exc:
            st.error(f"{rotulo} falhou: {exc}", icon=":material/error:")
            return
    panorama.clear()
    st.success(f"{rotulo} concluída.", icon=":material/check_circle:")
    st.rerun()


dados = panorama()

_ui.cabecalho("Dashboard", "Acompanhe suas vagas e continue de onde parou.")

# ── Continuar de onde parei ───────────────────────────────────────────────────
# O topo da página inicial é a retomada, não um placar.

if dados["revisar"]:
    with st.container(border=True):
        esq, dir_ = st.columns([2.6, 1], vertical_alignment="center")
        with esq:
            st.markdown(
                '<div style="font-size:1.02rem;font-weight:600;color:var(--txt-1)">'
                'Continue sua revisão</div>'
                '<div style="font-size:.875rem;color:var(--txt-3);margin-top:.15rem">'
                f'{dados["revisar"]} vagas aguardando sua revisão, com currículo e '
                'respostas já preparados.</div>',
                unsafe_allow_html=True,
            )
        with dir_:
            st.page_link("pages/5_Aplicar.py", label="Revisar agora",
                         icon=":material/rate_review:", use_container_width=True)
else:
    _ui.vazio("Nada aguardando revisão",
              "Colete vagas novas ou reduza a aderência mínima na tela de revisão.")

# ── Métricas ──────────────────────────────────────────────────────────────────
# Documento preparado nunca é apresentado como candidatura: são coisas
# diferentes, e juntá-las inflaria o resultado.

_ui.secao("Suas vagas")
m1, m2, m3, m4 = st.columns(4)
with m1:
    _ui.metrica("Aguardando revisão", dados["revisar"],
                "com material preparado", destaque=bool(dados["revisar"]))
with m2:
    _ui.metrica("Possibilidades", dados["possibilidades"],
                "abaixo do corte de aderência")
with m3:
    _ui.metrica("Deixadas para depois", dados["adiadas"], "você adiou a decisão")
with m4:
    _ui.metrica("Candidaturas enviadas", dados["enviadas"], "confirmadas por você")

# ── Origem ────────────────────────────────────────────────────────────────────

_ui.secao("De onde vêm as vagas")
esq, dir_ = st.columns([3, 2])

with esq:
    for plataforma, n in sorted(dados["por_plataforma"].items(),
                                key=lambda x: -x[1]["util"]):
        taxa = n["util"] / n["total"] if n["total"] else 0
        st.markdown(
            '<div style="display:flex;justify-content:space-between;'
            'font-size:.875rem;margin-bottom:.15rem">'
            '<span style="color:var(--txt-1);font-weight:550">'
            f'{plataforma.title()}</span>'
            f'<span class="num" style="color:var(--txt-3)">{n["util"]} de '
            f'{n["total"]:,} úteis</span></div>'.replace(",", "."),
            unsafe_allow_html=True,
        )
        st.progress(min(taxa, 1.0))

with dir_:
    pdfs = len(list(paths.RESUMES.glob("*.pdf")))
    cartas = len(list(paths.COVER_LETTERS.glob("*.txt")))
    st.markdown(
        '<div class="cartao">'
        '<div style="font-size:.875rem;color:var(--txt-2);margin-bottom:.4rem">'
        f'<b class="num">{pdfs}</b> currículos adaptados</div>'
        '<div style="font-size:.875rem;color:var(--txt-2)">'
        f'<b class="num">{cartas}</b> cartas de apresentação</div>'
        '<div style="font-size:.8rem;color:var(--txt-3);margin-top:.5rem">'
        'Documentos preparados não são candidaturas: o envio acontece na tela '
        'de revisão.</div></div>',
        unsafe_allow_html=True,
    )

# ── Envio automático ──────────────────────────────────────────────────────────
# A lógica de quem qualifica mora em jobapplier/envio_automatico.py — aqui só
# botões.

_ui.secao("Envio automático")
corte_auto = ea.threshold_auto(config)

with st.container(border=True):
    if not ea.esta_ativo(config):
        st.markdown(
            f"**Desligado.** O sistema prepara currículo, carta e respostas, e "
            f"não envia nada. Ligado, vagas com aderência a partir de "
            f"{corte_auto}% em plataformas com automação serão enviadas em seu "
            f"nome, dentro dos limites diários."
        )
        entendo = st.checkbox(
            "Entendo que o sistema passará a enviar candidaturas em meu nome, "
            "sem revisão individual"
        )
        if st.button("Ativar envio automático", type="primary",
                     icon=":material/bolt:", disabled=not entendo):
            ea.ativar(config)
            panorama.clear()
            st.rerun()
    else:
        st.markdown(
            f"**Ligado.** Vagas futuras com aderência a partir de {corte_auto}% "
            f"em plataformas com automação serão enviadas automaticamente. As "
            f"demais seguem para a revisão."
        )
        if st.button("Desativar", icon=":material/pause:"):
            ea.desativar(config)
            panorama.clear()
            st.rerun()

        # Ativar e reenfileirar são atos separados, por decisão: vaga preparada
        # em modo sombra esperava revisão humana, e mudar isso retroativamente é
        # um segundo clique — com a lista na frente dos olhos.
        quals = ea.qualificaveis(config)
        if quals:
            st.markdown(f"**{len(quals)} vagas já preparadas** qualificam:")
            for q in quals:
                st.caption(f"{q['score']:.0f}% · {(q['titulo'] or '')[:56]} — "
                           f"{q['empresa'] or '—'}")
            if st.button(f"Reenfileirar {len(quals)} para envio",
                         icon=":material/playlist_add:"):
                n = ea.reenfileirar(config)
                panorama.clear()
                st.success(f"{n} vagas na fila de envio. Saem no próximo ciclo, "
                           "dentro dos limites diários.")
                st.rerun()

risco = config.load().get("risco") or {}
if risco.get("auto_aplicar_pendentes"):
    st.warning("`auto_aplicar_pendentes` está ligado: vagas pendentes serão "
               "candidatadas sem a sua aprovação.", icon=":material/warning:")

# ── Atualizar vagas ───────────────────────────────────────────────────────────
# Seção secundária e recolhida: é operação, não o assunto da página inicial.

_ui.secao("Atualizar vagas")
with st.expander("Execução manual"):
    st.caption("Normalmente roda sozinho a cada duas horas. Use aqui para "
               "forçar uma atualização.")
    a, b, c = st.columns(3)
    with a:
        if st.button("Coletar vagas", icon=":material/cloud_download:",
                     use_container_width=True,
                     help="Busca nas plataformas configuradas. Só HTTP, sem custo."):
            from jobapplier.orchestrator import run_collection
            executar("Coleta", run_collection, "Buscando vagas nas plataformas…")
    with b:
        if st.button("Filtrar e avaliar", icon=":material/filter_alt:",
                     use_container_width=True,
                     help="Filtros, normalização e aderência. Sem chamada de API."):
            from jobapplier.orchestrator import run_pipeline
            executar("Análise", run_pipeline, "Filtrando e avaliando…")
    with c:
        if st.button("Preparar documentos", icon=":material/description:",
                     use_container_width=True,
                     help="Currículo adaptado, PDF verificado e carta para cada "
                          "vaga aprovada."):
            from jobapplier.orchestrator import run_applications
            executar("Preparação", run_applications,
                     "Adaptando currículos e gerando PDFs…")

    st.caption(f"{dados['pontuadas']:,} vagas avaliadas de {dados['total']:,} "
               "coletadas.".replace(",", "."))
