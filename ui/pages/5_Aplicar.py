"""Baralho de candidatura: um cartão por vez, decisão rápida.

A tela que o resto do projeto serve. As três esteiras existem para chegar aqui:
uma vaga por vez, já pontuada, com o currículo reescrito para ela, a carta e as
respostas do formulário prontas. Ele lê, decide, abre o link e envia.

Por que baralho e não lista: a decisão é binária e repetitiva — vale ou não vale
a pena aplicar. Uma lista de 150 linhas convida a rolar sem decidir nada; um
cartão por vez força a decisão e registra o que já foi visto, que é o que
transforma 150 vagas paradas em uma fila que anda.

Nada aqui envia nada. O envio é ele, no site, com a ficha aberta ao lado.
"""
import _bootstrap  # noqa: F401, I001  # antes de qualquer import de jobapplier
import _ui

import json

import streamlit as st

from jobapplier.config.manager import ConfigManager


config = ConfigManager()

try:
    from jobapplier import aderencia, empresas, paths
    from jobapplier import ficha as mod_ficha
    from jobapplier import fila as fila_mod
    from jobapplier.database.connection import get_session
    from jobapplier.database.models import Vaga
except Exception as exc:
    st.error(f"Não foi possível carregar o backend: {exc}")
    st.stop()


#: Status que entram no baralho. 'pendente' é a possibilidade de score baixo:
#: entra na fila mas o slider padrão (65) a esconde — aparece quando você
#: baixa o filtro, não por padrão. Score nunca rejeita (ver CLAUDE.md).
NA_FILA = ("pronta_envio_manual", "aprovada", "pronta_para_revisao", "pendente")

# ── Dados ─────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def carregar_fila(plataformas: tuple, score_min: int, modalidades: tuple,
                  cidades: tuple) -> list[dict]:
    """Vagas da fila, como dicts — objetos ORM não sobrevivem ao cache."""
    with get_session() as sessao:
        consulta = (sessao.query(Vaga)
                    .filter(Vaga.status.in_(NA_FILA))
                    .order_by(Vaga.score.desc().nullslast()))
        if plataformas:
            consulta = consulta.filter(Vaga.plataforma.in_(plataformas))
        linhas = consulta.all()

    from jobapplier import documentos

    com_curriculo = {d.vaga_id for d in documentos.listar() if d.curriculo}

    fila = []
    for v in linhas:
        if (v.score or 0) < score_min:
            continue
        # "não informada" é opção de filtro, não ausência: 30% da fila não
        # declara modalidade, e escondê-las por omissão sumiria com um terço
        # das vagas sem o usuário entender por quê.
        modo = v.modalidade or "não informada"
        if modalidades and modo not in modalidades:
            continue
        if cidades and _cidade(v.localizacao) not in cidades:
            continue
        fila.append({
            "aderencia": aderencia.analisar(v).como_dict(),
            "tem_curriculo": v.id in com_curriculo,
            "id": v.id, "titulo": v.titulo, "empresa": v.empresa,
            "plataforma": v.plataforma, "link": v.link, "score": v.score or 0,
            "localizacao": v.localizacao, "modalidade": v.modalidade,
            "status": v.status, "descricao": v.descricao,
            "normalizado_json": v.normalizado_json,
            "breakdown": v.score_breakdown_json,
        })
    return fila


def _cidade(localizacao: str | None) -> str:
    """Primeiro segmento do local, normalizado para virar opção de filtro.

    Os dados vêm de três plataformas e cada uma escreve do seu jeito: a fila
    real tinha "São Paulo" (71) e "Sao Paulo" (3) como opções separadas, e
    dezesseis vagas remotas espalhadas em "Remote", "Remote - USA", "Remote US"
    e "Remote - US". Sem juntar, o usuário precisa marcar quatro caixas para
    dizer uma coisa só — e provavelmente marca uma e perde as outras doze.
    """
    import unicodedata

    bruto = (localizacao or "").split(",")[0].strip()
    if not bruto:
        return "não informada"

    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", bruto.lower())
        if unicodedata.category(c) != "Mn"
    )
    if sem_acento.startswith(("remote", "remoto")):
        return "Remoto"
    return _CIDADES_CANONICAS.get(sem_acento, bruto)


