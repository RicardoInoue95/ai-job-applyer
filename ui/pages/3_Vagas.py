"""Catálogo: todas as vagas coletadas, de todas as plataformas, num lugar só.

É a tela que dá sentido ao nome do produto — centralizar. Serve para explorar e
comparar; decidir uma a uma é o trabalho da tela Revisar e aplicar.

Reescrita depois de uma revisão de UX. A versão anterior empilhava accordions
idênticos, cada um abrindo para revelar `📍 São Paulo | 🗂️ pendente` — emoji
como ícone, status como texto técnico cru, e nenhuma forma de comparar duas
vagas sem abrir as duas. O score aparecia como `**94**`, número sem unidade.

Agora cada vaga é uma linha escaneável: empresa e título no topo, plataforma,
local, modalidade e senioridade como metadados, aderência com barra, status como
badge. Dá para percorrer trinta sem abrir nenhuma.

Nenhuma regra mudou: os mesmos filtros, a mesma consulta, as mesmas ações de
aprovar e rejeitar, gravando o mesmo histórico.
"""
import _bootstrap  # noqa: F401, I001  # antes de qualquer import de jobapplier
import _ui

import streamlit as st

from jobapplier.config.manager import ConfigManager
from jobapplier.tempo import agora_utc

config = ConfigManager()

try:
    from sqlalchemy import String, cast, func

    from jobapplier import aderencia, empresas
    from jobapplier import status as vocab
    from jobapplier.database.connection import get_session
    from jobapplier.database.models import AprovacoesHistorico, Vaga
except Exception as exc:
    st.error(f"Erro ao conectar ao banco: {exc}", icon=":material/error:")
    st.stop()


_ui.cabecalho("Vagas", "Encontre oportunidades que combinam com você.")


# ── Filtros ───────────────────────────────────────────────────────────────────
# Uma barra compacta, não uma coluna de controles soltos. Vagas esperando por
# VOCÊ vêm primeiro: é o que o modo sombra produz e o que a tela existe para
# resolver.

_aguardando = vocab.exigem_sua_acao()
_demais = [c for c in vocab.codigos_vaga() if c not in _aguardando]
_OPCOES = ["aguardando você", *_aguardando, *_demais, "todas"]


def _rotulo_status(codigo: str) -> str:
    # "Na fila" é a fila inteira (394); "precisam de você" (42, na barra) é o
    # subconjunto com dossiê e aderência alta. Chamar o filtro de "Aguardando
    # você" fazia os dois parecerem o mesmo número.
    if codigo == "aguardando você":
        return "Na fila"
    if codigo == "todas":
        return "Todas"
    return vocab.de_vaga(codigo).rotulo


# Aderência como faixa, não como slider: "80%+" se lê e se lembra; um slider
# em 5 em 5 pede ajuste fino que ninguém quer fazer em lista.
_FAIXAS = {0: "Aderência", 65: "65%+", 75: "75%+", 80: "80%+", 85: "85%+"}
_SENIORIDADES = ["Júnior", "Pleno", "Sênior", "Especialista", "Líder"]

# Chaves fixas para que "Limpar filtros" consiga zerar tudo num clique.
_PADRAO = {"f_busca": "", "f_status": _OPCOES[0], "f_aderencia": 0,
           "f_modalidades": [], "f_plataformas": [], "f_local": "",
           "f_senioridades": [], "f_descartadas": False, "f_ordem": "aderencia",
           "f_limite": 25}
_ORDENS = {"aderencia": "Maior aderência", "recentes": "Mais recentes"}
PASSO = 25


def _mostrar_mais() -> None:
    st.session_state["f_limite"] = st.session_state.get("f_limite", PASSO) + PASSO


def _limpar_filtros() -> None:
    for chave, valor in _PADRAO.items():
        st.session_state[chave] = valor


filtros = st.container(key="filtros")
with filtros:
    c1, c2, c3, c4, c5 = st.columns([1.7, 1.3, 1.05, 1.15, 1.15])
with c1:
    busca = st.text_input("Buscar", placeholder="Título, empresa ou tecnologia",
                          label_visibility="collapsed", key="f_busca")
