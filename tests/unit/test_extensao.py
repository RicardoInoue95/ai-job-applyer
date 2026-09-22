"""A extensão preenche e para. Nunca envia.

Preencher formulário na sessão que o candidato já abriu é assistência: não há
login a automatizar nem detecção a evadir — é ele navegando, com ajuda. Submeter
por ele é o que o CAPTCHA e o termo de uso da plataforma existem para impedir.

A diferença mora em duas linhas de JavaScript, e estes testes as guardam.
"""
import json
import re
from pathlib import Path

import pytest

EXT = Path(__file__).resolve().parents[2] / "extensao"
MANIFEST = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))


def _codigo(arquivo: str) -> str:
    """Sem comentário: o cabeçalho descreve o que NÃO se faz, e uma checagem de
    substring reprovaria a explicação."""
    js = (EXT / arquivo).read_text(encoding="utf-8")
    sem_bloco = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    # Só comentário de linha inteira. Cortar todo `//` engolia o de
    # `http://127.0.0.1:8787` e o teste passava a reprovar a própria URL do
    # backend que ele existe para exigir.
    return "\n".join("" if ln.lstrip().startswith("//") else ln
                     for ln in sem_bloco.splitlines())


# ── Nunca envia ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("arquivo", ["conteudo.js", "campos.js", "fundo.js"])
def test_nao_submete_formulario(arquivo):
    codigo = _codigo(arquivo)
    for proibido in (".submit()", "requestSubmit", "form.submit"):
        assert proibido not in codigo, f"{arquivo}: {proibido} envia a candidatura"


def test_o_unico_clique_e_em_radio():
    """`alvo.click()` marca uma opção — é preenchimento. Qualquer outro clique
    precisaria de justificativa, e botão de envio não tem nenhuma."""
    cliques = [ln.strip() for ln in _codigo("conteudo.js").splitlines()
               if ".click()" in ln]
    assert len(cliques) == 1, cliques
    # Compara o começo da linha: o comentário inline que explica por que é
    # `click()` e não `.checked` fica depois, e é legítimo.
    assert cliques[0].startswith("alvo.click();"), cliques[0]


def test_nao_resolve_desafio():
    codigo = _codigo("conteudo.js") + _codigo("campos.js") + _codigo("fundo.js")
    for proibido in ("2captcha", "anticaptcha", "capsolver", "hcaptcha",
                     "grecaptcha", "navigator.webdriver"):
        assert proibido not in codigo.lower()


# ── A decisão fica no Python ──────────────────────────────────────────────────

def test_pergunta_ao_backend_em_vez_de_decidir():
    assert "sendMessage" in _codigo("conteudo.js")
    assert "/responder" in _codigo("fundo.js")


def test_quem_chama_a_api_e_o_service_worker():
    """No Manifest V3 o `fetch` de um content script obedece ao CSP da PÁGINA, e
    o `connect-src` da Gupy não inclui `127.0.0.1` — a requisição morria antes
    de sair e o aviso culpava o backend, que estava no ar. O service worker roda
    na origem da extensão e não é regido pelo CSP do site."""
    assert "127.0.0.1:8787" in _codigo("fundo.js")
    assert "127.0.0.1" not in _codigo("conteudo.js"), (
        "o content script voltou a falar com a API direto; o CSP da página "
        "vai bloquear e o erro parecerá backend fora do ar")
    assert MANIFEST["background"]["service_worker"] == "fundo.js"


def test_service_worker_mantem_o_canal_aberto():
    """`onMessage` sem `return true` fecha o canal antes do await, e a resposta
    se perde em silêncio."""
    assert "return true" in _codigo("fundo.js")


def test_o_aviso_distingue_a_causa_da_falha():
    """Uma mensagem só para três falhas mandou reiniciar um serviço que estava
    no ar, enquanto o problema era a URL do formulário não bater com a do banco.
    O status vem do service worker justamente para separá-las."""
    worker = _codigo("fundo.js")
    assert "e.status" in worker or "erro.status" in worker, (
        "o service worker engoliu o status; 404 e backend fora do ar chegam "
        "iguais ao aviso")
    conteudo = _codigo("conteudo.js")
    # A distinção por causa mudou de lugar, não sumiu: o texto de cada falha
    # vem do catálogo do Python (`jobapplier/erros.py`), que sabe qual foi.
    assert "avisoDoErro" in conteudo, "o aviso não lê o erro do backend"
    assert "erro.acao" in conteudo, (
        "o aviso mostra o que houve e não o que fazer — a ação é a metade que "
        "importa para quem está cansado")
    # Os dois que o backend NÃO pode informar, porque nos dois ele não respondeu.
    assert "status === -1" in conteudo, "service worker mudo sem aviso próprio"
    assert "api-fora" in conteudo, "API fora do ar sem aviso próprio"


