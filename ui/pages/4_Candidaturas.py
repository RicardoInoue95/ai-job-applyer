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

    from jobapplier import acompanhamento, empresas, fila
    from jobapplier import status as vocab
    from jobapplier.database.connection import get_session
    from jobapplier.database.models import Candidatura, Vaga
except Exception as exc:
    st.error(f"Erro ao conectar ao banco: {exc}", icon=":material/error:")
    st.stop()


_ui.cabecalho("Candidaturas", "Acompanhe tudo o que você já enviou.")

# ── Funil ─────────────────────────────────────────────────────────────────────
# Manual por enquanto: você marca a resposta que obteve, e o número que o
# projeto nunca teve — de quantas fui chamado? — passa a existir. A leitura
# por e-mail continua sendo o destino (`jobapplier/desfecho.py`); quando
# chegar, conta na mesma tabela.

funil = acompanhamento.resumo()
partes = [f"**{funil.enviadas} enviadas**"]
if funil.com_resposta:
    partes.append(f"{funil.com_resposta} com resposta")
if funil.entrevistas:
    partes.append(f"{funil.entrevistas} entrevista{'s' if funil.entrevistas != 1 else ''}")
if funil.ofertas:
    partes.append(f"{funil.ofertas} oferta{'s' if funil.ofertas != 1 else ''}")
if funil.recusas:
    partes.append(f"{funil.recusas} recusa{'s' if funil.recusas != 1 else ''}")
st.markdown(" · ".join(partes))
# "Aguardando retorno" não é o que o sistema sabe: ele sabe que foram enviadas
# e que ninguém marcou resposta. A frase diz isso.
if funil.enviadas and not funil.com_resposta and not funil.recusas:
    st.caption("Nenhuma resposta identificada ainda. Marque abaixo quando uma "
               "empresa responder.")
elif funil.aguardando:
    st.caption(f"{funil.aguardando} sem resposta identificada.")

with get_session() as session:
    atencao = (session.query(func.count(Candidatura.id))
               .filter(Candidatura.status == "revisao_manual").scalar() or 0)


def _ver_atencao() -> None:
    """Aplica o filtro "Envio não confirmado" no histórico: a frase apontava
    para uma seção 900px abaixo, sem link nem filtro (auditoria de UX)."""
    st.session_state["h_status"] = "revisao_manual"
    st.session_state["h_busca"] = ""
    st.session_state["h_plataforma"] = []


if atencao:
    st.markdown(f"**{atencao} precisa{'m' if atencao != 1 else ''} de atenção** — "
                "confirme uma informação ou verifique se o envio saiu.")
    st.button(f"Ver {'as ' if atencao != 1 else 'a '}{atencao} no histórico",
              icon=":material/arrow_downward:", type="tertiary", on_click=_ver_atencao)

# ── O que aconteceu com cada uma ─────────────────────────────────────────────
# Um seletor por candidatura enviada. Mudar grava na hora; "sem resposta"
# desfaz. É a única contabilidade que pede que você volte à tela — e ela
# rende algo: o funil deixa de morrer em "enviada".

_ui.secao("O que aconteceu com cada uma")

with get_session() as session:
    # A data é a da candidatura registrada (pela esteira ou por "Já me
    # candidatei"), não a última mudança da vaga — a varredura de encerradas
    # também toca a vaga.
    ultima = (session.query(Candidatura.vaga_id,
                            func.max(Candidatura.criado_em).label("em"))
              .group_by(Candidatura.vaga_id).subquery())
    enviadas = (session.query(Vaga.id, Vaga.empresa, Vaga.titulo, ultima.c.em)
                .outerjoin(ultima, ultima.c.vaga_id == Vaga.id)
                .filter(Vaga.status.in_(acompanhamento.ENVIADAS))
                .order_by(ultima.c.em.desc().nullslast(), Vaga.id.desc()).all())
desfechos = acompanhamento.por_vaga([v[0] for v in enviadas])

OPCOES = [acompanhamento.SEM_RESPOSTA, "recebida", "resposta", "entrevista",
          "oferta", "recusa"]
_rotulo = {acompanhamento.SEM_RESPOSTA: acompanhamento.ROTULOS[None]}
_rotulo.update({d.value: r for d, r in acompanhamento.ROTULOS.items() if d})


def _rotulo_usuario(codigo: str) -> str:
    """Rótulo do catálogo sem o sufixo "(legado)": ele existe para o relatório
    do panorama separar as duas épocas (`test_todo_legado_esta_catalogado_com_rotulo`),
    mas para quem acompanha candidaturas é vocabulário de sistema."""
    return vocab.de_candidatura(codigo).rotulo.replace(" (legado)", "")


def _perguntas_do_erro(texto: str) -> list[str]:
    """`["Qual é a sua pretensão?", …]` → lista; qualquer outra coisa → []."""
    import json

    try:
        dados = json.loads(texto)
    except (TypeError, ValueError):
        return []
    return [str(q) for q in dados] if isinstance(dados, list) and dados else []