with c2:
    status_filter = st.selectbox("Status", _OPCOES,
                                 format_func=_rotulo_status,
                                 label_visibility="collapsed", key="f_status",
                                 help="**Na fila**: o que espera a sua decisão. "
                                      "**Todas**: também encerradas, enviadas e descartadas, "
                                      "com o status em cada cartão. Os demais são um status só.")
with c3:
    aderencia_min = st.selectbox("Aderência", list(_FAIXAS),
                                 format_func=_FAIXAS.__getitem__,
                                 label_visibility="collapsed", key="f_aderencia")
with c4:
    modalidades = st.multiselect("Modalidade", ["remoto", "híbrido", "presencial"],
                                 placeholder="Modalidade",
                                 format_func=str.capitalize,
                                 label_visibility="collapsed", key="f_modalidades")
with c5:
    plataformas = st.multiselect(
        "Plataforma", ["greenhouse", "gupy", "linkedin", "inhire", "lever"],
        placeholder="Plataforma", format_func=str.title,
        label_visibility="collapsed", key="f_plataformas")

with st.expander("Mais filtros"):
    m1, m2, m3 = st.columns([1, 1, 1.4], vertical_alignment="bottom")
    with m1:
        localizacao_busca = st.text_input("Localização", placeholder="Cidade", key="f_local")
    with m2:
        senioridades = st.multiselect("Senioridade", _SENIORIDADES, placeholder="Todas",
                                      key="f_senioridades")
    with m3:
        mostrar_filtradas = st.checkbox(
            "Incluir vagas descartadas pelos filtros", key="f_descartadas",
            help="Vagas que não passaram nos filtros 4A/4B. Úteis para conferir "
                 "se o filtro está cortando demais.")


# ── Consulta ──────────────────────────────────────────────────────────────────

def _get_vagas(status: str, busca: str, limite: int, ordem: str) -> tuple[list, int]:
    """Devolve (até `limite` vagas, total que casa com os filtros). O total
    existe para a legenda dizer "25 de 808"; "Mostrar mais" sobe o limite de
    25 em 25 — antes eram 100 de uma vez, 19 telas."""
    with get_session() as session:
        q = session.query(Vaga)
        if status == "aguardando você":
            q = q.filter(Vaga.status.in_(vocab.exigem_sua_acao()))
        elif status != "todas":
            q = q.filter(Vaga.status == status)
        elif not mostrar_filtradas:
            q = q.filter(Vaga.status.notin_(["filtrada_4a", "filtrada_4b"]))
        if busca:
            # Também nas tecnologias normalizadas: "Databricks" é como se pensa
            # numa vaga, e o título raramente diz.
            termo = f"%{busca.lower()}%"
            q = q.filter(
                func.lower(Vaga.titulo).like(termo) | func.lower(Vaga.empresa).like(termo)
                | func.lower(cast(Vaga.normalizado_json, String)).like(termo)
            )
        if plataformas:
            q = q.filter(Vaga.plataforma.in_(plataformas))
        if modalidades:
            q = q.filter(Vaga.modalidade.in_(modalidades))
        if aderencia_min:
            q = q.filter(Vaga.score >= aderencia_min)
        if localizacao_busca:
            q = q.filter(func.lower(Vaga.localizacao).like(f"%{localizacao_busca.lower()}%"))
        ordenacao = ((Vaga.criado_em.desc(), Vaga.score.desc().nullslast())
                     if ordem == "recentes"
                     else (Vaga.score.desc().nullslast(), Vaga.criado_em.desc()))
        if senioridades:
            # Senioridade mora em normalizado_json; filtrar no banco exigiria
            # operador JSON por dialeto. Cem linhas em Python é barato.
            aceitas = {x.lower() for x in senioridades}
            vagas = q.order_by(*ordenacao).limit(400).all()
            filtradas = [v for v in vagas
                         if isinstance(v.normalizado_json, dict)
                         and (v.normalizado_json.get("senioridade") or "").lower() in aceitas]
            return filtradas[:limite], len(filtradas)
        total = q.count()
        return q.order_by(*ordenacao).limit(limite).all(), total


def _aprovar(vaga_id: int, score_val: float | None):
    with get_session() as session:
        session.query(Vaga).filter(Vaga.id == vaga_id).update({"status": "aprovada"})
        if score_val is not None:
            session.add(AprovacoesHistorico(vaga_id=vaga_id, score=score_val,
                                            aprovado=True, criado_em=agora_utc()))