def test_a_extensao_nao_reescreve_mensagem_do_catalogo():
    """Mensagem duplicada em JavaScript diverge do backend no primeiro dia.
    Fora os três erros locais — os que acontecem quando o Python não responde —
    nenhum texto de erro nasce aqui."""
    conteudo = _codigo("conteudo.js")
    locais = conteudo[conteudo.index("const LOCAIS"):conteudo.index("function erroDaFalha")]
    fora = conteudo.replace(locais, "")
    for proibido in ("Vaga fora do acervo", "não achou esta vaga",
                     "Rode `python run.py`", "chrome://extensions"):
        assert proibido not in fora, f"texto de erro fixo no JS: {proibido}"


def test_o_aviso_nao_realimenta_o_observador():
    """`aviso()` recriava o elemento a cada chamada, o MutationObserver via a
    mutação como mudança de formulário e chamava `preencher()` de novo: 1,2
    requisição por segundo, para sempre, medido no log da API."""
    codigo = _codigo("conteudo.js")
    assert "AVISO.isConnected" in codigo, (
        "o aviso voltou a ser recriado a cada chamada")
    assert 'getElementById("aija-aviso")?.remove()' not in codigo


def test_404_nao_e_repetido():
    """Vaga fora do acervo não passa a estar porque perguntamos de novo."""
    codigo = _codigo("conteudo.js")
    assert "desistidas" in codigo


def test_campo_sem_resposta_nao_e_preenchido():
    """`valor: null` vem da API quando a política proíbe responder — sensível,
    pergunta composta, fato que o currículo não sustenta. O cliente respeita."""
    codigo = _codigo("conteudo.js")
    assert "=== null" in codigo or "== null" in codigo


# ── Escopo ────────────────────────────────────────────────────────────────────

def test_so_roda_em_plataforma_de_vaga():
    """`<all_urls>` deixaria a extensão ler qualquer página aberta."""
    for bloco in MANIFEST["content_scripts"]:
        for padrao in bloco["matches"]:
            assert padrao != "<all_urls>"
            assert any(p in padrao for p in
                       ("gupy.io", "greenhouse.io", "lever.co", "inhire.app",
                        "linkedin.com/in/", "linkedin.com/jobs/"))


# ── LinkedIn: perfil (leitura) e Easy Apply (assistido) ──────────────────────
# Duas permissões em linkedin.com, cada uma para uma coisa: `/in/*` lê o perfil
# do candidato quando ele clica; `/jobs/*` preenche o Easy Apply e anexa o
# currículo — no clique, sem enviar, sem "Avançar". A invariante 6 proíbe
# AUTOMATIZAR o Easy Apply (e fazer login); preencher a sessão que o candidato
# abriu é o mesmo modelo assistido da Gupy. Decisão do usuário em 22/09/2026.

def _blocos_linkedin():
    return [b for b in MANIFEST["content_scripts"]
            if any("linkedin" in m for m in b["matches"])]


def test_linkedin_so_perfil_e_vagas():
    blocos = _blocos_linkedin()
    assert blocos, "linkedin não está registrado"
    for bloco in blocos:
        for padrao in bloco["matches"]:
            if "linkedin" not in padrao:
                continue
            assert padrao in ("https://www.linkedin.com/in/*",
                              "https://www.linkedin.com/jobs/*"), padrao
    for host in MANIFEST["host_permissions"]:
        if "linkedin" in host:
            assert host in ("https://www.linkedin.com/in/*",
                            "https://www.linkedin.com/jobs/*"), host


def test_no_perfil_so_o_leitor_e_nas_vagas_so_o_preenchimento():
    """`linkedin.js` (lê o perfil) nunca carrega em /jobs; `conteudo.js`
    (preenche) nunca carrega em /in."""
    for bloco in _blocos_linkedin():
        if any(m.endswith("/in/*") for m in bloco["matches"]):
            assert bloco["js"] == ["linkedin.js"], bloco["js"]
        if any(m.endswith("/jobs/*") for m in bloco["matches"]):
            assert "linkedin.js" not in bloco["js"]
            assert "conteudo.js" in bloco["js"]