#: Grafias que aparecem no corpus para a mesma cidade.
_CIDADES_CANONICAS = {
    "sao paulo": "São Paulo",
    "rio de janeiro": "Rio de Janeiro",
    "belo horizonte": "Belo Horizonte",
    "brasil": "Brasil (não especificado)",
    "brazil": "Brasil (não especificado)",
}


@st.cache_data(ttl=120)
def opcoes_de_filtro() -> tuple[list[str], list[str]]:
    """Modalidades e cidades que existem na fila, com quantas vagas cada uma.

    Vêm do banco, não de lista fixa: filtro que oferece opção sem resultado faz
    o usuário achar que a fila está vazia quando ele é que filtrou demais.
    """
    from collections import Counter

    with get_session() as sessao:
        linhas = (sessao.query(Vaga.modalidade, Vaga.localizacao)
                  .filter(Vaga.status.in_(NA_FILA)).all())

    modos = Counter(m or "não informada" for m, _ in linhas)
    cidades = Counter(_cidade(loc) for _, loc in linhas)
    return (
        [m for m, _ in modos.most_common()],
        [c for c, n in cidades.most_common(12) if n >= 2],
    )


def decidir(vaga_id: int, novo_status: str, status_anterior: str) -> None:
    """Aplica a decisão e guarda o suficiente para desfazer.

    Toda decisão tira a vaga da fila — por isso não existe índice a persistir:
    o cartão atual é sempre o primeiro, e fechar o navegador não perde nada. A
    versão anterior guardava a posição em `session_state`, que morre com a aba,
    e quem parava na vaga 40 voltava para a 1.
    """
    with get_session() as sessao:
        sessao.query(Vaga).filter(Vaga.id == vaga_id).update({"status": novo_status})
    st.session_state["ultima_decisao"] = (vaga_id, status_anterior, novo_status)
    st.session_state["decididas_hoje"] = st.session_state.get("decididas_hoje", 0) + 1
    carregar_fila.clear()
    opcoes_de_filtro.clear()


def desfazer() -> None:
    """Devolve a última vaga decidida ao status em que estava."""
    ultima = st.session_state.get("ultima_decisao")
    if not ultima:
        return
    vaga_id, status_anterior, _ = ultima
    with get_session() as sessao:
        sessao.query(Vaga).filter(Vaga.id == vaga_id).update(
            {"status": status_anterior})
    st.session_state.pop("ultima_decisao", None)
    st.session_state["decididas_hoje"] = max(
        0, st.session_state.get("decididas_hoje", 1) - 1)
    carregar_fila.clear()
    opcoes_de_filtro.clear()


@st.cache_data(ttl=300)
def carregar_ficha(vaga_id: int) -> dict:
    """Perguntas do formulário com as respostas que temos. Toca a rede."""
    with get_session() as sessao:
        vaga = sessao.query(Vaga).filter(Vaga.id == vaga_id).first()
        if vaga is None:
            return {"situacao": "erro", "itens": []}
        sessao.expunge(vaga)

    resume = json.loads(paths.RESUME_JSON.read_text(encoding="utf-8"))
    f = mod_ficha.montar(vaga, resume, config.load())
    return {
        "situacao": f.situacao, "detalhe": f.detalhe,
        "respondidas": f.respondidas, "total": f.total,
        "itens": [
            {"pergunta": i.pergunta, "resposta": i.resposta,
             "obrigatoria": i.obrigatoria, "eliminatoria": i.eliminatoria,
             "confirmar": i.exige_confirmacao, "opcoes": i.opcoes,
             "origem": i.origem}
            for i in f.itens
        ],
    }