def _rejeitar(vaga_id: int, score_val: float | None):
    with get_session() as session:
        session.query(Vaga).filter(Vaga.id == vaga_id).update(
            {"status": "descartada_por_voce"})
        if score_val is not None:
            session.add(AprovacoesHistorico(vaga_id=vaga_id, score=score_val,
                                            aprovado=False, criado_em=agora_utc()))


# Ordenação ao lado da contagem: o widget precisa existir antes da consulta,
# a contagem só depois — por isso o espaço reservado à esquerda.
linha_topo = st.container()
with linha_topo:
    c_cont, c_ord = st.columns([2.2, 1], vertical_alignment="center")
    with c_ord:
        ordem = st.selectbox("Ordenar", list(_ORDENS), format_func=_ORDENS.__getitem__,
                             label_visibility="collapsed", key="f_ordem")
limite = st.session_state.get("f_limite", PASSO)
vagas, total = _get_vagas(status_filter, busca, limite, ordem)
# Em "Na fila" o status é sempre o mesmo e nos filtros por código você acabou
# de escolhê-lo. Em "Todas" ele é a única defesa: as quatro primeiras eram
# encerradas com 100% e ninguém via (auditoria de UX).
mostrar_status = status_filter == "todas"

# Filtros ativos como chips — também no estado vazio, que é justamente
# quando se pergunta "por que não vejo nada?".
ativos = [
    *(f"“{busca.strip()}”" for _ in [0] if busca.strip()),
    *([_rotulo_status(status_filter)] if status_filter != "aguardando você" else []),
    *([_FAIXAS[aderencia_min]] if aderencia_min else []),
    *(m.capitalize() for m in modalidades),
    *(p.title() for p in plataformas),
    *([localizacao_busca.strip()] if localizacao_busca.strip() else []),
    *senioridades,
    *(["descartadas incluídas"] if mostrar_filtradas else []),
]


def _linha_de_contagem(n: int) -> None:
    criterio = "mais recentes primeiro" if ordem == "recentes" else "por aderência"
    if not n:
        rotulo = "Nenhuma vaga"
    elif total > n:
        rotulo = f"{n} de {total} vagas, {criterio}"
    else:
        rotulo = f"{n} vaga{'s' if n != 1 else ''}, {criterio}"
    with c_cont:
        st.markdown(
            f'<div class="vaga-meta">'
            f'<span>{rotulo}</span>'
            + ("".join(_ui.badge(x) for x in ativos) if ativos else "")
            + "</div>",
            unsafe_allow_html=True,
        )

# ── Ações em lote ─────────────────────────────────────────────────────────────

if status_filter == "pendente" and vagas:
    with st.container(border=True):
        e, d = st.columns([2.4, 1], vertical_alignment="center")
        with e:
            st.markdown(f"**{len(vagas)} possibilidades** nesta seleção — "
                        "aderência abaixo do corte de aprovação.")
        with d:
            if st.button("Aprovar todas", icon=":material/done_all:",
                         use_container_width=True):
                for v in vagas:
                    _aprovar(v.id, v.score)
                st.success(f"{len(vagas)} vagas aprovadas.")
                st.rerun()

# ── Lista ─────────────────────────────────────────────────────────────────────

if not vagas:
    _linha_de_contagem(0)
    _ui.vazio("Nenhuma vaga com esses filtros",
              "Tente afrouxar a busca, o status ou a aderência mínima.")
    if ativos:
        st.button("Limpar filtros", icon=":material/filter_alt_off:",
                  type="tertiary", on_click=_limpar_filtros)
    st.stop()

_linha_de_contagem(len(vagas))

