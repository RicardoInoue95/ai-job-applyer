"""Histórico: o que foi preparado, o que foi enviado e o que travou.

Reescrita depois de uma revisão de UX. A versão anterior era uma sequência de
accordions genéricos — para saber o que aconteceu com uma candidatura era
preciso abrir uma a uma, e não havia como comparar duas. Cinco `st.metric`
soltos no topo misturavam grandezas diferentes sob o rótulo "Total".

Agora é tabela: vaga, empresa, plataforma, status, data. Dá para ordenar,
filtrar e ver trinta linhas de uma vez. O detalhe de uma candidatura específica
continua acessível, mas deixou de ser o único caminho.

Uma correção de vocabulário que importa: "Erros" virou **Falhas técnicas**. Erro
sugere que o usuário errou; o que essas linhas registram é automação que não
completou.
"""
import _bootstrap  # noqa: F401, I001  # antes de qualquer import de jobapplier
import _ui

import streamlit as st

from jobapplier.config.manager import ConfigManager

config = ConfigManager()

try:
    from sqlalchemy import func

    from jobapplier import status as vocab
    from jobapplier.database.connection import get_session
    from jobapplier.database.models import Candidatura, Vaga
except Exception as exc:
    st.error(f"Erro ao conectar ao banco: {exc}", icon=":material/error:")
    st.stop()


_ui.cabecalho("Candidaturas",
              "Acompanhe o histórico e o andamento das suas candidaturas.")

# ── Métricas ──────────────────────────────────────────────────────────────────
# Cada uma diz o que conta. "Total" sozinho misturava candidatura enviada,
# documento preparado e tentativa que falhou — números de naturezas diferentes
# somados sob um rótulo que não explicava nada.

#: Vocabulário novo + legado: linhas antigas do banco continuam contando.
GRUPOS = {
    "enviadas": ("enviada_confirmada", "enviada"),
    # Só o vocabulário atual. `perguntas_pendentes` é legado da régua antiga —
    # 165 linhas de agosto — e contá-lo como "aguardando ação sua" punha 168 no
    # topo da página: a lista de afazeres de volta, com outro nome. As linhas
    # continuam na tabela, com o status delas.
    "revisao": ("revisao_manual",),
    "preparadas": ("simulada",),
    "falhas": ("falha_automacao", "erro"),
}

with get_session() as session:
    contagem = {
        nome: (session.query(func.count(Candidatura.id))
               .filter(Candidatura.status.in_(codigos)).scalar() or 0)
        for nome, codigos in GRUPOS.items()
    }
    aprovadas_count = (session.query(func.count(Vaga.id))
                       .filter(Vaga.status == "aprovada").scalar() or 0)

# Dois números, não quatro: "enviadas" e "aguardando alguma ação sua" são os
# que mudam uma decisão. "Preparadas" e "falhas técnicas" continuam na tabela,
# como filtro; a aderência ATS média era nível técnico e saiu da tela.
#
# Honesto sobre o limite: o sistema ainda não lê respostas por e-mail, então
# não sabe se você foi chamado. Fingir "em processo / entrevista" com colunas
# vazias seria uma falsa sensação de produto completo.
m1, m2 = st.columns(2)
with m1:
    _ui.metrica("Enviadas", contagem["enviadas"], "confirmadas pela plataforma")
with m2:
    _ui.metrica("Aguardando alguma ação sua", contagem["revisao"],
                "pergunta em branco ou envio sem prova",
                destaque=bool(contagem["revisao"]))
st.caption("Ainda não identificamos respostas a candidaturas enviadas — o "
           "acompanhamento por e-mail é o próximo passo do produto.")

# ── Ação principal ────────────────────────────────────────────────────────────
# Leva à revisão do que está pronto, não a um envio em massa sem contexto.

if aprovadas_count:
    with st.container(border=True):
        esq, dir_ = st.columns([2.6, 1], vertical_alignment="center")
        with esq:
            st.markdown(
                f"**{aprovadas_count} vagas aprovadas** aguardam preparação de "
                "documentos. Depois disso, você revisa e envia."
            )
        with dir_:
            st.page_link("pages/5_Aplicar.py", label="Ir para a revisão",
                         icon=":material/rate_review:", use_container_width=True)

# ── Filtros ───────────────────────────────────────────────────────────────────

_ui.secao("Histórico")

TODOS = "Todos os status"
_codigos = [s.codigo for s in vocab.CANDIDATURA]

