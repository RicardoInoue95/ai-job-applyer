"""Leitura do código de verificação — o que pode e o que não pode vazar.

Este módulo lê a caixa de e-mail do candidato, que é o acesso mais amplo que o
projeto já pediu. Os testes cobrem as três coisas que o tornam aceitável: o
código certo é encontrado, o código errado não é inventado, e o código nunca
escapa para log.

Sem rede: `extrair_codigo` recebe texto, e o caminho IMAP é testado só na recusa
por falta de configuração.
"""
import ast
import logging

import pytest

from jobapplier import verificacao
from jobapplier.verificacao import Achado, extrair_codigo

EMAIL_ADYEN = """
Hi Ricardo,

A verification code was sent to confirm your application to Adyen.
Your security code is 7K2M9XQP

To submit your application, enter the 8-character code to confirm you're a human.
"""

EMAIL_SEIS_DIGITOS = """
Seu código de verificação é 481920. Ele expira em 10 minutos.
"""


def test_acha_codigo_alfanumerico_de_oito():
    assert extrair_codigo(EMAIL_ADYEN) == "7K2M9XQP"


def test_acha_codigo_numerico_de_seis():
    assert extrair_codigo(EMAIL_SEIS_DIGITOS) == "481920"


def test_exige_contexto_perto_do_candidato():
    """Um e-mail de candidatura tem vários trechos de 8 maiúsculos — id de vaga,
    hash de rastreamento. Pegar o primeiro daria um código errado com convicção."""
    sem_contexto = ("Application ABCD1234 received for position XYZW9876 "
                    "at company QRST5555. Thank you for applying.")
    assert extrair_codigo(sem_contexto) is None


def test_prefere_o_que_tem_contexto_e_nao_o_primeiro():
    texto = ("Reference ZZZZ0000 for your records. "
             "Your verification code is 7K2M9XQP and expires soon.")
    assert extrair_codigo(texto) == "7K2M9XQP"


@pytest.mark.parametrize("vazio", ["", None, "   "])
def test_texto_vazio_nao_inventa_codigo(vazio):
    assert extrair_codigo(vazio) is None


def test_texto_sem_codigo_nenhum():
    assert extrair_codigo("Obrigado por se candidatar. Boa sorte!") is None


# ── O código não pode vazar ───────────────────────────────────────────────────

def test_repr_do_achado_esconde_o_codigo():
    """`logger.info("%s", achado)` e um traceback com locais são as duas formas
    fáceis de o código parar em data/logs/*.jsonl (invariante 11)."""
    a = Achado(codigo="7K2M9XQP", remetente="greenhouse.io", assunto="Verify")
    assert "7K2M9XQP" not in repr(a)
    assert "oculto" in repr(a)


def test_busca_nao_loga_o_codigo(caplog, monkeypatch):
    """A mensagem de log conta quantos remetentes tinham código, nunca qual."""
    monkeypatch.setattr(verificacao, "credenciais",
                        lambda config=None: ("u@x.com", "senha", "imap.x"))

    class _ConexaoFake:
        def login(self, *a): pass
        def select(self, *a, **k): pass
        def search(self, *a): return "OK", [b""]
        def logout(self): pass

    monkeypatch.setattr(verificacao.imaplib, "IMAP4_SSL",
                        lambda servidor: _ConexaoFake())
    with caplog.at_level(logging.INFO):
        verificacao.buscar_codigo()
    assert "7K2M9XQP" not in caplog.text
    assert "senha" not in caplog.text


# ── Configuração ──────────────────────────────────────────────────────────────

def test_sem_configuracao_recusa_com_instrucao(monkeypatch):
    """Erro que não diz o que fazer vira ticket. Este diz."""
    monkeypatch.setattr(verificacao, "credenciais",
                        lambda config=None: (None, None, "imap.gmail.com"))
    with pytest.raises(verificacao.VerificacaoIndisponivel) as exc:
        verificacao.buscar_codigo()
    texto = str(exc.value)
    assert "AIJOB_IMAP_USER" in texto
    assert "senha de app" in texto
    assert "Nunca use a senha da conta" in texto


def test_configurado_reflete_as_credenciais(monkeypatch):
    monkeypatch.setattr(verificacao, "credenciais",
                        lambda config=None: (None, None, "h"))
    assert verificacao.configurado() is False
    monkeypatch.setattr(verificacao, "credenciais",
                        lambda config=None: ("u", "p", "h"))
    assert verificacao.configurado() is True


