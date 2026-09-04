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
DASHBOARD = st.Page("pages/2_Dashboard.py", title="Dashboard",
                    icon=":material/home:", url_path="dashboard", default=True)
VAGAS = st.Page("pages/3_Vagas.py", title="Vagas",
                icon=":material/work_outline:", url_path="vagas")
CANDIDATURAS = st.Page("pages/4_Candidaturas.py", title="Candidaturas",
                       icon=":material/send:", url_path="candidaturas")
APLICAR = st.Page("pages/5_Aplicar.py", title="Revisar e aplicar",
                  icon=":material/rate_review:", url_path="revisar")

# Sem configuração completa não há o que navegar: a única página é o wizard.
paginas = ([DASHBOARD, VAGAS, APLICAR, CANDIDATURAS, CONFIGURACOES]
           if configurado else [CONFIGURACOES])

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
            from jobapplier.database.connection import get_session
            from jobapplier.database.models import Vaga

            ativo = ea.esta_ativo(config)
            with get_session() as sessao:
                ultima = (sessao.query(Vaga.ultima_coleta_em)
                          .order_by(Vaga.ultima_coleta_em.desc()).first())

            cor = "var(--aviso)" if ativo else "var(--ok)"
            rotulo = "Envio automático ativo" if ativo else "Modo sombra ativo"
            detalhe = ("candidaturas são enviadas em seu nome" if ativo
                       else "nada é enviado sem você")
            quando = (ultima[0].strftime("%d/%m às %H:%M")
                      if ultima and ultima[0] else "—")

            st.markdown(
                f'<div class="rodape">'
                f'<div class="rodape-linha">'
                f'<span class="ponto" style="background:{cor}"></span>{rotulo}</div>'
                f'<div class="rodape-linha" style="padding-left:1.1rem">{detalhe}</div>'
                f'<div class="rodape-linha" style="margin-top:.35rem">'
                f'Última coleta: {quando}</div></div>',
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
