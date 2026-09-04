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
    assert "status === 404" in conteudo, "vaga fora do acervo sem aviso próprio"
    assert "status === -1" in conteudo, "extensão desatualizada sem aviso próprio"


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
                       ("gupy.io", "greenhouse.io", "lever.co", "inhire.app"))


def test_backend_e_so_loopback():
    locais = [h for h in MANIFEST["host_permissions"] if h.startswith("http://")]
    assert locais == ["http://127.0.0.1:8787/*"], locais


def test_nao_pede_permissao_ampla():
    """`tabs` e `<all_urls>` dariam acesso ao que o candidato navega."""
    for perigosa in ("tabs", "webRequest", "cookies", "history", "<all_urls>"):
        assert perigosa not in MANIFEST["permissions"]


def test_manifest_v3():
    assert MANIFEST["manifest_version"] == 3