def _marcar(vaga_id: int, chave: str) -> None:
    valor = st.session_state[chave]
    acompanhamento.registrar(vaga_id, valor)
    # Gravar em silêncio deixava a dúvida "salvou?". O toast é o único feedback
    # que não empurra a lista.
    st.toast(f"Anotado: {_rotulo[valor]}.", icon=":material/check:")


if not enviadas:
    st.caption("Nenhuma candidatura enviada ainda.")
envios = st.container(key="envios")
for vaga_id, empresa, titulo, em in enviadas:
    atual = desfechos.get(vaga_id)
    chave = f"desfecho_{vaga_id}"
    with envios:
        esq, dir_ = st.columns([3.4, 1.6], vertical_alignment="center")
        with esq:
            quando = f"Enviada em {em.strftime('%d/%m')}" if em else "Enviada"
            st.markdown(
                f'<div class="vaga-empresa">{empresas.nome_exibicao(empresa) or empresa}</div>'
                f'<div style="font-weight:600;color:var(--txt-1)">{fila.titulo_exibicao(titulo)}</div>'
                f'<div class="meta-linha">{quando}</div>',
                unsafe_allow_html=True)
        with dir_:
            st.selectbox(
                "Resposta obtida", OPCOES,
                index=OPCOES.index(atual.value) if atual else 0,
                format_func=lambda c: _rotulo[c], key=chave,
                label_visibility="collapsed", on_change=_marcar, args=(vaga_id, chave),
            )

# ── Filtros ───────────────────────────────────────────────────────────────────

_ui.secao("Histórico")

TODOS = "Todos os status"
# Padrão: envios e o que pede atenção. "Preparada, não enviada" são 280 das
# 300 linhas — simulações do modo sombra — e escondiam as 11 que contam.
ENVIOS_E_ATENCAO = "Envios e atenção"
_ENVIOS = ("enviada_confirmada", "revisao_manual", "falha_automacao",
           "aguardando_verificacao", "enviada", "perguntas_pendentes")
_codigos = [s.codigo for s in vocab.CANDIDATURA]

# Chaves fixas: "Limpar filtros" zera as três num clique (mesmo padrão de Vagas).
_PADRAO_HIST = {"h_busca": "", "h_status": ENVIOS_E_ATENCAO, "h_plataforma": []}


def _limpar_historico() -> None:
    for chave, valor in _PADRAO_HIST.items():
        st.session_state[chave] = valor


f1, f2, f3 = st.columns([1.4, 1.3, 1.3])
with f1:
    busca = st.text_input("Buscar", placeholder="Vaga ou empresa",
                          label_visibility="collapsed", key="h_busca")
with f2:
    filtro_status = st.selectbox(
        "Status", [ENVIOS_E_ATENCAO, TODOS, *_codigos], label_visibility="collapsed",
        format_func=lambda c: c if c in (TODOS, ENVIOS_E_ATENCAO)
        else _rotulo_usuario(c), key="h_status")
with f3:
    filtro_plataforma = st.multiselect(
        "Plataforma", ["greenhouse", "gupy", "linkedin", "inhire"],
        placeholder="Plataforma", label_visibility="collapsed", key="h_plataforma")

with get_session() as session:
    q = (session.query(Candidatura, Vaga)
         .join(Vaga, Candidatura.vaga_id == Vaga.id))
    if filtro_status == ENVIOS_E_ATENCAO:
        q = q.filter(Candidatura.status.in_(_ENVIOS))
    elif filtro_status != TODOS:
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
              "Revise as vagas em Revisar para começar.")
    if busca or filtro_plataforma or filtro_status != ENVIOS_E_ATENCAO:
        st.button("Limpar filtros", icon=":material/filter_alt_off:",
                  type="tertiary", on_click=_limpar_historico)
    st.stop()

st.caption(f"{len(registros)} registro{'s' if len(registros) != 1 else ''}"
           + (" (máx. 300)" if len(registros) >= 300 else ""))

# ── Tabela ────────────────────────────────────────────────────────────────────
# Estruturada, não accordion: o ponto é comparar e localizar, não abrir uma a uma.

st.dataframe(
    [
        {
            "Vaga": fila.titulo_exibicao(r["titulo"]) or "—",
            "Empresa": empresas.nome_exibicao(r["empresa"]) or (r["empresa"] or "—"),
            # Plataforma é nível 3: fica no detalhe. Na tabela, o que decide é
            # vaga, empresa, status e quando.
            "Status": _rotulo_usuario(r["status"]),
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
        "Abrir": st.column_config.LinkColumn(display_text="Abrir vaga",
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
        st.markdown(_ui.badge(_rotulo_usuario(s.codigo), s.tom), unsafe_allow_html=True)
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
            # O applicator grava a lista de perguntas sem resposta como JSON
            # no campo `erro`. Para quem lê, é uma lista de perguntas — não
            # um array com aspas e colchetes.
            perguntas = _perguntas_do_erro(escolha["erro"])
            if perguntas:
                st.markdown(
                    f"**{len(perguntas)} pergunta{'s' if len(perguntas) != 1 else ''} "
                    f"ficara{'m' if len(perguntas) != 1 else ''} sem resposta:**\n"
                    + "\n".join(f"- {q}" for q in perguntas))
            else:
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