def test_no_easy_apply_le_so_o_dialogo_e_nao_avanca():
    """A página de vagas tem busca, filtros e mensagens — todos <input>. Só o
    diálogo do Easy Apply é formulário. E nenhum botão dele é clicado: nem
    "Avançar", nem "Revisar", nem "Enviar candidatura"."""
    codigo = _codigo("conteudo.js")
    assert "raizDoFormulario" in codigo
    assert 'div[role=dialog]' in codigo
    for proibido in ("Avançar", "Next", "Review", "Submit application",
                     "Enviar candidatura", "artdeco-button--primary",
                     "aria-label=\"Continue", "footer button"):
        assert proibido not in codigo, f"conteudo.js clica em {proibido!r}"


def test_curriculo_entra_pelo_campo_de_arquivo_sem_clique():
    """O PDF vai pelo `DataTransfer` + `change`, como um arrasto — não por
    clique no botão de upload da plataforma. O único clique segue sendo o do
    radio (`test_o_unico_clique_e_em_radio`)."""
    codigo = _codigo("conteudo.js")
    assert "new DataTransfer()" in codigo
    assert "campo.files = dt.files" in codigo
    assert 'tipo: "curriculo"' in codigo
    # Vários campos de arquivo: só o que fala em currículo; nunca o primeiro.
    assert "curr[i" in codigo and "resume" in codigo
    # Quem busca o PDF é o service worker (CSP), e ele não toca no DOM.
    fundo = _codigo("fundo.js")
    assert "/curriculo`" in fundo
    assert "document." not in fundo


def test_leitor_de_perfil_nao_preenche_nem_clica():
    codigo = _codigo("linkedin.js")
    for proibido in (".click()", ".submit()", "requestSubmit", ".value =",
                     "dispatchEvent", "easy-apply", "jobs-apply"):
        assert proibido not in codigo, f"linkedin.js: {proibido}"
    for proibido in ("2captcha", "anticaptcha", "hcaptcha", "grecaptcha",
                     "navigator.webdriver"):
        assert proibido not in codigo.lower()


def test_leitor_de_perfil_so_le_sozinho_o_proprio_perfil():
    """Leitura sem clique só acontece depois de conferir, com o backend, que o
    slug da página é o do candidato e que a última leitura está velha. Perfil de
    terceiro nunca é lido sem clique — e com clique a API recusa (403)."""
    codigo = _codigo("linkedin.js")
    assert 'addEventListener("click"' in codigo
    assert "lerPerfil()" in codigo
    # A única chamada de envio vive em `analisar`, que o clique e a leitura
    # automática compartilham.
    envios = [ln for ln in codigo.splitlines()
              if "sendMessage" in ln and "perfil_linkedin" in ln]
    assert len(envios) == 1, envios
    # A automática pergunta ao backend qual é o slug e compara com a página.
    auto = codigo[codigo.index("async function lerSozinhoSeForMeuEVelho"):]
    auto = auto[:auto.index("if (E_PERFIL)")]
    assert '"situacao_perfil"' in auto
    assert "meuSlug" in auto and "daPagina" in auto
    assert "daPagina.toLowerCase() !== meuSlug" in auto
    assert "dias_para_reler" in auto


def test_backend_e_so_loopback():
    locais = [h for h in MANIFEST["host_permissions"] if h.startswith("http://")]
    assert locais == ["http://127.0.0.1:8787/*"], locais


def test_nao_pede_permissao_ampla():
    """`tabs` e `<all_urls>` dariam acesso ao que o candidato navega."""
    for perigosa in ("tabs", "webRequest", "cookies", "history", "<all_urls>"):
        assert perigosa not in MANIFEST["permissions"]


def test_manifest_v3():
    assert MANIFEST["manifest_version"] == 3


# ── Sintaxe ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("arquivo", ["conteudo.js", "campos.js", "fundo.js", "linkedin.js"])
def test_javascript_compila(arquivo):
    """Erro de sintaxe num content script não aparece em lugar nenhum: nem no
    console da página, nem no aviso — a extensão simplesmente não faz nada. Uma
    quebra de linha que devia ser `\n` custou uma rodada inteira de depuração."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node não instalado")
    r = subprocess.run([node, "--check", str(EXT / arquivo)],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
