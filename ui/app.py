"""Entrada da aplicação: navegação, identidade e estado do sistema.

Passou de redirecionador de três linhas para o dono da navegação. O motivo é o
que o usuário lê na barra lateral: com a descoberta automática de `pages/`, o
Streamlit deriva os rótulos dos nomes de arquivo — "app", "Setup", "Aplicar" —
e não aceita ícone. Era nome de arquivo virando interface.

Com `st.navigation` os rótulos são escolhidos ("Configurações", "Revisar e
aplicar"), os ícones são Material de verdade, e a guarda de configuração
incompleta fica num lugar só em vez de repetida no topo de cada página.

`st.set_page_config` também é chamado só aqui — com navegação explícita, as
páginas não podem mais chamá-lo.
"""
import _bootstrap  # noqa: F401, I001  # antes de qualquer import de jobapplier
import _ui

import streamlit as st

from jobapplier.config.manager import ConfigManager

st.set_page_config(
    page_title="AI Job Applier",
    page_icon=":material/work:",
    layout="wide",
    initial_sidebar_state="expanded",
)

_ui.aplicar()

config = ConfigManager()
configurado = config.is_setup_complete()

# ── Páginas ──────────────────────────────────────────────────────────────────
# Os arquivos continuam em `pages/` (os testes de contrato os leem de lá), mas
# quem define título e ícone é esta lista.

CONFIGURACOES = st.Page("pages/1_Setup.py", title="Configurações",
                        icon=":material/settings:", url_path="configuracoes")
INICIO = st.Page("pages/2_Dashboard.py", title="Início",
                 icon=":material/home:", url_path="inicio", default=True)
VAGAS = st.Page("pages/3_Vagas.py", title="Vagas",
                icon=":material/work_outline:", url_path="vagas")
CANDIDATURAS = st.Page("pages/4_Candidaturas.py", title="Candidaturas",
                       icon=":material/send:", url_path="candidaturas")
# Documentos continua acessível pela URL e por link dentro do produto, mas sai
# da navegação: é acervo, não decisão. "Tenho 590 documentos" não é o que
# ninguém quer pensar — "minha candidatura para a X está pronta" é.
DOCUMENTOS = st.Page("pages/7_Documentos.py", title="Currículos e cartas",
                     icon=":material/description:", url_path="documentos")


def _revisar_com_contador() -> "st.Page":
    """"Revisar · 14": o contador na barra é a informação mais poderosa que a
    navegação pode dar — "tenho 14 coisas para decidir" sem entrar em lugar
    nenhum. Sem banco, o rótulo fica sem número, não sem página."""
    try:
        from jobapplier import fila

        n = len(fila.precisam_de_voce())
        titulo = f"Revisar · {n}" if n else "Revisar"
    except Exception:
        titulo = "Revisar"
    return st.Page("pages/5_Aplicar.py", title=titulo,
                   icon=":material/rate_review:", url_path="revisar")


# A jornada, não o sistema: Início → Vagas → Revisar → Candidaturas. O resto
# existe, mas não na barra. Sem configuração completa a única página é o wizard.
if configurado:
    paginas = {
        "": [INICIO, VAGAS, _revisar_com_contador(), CANDIDATURAS],
        "Mais": [CONFIGURACOES, DOCUMENTOS],
    }
else:
    paginas = [CONFIGURACOES]

# ── Identidade ───────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(
        '<div class="marca"><div class="marca-nome">AI Job Applier</div>'
        '<div class="marca-sub">Suas vagas em um lugar só</div></div>',
        unsafe_allow_html=True,
    )

pagina = st.navigation(paginas, position="sidebar")

# ── Estado do sistema, no rodapé da barra ────────────────────────────────────
# Modo sombra é a informação que muda a leitura de tudo: com ele ligado, nada é
# enviado. Ficava só numa legenda no meio do Dashboard, onde some.

if configurado:
    with st.sidebar:
        try:
            from jobapplier import envio_automatico as ea

            ativo = ea.esta_ativo(config)

            # Uma linha. A versão anterior tinha três — rótulo, explicação e
            # data — e era o elemento mais pesado da barra. O estado importa
            # (com envio ativo, coisas são enviadas em seu nome); a explicação
            # cabe no Início, onde há espaço para dizê-la.
            cor = "var(--aviso)" if ativo else "var(--ok)"
            rotulo = "Automação ativa" if ativo else "Modo sombra"
            st.markdown(
                f'<div class="rodape"><div class="rodape-linha">'
                f'<span class="ponto" style="background:{cor}"></span>{rotulo}'
                f'</div></div>',
                unsafe_allow_html=True,
            )
        except Exception:
            # Rodapé é informação de apoio: banco fora do ar não pode impedir a
            # navegação, e a página em si já reporta o erro com contexto.
            st.markdown(
                '<div class="rodape"><div class="rodape-linha">'
                '<span class="ponto" style="background:var(--txt-3)"></span>'
                'Estado indisponível</div></div>',
                unsafe_allow_html=True,
            )

pagina.run()