def documentos(vaga_id: int) -> tuple[object, str]:
    """(caminho do PDF ou None, texto da carta)."""
    pdf = next(paths.RESUMES.glob(f"*_{vaga_id}.pdf"), None)
    carta_path = paths.COVER_LETTERS / f"cover_letter_{vaga_id}.txt"
    carta = carta_path.read_text(encoding="utf-8") if carta_path.exists() else ""
    return pdf, carta


# ── Cabeçalho e filtros ───────────────────────────────────────────────────────
# Os filtros saíram da barra lateral: lá é navegação do produto, e misturar
# filtro de uma página com o menu fazia parecer que valiam para todas.

# O padrão da fila é o MESMO conjunto do contador da barra ("Revisar · 42"):
# excelentes com dossiê pronto. A versão anterior abria com "287 vagas para
# revisar" — o corte de 65 — ao lado de uma barra que dizia 42, e começava
# por uma vaga sem currículo gerado. Baixar o corte continua possível, no
# filtro; o que muda é o ponto de partida.
corte_padrao = fila_mod.corte_de_atencao()

_ui.cabecalho("Revisar", "A IA encontrou e preparou. Falta a sua decisão.")

modos_disponiveis, cidades_disponiveis = opcoes_de_filtro()

with st.expander("Filtros", expanded=False):
    f1, f2, f3, f4 = st.columns([1.1, 1, 1.2, 1])
    with f1:
        plataformas = st.multiselect(
            "Plataforma", ["gupy", "greenhouse", "linkedin", "inhire"],
            default=["gupy", "greenhouse", "inhire"], placeholder="Todas")
    with f2:
        modalidades = st.multiselect("Modalidade", modos_disponiveis,
                                     placeholder="Todas")
    with f3:
        cidades = st.multiselect("Localização", cidades_disponiveis,
                                 placeholder="Todas")
    with f4:
        score_min = st.slider("Aderência mínima", 0, 100, corte_padrao, step=5,
                              help="Abaixo do padrão entram as vagas boas mas "
                                   "não excelentes — e as possibilidades.")
        so_prontas = st.toggle("Só com dossiê pronto", value=True)

fila = carregar_fila(tuple(plataformas), score_min, tuple(modalidades),
                     tuple(cidades))
if so_prontas:
    fila = [v for v in fila if v["tem_curriculo"]]
feitas = st.session_state.get("decididas_hoje", 0)

if not fila:
    if feitas:
        _ui.vazio("Revisão concluída",
                  f"Você revisou {feitas} vaga(s) nesta sessão.")
    else:
        _ui.vazio("Nenhuma vaga com esses filtros",
                  "Afrouxe um filtro, reduza a aderência mínima ou colete "
                  "vagas novas em Configurações → Automação.")
    st.stop()

# Sempre a primeira: toda decisão remove a vaga da fila, então não há índice
# para guardar nem posição para perder entre sessões.
vaga = fila[0]

# "217 vagas para revisar" em vez de "faltam 217": mesmo número, sem a
# conotação de dívida acumulada.
restantes = len(fila)
progresso = f"{restantes} vaga{'s' if restantes != 1 else ''} para revisar"
if feitas:
    progresso += f"  ·  {feitas} revisada{'s' if feitas != 1 else ''} nesta sessão"
st.caption(progresso)

if st.session_state.get("ultima_decisao") and st.button(
        "Desfazer última decisão", icon=":material/undo:"):
    desfazer()
    st.rerun()


# ── Duas colunas ──────────────────────────────────────────────────────────────
# A decisão precisa da vaga E do material preparado ao mesmo tempo. Empilhado
# numa coluna estreita, ver a ficha exigia rolar e perder o cartão de vista.

# 60/40: a esquerda decide, a direita é a candidatura pronta.
coluna_vaga, coluna_apoio = st.columns([1.5, 1], gap="large")