f1, f2, f3 = st.columns([1.4, 1.3, 1.3])
with f1:
    busca = st.text_input("Buscar", placeholder="Vaga ou empresa",
                          label_visibility="collapsed")
with f2:
    filtro_status = st.selectbox(
        "Status", [TODOS, *_codigos], label_visibility="collapsed",
        format_func=lambda c: c if c == TODOS else vocab.de_candidatura(c).rotulo)
with f3:
    filtro_plataforma = st.multiselect(
        "Plataforma", ["greenhouse", "gupy", "linkedin", "inhire"],
        placeholder="Plataforma", label_visibility="collapsed")

with get_session() as session:
    q = (session.query(Candidatura, Vaga)
         .join(Vaga, Candidatura.vaga_id == Vaga.id))
    if filtro_status != TODOS:
        q = q.filter(Candidatura.status == filtro_status)
    if filtro_plataforma:
        q = q.filter(Vaga.plataforma.in_(filtro_plataforma))
    if busca:
        termo = f"%{busca.lower()}%"
        q = q.filter(func.lower(Vaga.titulo).like(termo)
                     | func.lower(Vaga.empresa).like(termo))
    linhas = q.order_by(Candidatura.criado_em.desc()).limit(300).all()
    registros = [
        {
            "id": c.id, "status": c.status, "criado_em": c.criado_em,
            "erro": c.erro, "perfil_base": c.perfil_base,
            "ats_otimizado": c.ats_score_otimizado,
            "titulo": v.titulo, "empresa": v.empresa,
            "plataforma": v.plataforma, "link": v.link,
        }
        for c, v in linhas
    ]

if not registros:
    _ui.vazio("Nenhuma candidatura com esses filtros",
              "Prepare documentos no Dashboard e revise as vagas para começar.")
    st.stop()

st.caption(f"{len(registros)} registro{'s' if len(registros) != 1 else ''} "
           "(máx. 300)")

# ── Tabela ────────────────────────────────────────────────────────────────────
# Estruturada, não accordion: o ponto é comparar e localizar, não abrir uma a uma.

st.dataframe(
    [
        {
            "Vaga": r["titulo"] or "—",
            # Slug técnico ("quintoandar") não é nome de empresa na tela.
            "Empresa": (r["empresa"] or "—").title(),
            "Plataforma": (r["plataforma"] or "").title(),
            "Status": vocab.de_candidatura(r["status"]).rotulo,
            "Data": r["criado_em"],
            "Abrir": r["link"] or None,
        }
        for r in registros
    ],
    use_container_width=True, hide_index=True, height=430,
    column_config={
        "Vaga": st.column_config.TextColumn(width="large"),
        "Data": st.column_config.DatetimeColumn(format="DD/MM/YY HH:mm",
                                                width="medium"),
        "Abrir": st.column_config.LinkColumn(display_text="Ver vaga",
                                             width="small"),
    },
)

# ── Detalhe ───────────────────────────────────────────────────────────────────
# Um por vez, escolhido — em vez de trinta accordions abertos por padrão.

with st.expander("Ver detalhes de uma candidatura"):
    escolha = st.selectbox(
        "Candidatura", registros,
        format_func=lambda r: f"{(r['titulo'] or '—')[:52]} — {r['empresa'] or '—'}",
        label_visibility="collapsed",
    )
    if escolha:
        s = vocab.de_candidatura(escolha["status"])
        st.markdown(_ui.badge(s.rotulo, s.tom), unsafe_allow_html=True)
        st.caption(s.descricao)

        d1, d2 = st.columns(2)
        with d1:
            st.caption(f"Perfil base: {escolha['perfil_base'] or '—'}")
            if escolha["ats_otimizado"]:
                st.caption(f"Aderência ATS do currículo: "
                           f"{escolha['ats_otimizado']:.0f}%")
        with d2:
            if escolha["link"]:
                st.link_button("Abrir vaga", escolha["link"],
                               icon=":material/open_in_new:",
                               use_container_width=True)

        if escolha["erro"]:
            st.warning(escolha["erro"], icon=":material/warning:")

        if escolha["status"] in ("falha_automacao", "erro"):
            if st.button("Tentar novamente", icon=":material/refresh:",
                         key=f"retry_{escolha['id']}"):
                with get_session() as session:
                    session.query(Vaga).filter(
                        Vaga.id == session.query(Candidatura.vaga_id)
                        .filter(Candidatura.id == escolha["id"]).scalar()
                    ).update({"status": "aprovada"})
                st.success("Vaga devolvida à fila de preparação.")
                st.rerun()
