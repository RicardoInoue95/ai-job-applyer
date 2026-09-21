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

    from jobapplier import aderencia, fila, paths
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
        enviadas = (sessao.query(func.count(Vaga.id))
                    .filter(Vaga.status.in_(("candidatada", "enviada_manual")))
                    .scalar() or 0)
        # "Aguardando retorno" honesto: enviadas sem evento registrado. Como a
        # tabela `eventos` ainda não é alimentada, hoje é igual a "enviadas" —
        # e a frase diz isso em vez de fingir um funil.
        ultima_coleta = sessao.query(func.max(Vaga.ultima_coleta_em)).scalar()
    return {"enviadas": enviadas, "ultima_coleta": ultima_coleta}


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

st.markdown(f"## {_saudacao()}")
if quantas:
    st.markdown(
        f"**{quantas} vaga{'s' if quantas != 1 else ''} "
        f"precisa{'m' if quantas != 1 else ''} da sua atenção.** "
        "A IA já preparou currículo, carta e respostas."
    )
    with st.container(key="cta"):
        st.page_link("pages/5_Aplicar.py", label="Revisar vagas",
                     icon=":material/rate_review:")
else:
    st.markdown("**Nada precisa de você agora.** "
                "O coletor segue rodando; volte mais tarde.")

# ── 2. Próximo passo ──────────────────────────────────────────────────────────
# Uma só, e não uma lista: o CTA de cima leva à fila; este deixa começar pela
# recomendada sem passar por ela.

if proxima:
    _ui.secao("Próximo passo")
    a = proxima.get("aderencia") or {}
    st.markdown(f"**{proxima['empresa_exibicao']}**")
    st.markdown(f"### {_ui.titulo_limpo(proxima['titulo'])}")
    meta = " · ".join(p for p in (proxima["modalidade"], proxima["localizacao"]) if p)
    if meta:
        st.caption(meta)
    if a:
        st.markdown(f"**{a['titulo']}** — {a['porque']}")
        if a.get("atencao"):
            st.markdown(f"⚠ {a['atencao']}")
    prontos = " ".join(
        f"{nome} ✓" for nome, ok in (("Currículo", proxima["tem_curriculo"]),
                                     ("Carta", proxima["tem_carta"])) if ok)
    if prontos:
        st.caption(prontos)
    st.page_link("pages/5_Aplicar.py", label="Revisar esta candidatura",
                 icon=":material/arrow_forward:")

# ── 3. Candidaturas ───────────────────────────────────────────────────────────

_ui.secao("Candidaturas")
# Um número só. O desenho previa "11 enviadas · 3 aguardando retorno", mas o
# sistema ainda não lê respostas por e-mail e não distingue as duas coisas —
# dois números iguais lado a lado era o pior dos mundos. Quando a leitura de
# e-mail existir, o segundo número entra com dado de verdade.
st.markdown(f"### {numeros['enviadas']}")
st.caption("enviadas · o sistema ainda não identifica respostas, então todas "
           "contam como aguardando retorno")
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
texto = (f"<b>Ativa.</b> A IA encontra, prepara e — acima de "
         f"{ea.threshold_auto(config)}% em plataformas com automação — envia em "
         f"seu nome. {coleta}." if ativa else
         f"<b>Modo sombra.</b> A IA encontra e prepara; nada é enviado sem você. "
         f"{coleta}.")
st.markdown(f'<span class="ponto" style="background:{cor};display:inline-block;'
            f'margin-right:.4rem"></span>{texto}', unsafe_allow_html=True)
st.page_link("pages/1_Setup.py", label="Configurar automação",
             icon=":material/settings:")