with coluna_vaga:
    plataforma = (vaga["plataforma"] or "").title()
    local = _ui.local_curto(vaga["localizacao"]) or "Local não informado"
    modo = (vaga["modalidade"] or "").capitalize()
    normalizado = (vaga["normalizado_json"]
                   if isinstance(vaga["normalizado_json"], dict) else {})
    senioridade = normalizado.get("senioridade") or ""

    meta = _ui.linha_meta(
        _ui.badge(plataforma),
        f"<span>{local}</span>",
        f"<span>{modo}</span>" if modo else "",
        f"<span>{senioridade}</span>" if senioridade else "",
    )
    st.markdown(
        '<div class="cartao">'
        f'<div class="vaga-empresa">'
        f'{empresas.nome_exibicao(vaga["empresa"]) or vaga["empresa"] or "—"}</div>'
        '<div class="vaga-titulo" style="font-size:1.28rem;margin:.2rem 0 .1rem">'
        f'{_ui.titulo_limpo(vaga["titulo"]) or "—"}</div>'
        f'{meta}'
        f'<div style="margin-top:.7rem">{_ui.conclusao(vaga["aderencia"])}</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Ação principal em índigo; descarte discreto. O vermelho fica reservado a
    # erro e bloqueio — usá-lo em botão comum torna o vermelho real invisível.
    # Uma primária, larga. Duas secundárias na linha de baixo. "Deixar para
    # depois" não é ação equivalente às outras — é adiar a decisão — e por
    # isso não ganha botão do mesmo peso.
    st.write("")
    # "Abrir candidatura", não "Abrir e candidatar": o botão abre o site e
    # registra que você abriu; quem envia é você, lá. O nome não pode prometer
    # o que o sistema não faz (Finalidade: honestidade sobre o limite).
    st.link_button("Abrir candidatura", vaga["link"] or "#",
                   icon=":material/open_in_new:", type="primary",
                   use_container_width=True)
    b1, b2 = st.columns(2)
    with b1:
        if st.button("Já me candidatei", icon=":material/check:",
                     use_container_width=True):
            decidir(vaga["id"], "enviada_manual", vaga["status"])
            st.rerun()
    with b2:
        if st.button("Não tenho interesse", icon=":material/close:",
                     use_container_width=True):
            decidir(vaga["id"], "descartada_por_voce", vaga["status"])
            st.rerun()
    if st.button("Deixar para depois", icon=":material/schedule:", type="tertiary",
                 help="Sai da fila principal e fica guardada. Não se perde."):
        decidir(vaga["id"], "adiada", vaga["status"])
        st.rerun()

    # ── Por que combina (nível 2: evidência) ────────────────────────────────
    # O cartão já deu a conclusão. Aqui as barras por eixo e as tecnologias —
    # para quem quer conferir, não para quem quer decidir.
    if vaga["aderencia"]:
        _ui.secao("Por que combina")
        _ui.evidencia(vaga["aderencia"])

    if vaga["descricao"]:
        with st.expander("Descrição completa da vaga"):
            st.write(vaga["descricao"][:6000])

    # ── A seguir ─────────────────────────────────────────────────────────────
    # Compacta de propósito: saber o que vem evita descartar uma vaga mediana
    # por medo de que seja a última boa, sem competir com a vaga atual.
    proximas = fila[1:4]
    if proximas:
        _ui.secao("A seguir")
        for prox in proximas:
            st.markdown(
                "<div style='font-size:.82rem;color:var(--txt-3);padding:.1rem 0'>"
                f"<span class='num'>{prox['score']:.0f}%</span> · "
                f"{(prox['titulo'] or '')[:48]} — {prox['empresa'] or '—'}</div>",
                unsafe_allow_html=True,
            )

with coluna_apoio, st.container(key="lado"):
    pdf, carta = documentos(vaga["id"])

    # A coluna direita é a candidatura pronta, como checklist: currículo,
    # carta, formulário — cada um com "✓" ou com o que falta. O texto da carta
    # fica atrás de um clique: é nível 2, e aberto por padrão ocupava metade
    # da coluna com um texto que se lê uma vez.
    _ui.secao("Sua candidatura")
    with st.spinner("Lendo o formulário da vaga…"):
        f = carregar_ficha(vaga["id"])

    linhas_check = []
    linhas_check.append(("Currículo", bool(pdf),
                         "adaptado para esta vaga" if pdf else "ainda não gerado"))
    linhas_check.append(("Carta", bool(carta),
                         "gerada" if carta else "não gerada — é opcional"))
    if f["situacao"] == "sem_suporte":
        linhas_check.append(("Formulário", None, "não sei ler o desta plataforma"))
    elif f["situacao"] != "ok":
        linhas_check.append(("Formulário", None, "não consegui ler"))
    elif not f["itens"]:
        linhas_check.append(("Formulário", True, "nenhuma pergunta adicional"))
    else:
        faltam = f["total"] - f["respondidas"]
        linhas_check.append(("Formulário", faltam == 0,
                             f"{f['respondidas']} de {f['total']} respondidas"
                             + (f" · {faltam} sua{'s' if faltam != 1 else ''}" if faltam else "")))

    for nome, ok, nota in linhas_check:
        marca = ("✓" if ok else "—") if ok is not None else "?"
        cor = "var(--ok)" if ok else ("var(--txt-3)" if ok is None else "var(--aviso)")
        st.markdown(
            f'<div style="display:flex;gap:.6rem;align-items:baseline;'
            f'padding:.35rem 0;border-bottom:1px solid var(--borda)">'
            f'<span style="color:{cor};font-weight:650;width:1rem">{marca}</span>'
            f'<span style="color:var(--txt-1);font-weight:550;width:6.5rem">{nome}</span>'
            f'<span style="color:var(--txt-3);font-size:var(--txt-apoio)">{nota}</span></div>',
            unsafe_allow_html=True,
        )

    # Uma frase de conclusão do checklist, e as ações como links: a decisão
    # mora na coluna da esquerda; aqui é evidência de que está pronto.
    tudo_pronto = all(ok for _, ok, _ in linhas_check if ok is not None) and pdf
    st.markdown(
        '<div class="meta-linha" style="margin:var(--e3) 0 var(--e2);color:var(--txt-2)">'
        + ("Tudo preparado para esta vaga." if tudo_pronto else
           "Falta algo — veja acima o que ainda não está pronto.")
        + "</div>", unsafe_allow_html=True)
    if pdf:
        st.download_button("Baixar currículo", pdf.read_bytes(),
                           file_name=pdf.name, mime="application/pdf",
                           icon=":material/download:", type="tertiary")

    if f["situacao"] == "ok" and f["itens"]:
        with st.expander(f"Perguntas do formulário ({f['total']})"):
            for item in f["itens"]:
                marca = ""
                if item["eliminatoria"]:
                    marca = _ui.badge("eliminatória", "erro") + " "
                elif item["obrigatoria"]:
                    marca = _ui.badge("obrigatória", "aviso") + " "
                st.markdown(
                    f"{marca}<span style='font-size:.9rem;color:var(--txt-1);"
                    f"font-weight:550'>{item['pergunta']}</span>",
                    unsafe_allow_html=True,
                )
                if item["resposta"] and item["confirmar"]:
                    st.warning(f"Sugestão: **{item['resposta']}** — confirme antes "
                               "de enviar, esta resposta pode eliminar você.",
                               icon=":material/priority_high:")
                elif item["resposta"]:
                    st.code(item["resposta"], language=None)
                else:
                    opcoes = (" · opções: " + ", ".join(item["opcoes"])
                              if item["opcoes"] else "")
                    st.caption(f"Sem resposta automática — responda você{opcoes}")

    if carta:
        # Um trecho para reconhecer, o resto atrás de um clique.
        # O segundo parágrafo, não a saudação: é onde a carta diz quem você é.
        paragrafos = [p.strip() for p in carta.strip().split("\n\n") if p.strip()]
        trecho = paragrafos[1] if len(paragrafos) > 1 else (paragrafos[0] if paragrafos else "")
        if len(trecho) > 200:
            trecho = trecho[:200].rstrip() + "…"
        st.caption(f"“{trecho}”")
        with st.expander("Ler carta completa"):
            st.text_area("carta", carta, height=320, label_visibility="collapsed",
                         key=f"carta_{vaga['id']}")


