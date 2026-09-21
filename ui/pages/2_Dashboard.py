"""Início: o que você precisa fazer agora.

Terceira reescrita, e a razão é de produto, não de layout. A anterior tentava
provar que o sistema trabalha muito — 325 vagas, 104 possibilidades, fontes por
plataforma, 590 currículos, 566 cartas, execução manual. Nada disso muda uma
decisão. Quem abre esta página quer saber uma coisa: **o que eu tenho que fazer?**

Quatro blocos, nesta ordem, e só eles:

1. Quantas vagas precisam de você, e o botão que leva à fila.
2. A próxima — uma vaga, com o dossiê marcado como pronto, para começar já.
3. Suas candidaturas, num número — o único que o sistema sabe hoje.
4. Automação, numa linha, com o link para configurar.

O que saiu não sumiu: origem das vagas está em Vagas; documentos, na página
deles; ligar e desligar o envio, em Configurações → Automação. Contabilidade
que só serve ao sistema não é tédio que se mostra na primeira tela.
"""
import _bootstrap  # noqa: F401, I001  # antes de qualquer import de jobapplier
import _ui

import streamlit as st

from jobapplier.config.manager import ConfigManager

config = ConfigManager()

try:
    from sqlalchemy import func

    from jobapplier import acompanhamento, aderencia, fila, paths
    from jobapplier import envio_automatico as ea
    from jobapplier.database.connection import get_session
    from jobapplier.database.models import Vaga
except Exception as exc:
    st.error(f"Banco de dados indisponível: {exc}", icon=":material/error:")
    st.info("Execute `python run.py` para subir o Postgres e a aplicação.")
    st.stop()


@st.cache_data(ttl=30)
def _numeros() -> dict:
    """O pouco que esta página precisa, numa ida ao banco."""
    with get_session() as sessao:
        ultima_coleta = sessao.query(func.max(Vaga.ultima_coleta_em)).scalar()
    return {"ultima_coleta": ultima_coleta}


@st.cache_data(ttl=30)
def _fila() -> tuple[int, dict | None]:
    """Quantas precisam de você, e a primeira delas."""
    itens = fila.precisam_de_voce()
    proxima = None
    if itens:
        with get_session() as sessao:
            v = sessao.get(Vaga, itens[0].id)
            a = aderencia.analisar(v) if v else None
        proxima = {**itens[0].como_dict(),
                   "aderencia": a.como_dict() if a else None}
    return len(itens), proxima


def _primeiro_nome() -> str:
    import json

    try:
        nome = json.loads(paths.RESUME_JSON.read_text(encoding="utf-8")).get("nome", "")
    except (OSError, ValueError):
        nome = ""
    return (nome or "").split(" ")[0]


def _saudacao() -> str:
    from jobapplier.tempo import agora_utc

    # Hora local, não UTC: "bom dia" às 21h é o sistema falando de si.
    hora = agora_utc().astimezone().hour
    periodo = "Bom dia" if hora < 12 else "Boa tarde" if hora < 18 else "Boa noite"
    nome = _primeiro_nome()
    return f"{periodo}, {nome}." if nome else f"{periodo}."


numeros = _numeros()
quantas, proxima = _fila()

# ── 1. O que precisa de você ──────────────────────────────────────────────────

st.markdown(f'<div class="pg-titulo">{_saudacao()}</div>', unsafe_allow_html=True)
if quantas:
    st.markdown(
        f'<p class="lede">Você tem <b>{quantas} vaga{"s" if quantas != 1 else ""}</b> '
        f'para revisar.<br>Currículos, cartas e respostas já estão preparados.</p>',
        unsafe_allow_html=True,
    )
    with st.container(key="cta"):
        # O número vai no botão: "Revisar 42 vagas" é a ação, sem que o olho
        # precise voltar à frase para saber quanto é.
        st.page_link("pages/5_Aplicar.py",
                     label=f"Revisar {quantas} vaga{'s' if quantas != 1 else ''}",
                     icon=":material/arrow_forward:")
else:
    st.markdown('<p class="lede">Nada precisa de você agora.<br>'
                'O coletor segue rodando; volte mais tarde.</p>',
                unsafe_allow_html=True)

# ── 2. Próximo passo ──────────────────────────────────────────────────────────
# Uma só, e não uma lista: o CTA de cima leva à fila; este deixa começar pela
# recomendada sem passar por ela.

