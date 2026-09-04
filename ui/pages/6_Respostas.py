"""O que o sistema aprendeu com você, e como corrigir.

Sem esta tela o banco de respostas seria uma caixa-preta que grava para sempre:
uma resposta digitada errada no primeiro formulário se repetiria em todos os
seguintes, sem nada que a mostre. A memória só é aceitável se for revisável.

O escopo é a coluna que mais importa entender:

    global    a resposta é sobre VOCÊ — RG, idioma, autodeclaração. Vale em
              qualquer empresa, e é onde mora a economia de tédio.
    empresa   a pergunta é sobre a empresa ("por que aqui?"). Guardada por
              empresa de propósito: texto genérico reaproveitado é o que faz
              recrutador descartar.
"""
import _bootstrap  # noqa: F401, I001  # antes de qualquer import de jobapplier
import _ui

import streamlit as st

_ui.cabecalho(
    "Respostas aprendidas",
    "O que você digitou uma vez e o sistema repete. A resposta é sua — o "
    "sistema não inventa nenhuma, só repete literalmente o que você deu.",
)

try:
    from jobapplier.database.connection import get_session
    from jobapplier.database.models import RespostaAprendida
# Cego de propósito: sem banco a página não tem o que mostrar, e o motivo
# exato importa menos que o aviso na tela.
except Exception as exc:
    st.error(f"Banco indisponível: {exc}")
    st.stop()

with get_session() as sessao:
    linhas = (sessao.query(RespostaAprendida)
              .order_by(RespostaAprendida.vezes_usada.desc(),
                        RespostaAprendida.atualizado_em.desc()).all())
    dados = [{
        "id": r.id, "pergunta": r.pergunta, "resposta": r.resposta,
        "classe": r.classe, "escopo": r.escopo, "empresa": r.empresa,
        "vezes_usada": r.vezes_usada or 0,
    } for r in linhas]

if not dados:
    _ui.vazio(
        "Nada aprendido ainda",
        "Ao preencher à mão um campo que a extensão deixou em branco, a "
        "resposta aparece aqui e passa a ser reaproveitada na próxima vaga que "
        "fizer a mesma pergunta.",
    )
    st.stop()

economia = sum(d["vezes_usada"] for d in dados)
col1, col2, col3 = st.columns(3)
col1.metric("Respostas guardadas", len(dados))
col2.metric("Reaproveitamentos", economia,
            help="Quantas vezes uma resposta guardada preencheu um campo. É o "
                 "número de vezes que você não redigitou.")
col3.metric("Valem em qualquer empresa",
            sum(1 for d in dados if d["escopo"] == "global"))

st.divider()

editadas = st.data_editor(
    dados,
    column_config={
        "id": None,
        "pergunta": st.column_config.TextColumn("Pergunta", width="large",
                                                disabled=True),
        "resposta": st.column_config.TextColumn("Resposta", width="large"),
        "classe": st.column_config.TextColumn("Classe", disabled=True),
        "escopo": st.column_config.TextColumn("Escopo", disabled=True),
        "empresa": st.column_config.TextColumn("Empresa", disabled=True),
        "vezes_usada": st.column_config.NumberColumn("Usada", disabled=True),
    },
    hide_index=True, use_container_width=True, num_rows="dynamic",
    key="editor_respostas",
)

if st.button("Salvar alterações", type="primary"):
    por_id = {d["id"]: d for d in dados}
    restantes = {e["id"] for e in editadas if e.get("id") is not None}
    with get_session() as sessao:
        removidas = alteradas = 0
        for ident in por_id.keys() - restantes:
            alvo = sessao.get(RespostaAprendida, ident)
            if alvo is not None:
                sessao.delete(alvo)
                removidas += 1
        for editada in editadas:
            ident = editada.get("id")
            if ident is None or ident not in por_id:
                continue
            nova = str(editada.get("resposta") or "").strip()
            if nova == por_id[ident]["resposta"]:
                continue
            alvo = sessao.get(RespostaAprendida, ident)
            if alvo is None:
                continue
            # Esvaziar é apagar: guardar "" faria o banco responder nada em
            # todo formulário seguinte, em silêncio.
            if nova:
                alvo.resposta = nova
                alteradas += 1
            else:
                sessao.delete(alvo)
                removidas += 1
    st.success(f"{alteradas} alteradas, {removidas} apagadas.")
    st.rerun()