def test_credencial_nao_cai_para_config_json():
    """Invariante 5: segredo novo só no .env. Este é o mais sensível do projeto
    — dá leitura da caixa inteira — e `data/config.json` já guarda CPF em texto
    plano; somar a senha ali aumentaria o estrago de um vazamento."""
    import inspect

    fonte = inspect.getsource(verificacao.credenciais)
    # `obter(nome, *caminho_config)`: sem caminho, não há fallback para o JSON.
    for chamada in ('obter("IMAP_USER"', 'obter("IMAP_PASS"'):
        assert chamada in fonte
        trecho = fonte[fonte.index(chamada):]
        assert trecho[: trecho.index(")")].count(",") <= 1, (
            "credencial de IMAP não pode ter caminho no config.json")


# ── O módulo não submete nada ─────────────────────────────────────────────────

def test_modulo_so_le():
    """A linha do desenho: ler o código é assistência; clicar em enviar sem o
    humano é o que o controle existe para impedir. Quem submete é
    `scripts/finalizar.py`, com navegador visível e o clique do candidato."""
    import inspect

    fonte = inspect.getsource(verificacao)
    for proibido in ("click(", "submit(", "goto(", "sync_playwright"):
        assert proibido not in fonte, f"{proibido} não pertence a este módulo"
    assert "readonly=True" in fonte, "a caixa tem de ser aberta somente leitura"


@pytest.mark.parametrize("texto,esperado", [
    # O caso real do rodapé: id de rastreamento antes, código depois.
    ("Reference ZZZZ0000 for your records. Your verification code is 7K2M9XQP.",
     "7K2M9XQP"),
    # Contexto longe demais não vale: o id não vira código por proximidade vaga.
    ("Job ABCD1234 was posted. " + "filler " * 30 + "Your code is 7K2M9XQP.",
     "7K2M9XQP"),
    # Código antes da palavra, redação menos comum mas existente.
    ("7K2M9XQP is your security code.", "7K2M9XQP"),
])
def test_escolhe_o_candidato_colado_ao_contexto(texto, esperado):
    assert extrair_codigo(texto) == esperado


def test_id_distante_do_contexto_nao_vira_codigo():
    """Fronteira do alcance: sem isso, qualquer e-mail longo com um id em cima e
    a palavra "code" no rodapé preencheria o campo com o id."""
    texto = "Reference ZZZZ0000. " + ("texto neutro " * 40) + "verification code below."
    assert extrair_codigo(texto) != "ZZZZ0000"


# ── O script que confere a configuração ───────────────────────────────────────
# "Configurei e não sei se funcionou" é o pior estado: a sessão assistida
# seguiria pedindo o código à mão e o registro de desfecho ficaria vazio, sem
# nada dizendo por quê.

def _fonte_checador() -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parents[2] / "scripts" / "checar_imap.py"
            ).read_text(encoding="utf-8")


def test_checador_e_valido():
    ast.parse(_fonte_checador())


def test_checador_nao_imprime_segredo():
    """Nenhum `print` do script menciona a variável da senha nem a do código.

    A checagem é literal de propósito. Tentei antes um transformer de AST que
    perdoava `len(senha)` e depois `senha if ... else`, perseguindo o código com
    esperteza crescente. O certo era o contrário: o script calcula a descrição
    da senha ANTES do print, e aí a regra simples basta.
    """
    arvore = ast.parse(_fonte_checador())
    for no in ast.walk(arvore):
        if not (isinstance(no, ast.Call) and isinstance(no.func, ast.Name)
                and no.func.id == "print"):
            continue
        impresso = ast.dump(ast.Module(body=[ast.Expr(a) for a in no.args],
                                       type_ignores=[]))
        assert "id='senha'" not in impresso, f"linha {no.lineno}: imprime a senha"
        assert "attr='codigo'" not in impresso, f"linha {no.lineno}: imprime o código"


def test_checador_ensina_o_caminho_da_senha_de_app():
    """Erro que não diz o que fazer vira ticket. Este diz, com a URL."""
    fonte = _fonte_checador()
    assert "apppasswords" in fonte
    assert "NUNCA a senha da conta" in fonte
    assert "duas etapas" in fonte


def test_checador_distingue_as_causas():
    """Senha errada, IMAP bloqueado e rede caída pedem ações diferentes."""
    fonte = _fonte_checador().lower()
    assert "authenticationfailed" in fonte
    assert "timed out" in fonte