# É a vaga que o produto recomenda processar agora: merece ser a única coisa
# com borda na tela (contrato: cartão só para o protagonista).
if proxima:
    _ui.secao("Próximo passo")
    a = proxima.get("aderencia") or {}
    meta = " · ".join(p for p in (_ui.local_curto(proxima["localizacao"]),
                                  (proxima["modalidade"] or "").capitalize()) if p)
    prontos = " · ".join(
        f"✓ {nome}" for nome, ok in (("Currículo", proxima["tem_curriculo"]),
                                     ("Carta", proxima["tem_carta"])) if ok)
    with st.container(border=True, key="proximo"):
        st.markdown(
            f'<div class="vaga-empresa">{proxima["empresa_exibicao"]}</div>'
            f'<div class="destaque-titulo">{_ui.titulo_limpo(proxima["titulo"])}</div>'
            + (f'<div class="meta-linha">{meta}</div>' if meta else "")
            + (f'<div style="margin-top:var(--e3)">{_ui.conclusao(a)}</div>' if a else "")
            + (f'<div class="meta-linha" style="margin-top:var(--e2);color:var(--ok)">'
               f'{prontos}</div>' if prontos else ""),
            unsafe_allow_html=True,
        )
        st.page_link("pages/5_Aplicar.py", label="Revisar candidatura",
                     icon=":material/arrow_forward:")

# ── 3. Candidaturas ───────────────────────────────────────────────────────────

_ui.secao("Suas candidaturas")
# Os números vêm do que você marcou em Candidaturas (funil manual, por
# enquanto). "Aguardando" só aparece quando é diferente de "enviadas" — dois
# números iguais lado a lado era o pior dos mundos.
funil = acompanhamento.resumo()
resumo = [f"**{funil.enviadas} enviadas**"]
if funil.entrevistas:
    resumo.append(f"{funil.entrevistas} entrevista{'s' if funil.entrevistas != 1 else ''}")
if funil.com_resposta and funil.com_resposta != funil.entrevistas:
    resumo.append(f"{funil.com_resposta} com resposta")
st.markdown(" · ".join(resumo))
# O sistema não sabe se está "aguardando": sabe que ninguém marcou resposta.
if funil.enviadas and funil.com_resposta == 0 and funil.recusas == 0:
    st.markdown('<div class="meta-linha" style="color:var(--txt-2)">'
                'Ainda não identificamos respostas das empresas.<br>'
                'Você pode atualizar o status de cada uma em Candidaturas.</div>',
                unsafe_allow_html=True)
elif funil.aguardando:
    st.markdown(f'<div class="meta-linha" style="color:var(--txt-2)">'
                f'{funil.aguardando} sem resposta identificada.</div>',
                unsafe_allow_html=True)
st.page_link("pages/4_Candidaturas.py", label="Ver candidaturas",
             icon=":material/send:")

# ── 4. Automação ──────────────────────────────────────────────────────────────

_ui.secao("Automação")
ativa = ea.esta_ativo(config)
quando = numeros["ultima_coleta"]
coleta = (f"Última coleta {quando.strftime('%d/%m às %H:%M')}" if quando
          else "Nenhuma coleta ainda")
# Mesmo ponto da barra lateral (token, não emoji): âmbar quando ativa, porque
# com ela ligada coisas são enviadas em seu nome — é estado que pede atenção.
cor = "var(--aviso)" if ativa else "var(--ok)"
titulo = "Ativa" if ativa else "Modo sombra"
detalhe = (f"A IA encontra e prepara suas candidaturas. Vagas acima de "
           f"{ea.threshold_auto(config)}% podem ser enviadas automaticamente."
           if ativa else
           "A IA encontra e prepara suas candidaturas. Nada é enviado sem você.")
st.markdown(
    f'<div><span class="ponto" style="background:{cor};display:inline-block;'
    f'margin-right:.4rem"></span><b>{titulo}</b></div>'
    f'<div class="meta-linha" style="margin-top:var(--e2)">{detalhe}</div>'
    f'<div class="meta-linha">{coleta}</div>',
    unsafe_allow_html=True,
)
st.page_link("pages/1_Setup.py", label="Configurar automação",
             icon=":material/settings:")