lista = st.container(key="lista")
for vaga in vagas:
    normalizado = vaga.normalizado_json if isinstance(vaga.normalizado_json, dict) else {}
    senioridade = normalizado.get("senioridade") or ""
    # "Desconhecida" não é informação: é o normalizador dizendo que não achou.
    if senioridade.lower() == "desconhecida":
        senioridade = ""

    # Nível 1: onde, como, que nível. Data de coleta e plataforma são nível 3 e
    # ficam em Detalhes — na lista, só confundiam com o que decide.
    meta = _ui.linha_meta(
        f"<span>{_ui.local_curto(vaga.localizacao)}</span>" if vaga.localizacao else "",
        f"<span>{(vaga.modalidade or '').capitalize()}</span>" if vaga.modalidade else "",
        f"<span>{senioridade}</span>" if senioridade else "",
    )

    a = aderencia.analisar(vaga).como_dict()
    with lista, st.container(border=True):
        esq, dir_ = st.columns([3.2, 1], vertical_alignment="top")
        with esq:
            # Uma linha do que a IA concluiu — o "porquê" do nível 1. Sem ela
            # o cartão era só título e número, e o trabalho de análise ficava
            # invisível. O ponto de atenção não vai aqui: em cem cartões vira
            # ruído; ele aparece em Detalhes e em Revisar.
            st.markdown(
                f'<div class="vaga-empresa">'
                f'{empresas.nome_exibicao(vaga.empresa) or vaga.empresa or "—"}</div>'
                f'<div class="vaga-titulo">{_ui.titulo_limpo(vaga.titulo) or "—"}</div>'
                f'{meta}'
                + (f'<div class="vaga-porque">{a["porque"]}</div>' if a.get("porque") else ""),
                unsafe_allow_html=True,
            )
        with dir_:
            # Status não vai na lista: em "aguardando você" é sempre o mesmo,
            # e nos outros filtros você acabou de escolhê-lo. Fica um sinal
            # pequeno só quando a vaga tem dossiê pronto, porque isso muda o
            # que fazer com ela — revisar, não aprovar.
            if mostrar_status:
                sinal = _ui.badge_status(vaga.status)
            else:
                # "Preparada" leva à página que a usa: antes era um sinal
                # sem destino, e a pessoa ia procurar a vaga na fila de 42.
                sinal = ('<a class="meta-linha" style="color:var(--ok)" href="/revisar" '
                         'target="_self">● Preparada · revisar</a>'
                         if vaga.status == "pronta_envio_manual" else "")
            st.markdown(
                '<div style="display:flex;flex-direction:column;'
                'align-items:flex-end;gap:.35rem">'
                f'{_ui.conclusao(a, so_titulo=True)}'
                f'{sinal}'
                '</div>',
                unsafe_allow_html=True,
            )

        with st.expander("Detalhes"):
            # Nível 2 pelo serviço: barras por eixo, tecnologias cobertas e o
            # que falta. Antes eram dois dicionários crus lidos à mão aqui e
            # de outro jeito em Revisar — a mesma vaga explicada de duas formas.
            if a.get("atencao"):
                st.markdown(f"⚠ {a['atencao']}")
            # Sem "A vaga pede: …": repetia 9 dos 12 chips acima. O que a
            # vaga pede e o currículo cobre está nos chips; o que falta, em
            # "Não cita".
            _ui.evidencia(a)
            # Nível 3, só aqui.
            coletada = vaga.criado_em.strftime("%d/%m/%Y") if vaga.criado_em else "—"
            st.caption(f"{(vaga.plataforma or '').title()} · vaga {vaga.id} · "
                       f"coletada em {coletada}")

            a1, a2, a3 = st.columns([1.3, 1, 1])
            with a1:
                st.link_button("Abrir vaga", vaga.link or "#",
                               icon=":material/open_in_new:",
                               use_container_width=True)
            if vaga.status == "pendente":
                with a2:
                    if st.button("Aprovar", key=f"apr_{vaga.id}", type="primary",
                                 icon=":material/check:", use_container_width=True):
                        _aprovar(vaga.id, vaga.score)
                        st.rerun()
                with a3:
                    if st.button("Descartar", key=f"rej_{vaga.id}",
                                 icon=":material/close:", use_container_width=True):
                        _rejeitar(vaga.id, vaga.score)
                        st.rerun()
            elif vaga.status == "aprovada":
                with a2:
                    if st.button("Desfazer aprovação", key=f"undo_{vaga.id}",
                                 icon=":material/undo:", use_container_width=True):
                        with get_session() as session:
                            session.query(Vaga).filter(Vaga.id == vaga.id).update(
                                {"status": "pendente"})
                        st.rerun()

if total > len(vagas):
    st.write("")
    st.button(f"Mostrar mais {min(PASSO, total - len(vagas))} "
              f"({len(vagas)} de {total})",
              icon=":material/expand_more:", use_container_width=True,
              on_click=_mostrar_mais)
