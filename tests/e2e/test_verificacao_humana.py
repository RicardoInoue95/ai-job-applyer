"""A detecção do passo de verificação, contra o HTML real da plataforma.

Esta é a camada que pega quebra de seletor, e ela pegou uma de verdade: a
primeira versão procurava `input[name*='security_code']`, e o formulário da
Adyen usa oito caixas de um caractere com `id="security-input-0"` até `-7`,
**sem atributo `name`**. O texto era detectado, o campo não, e como a checagem
exige os dois, a Adyen continuava classificada como falha técnica — que era o
bug que o status novo existia para corrigir.

A fixture veio de captura real em `data/screenshots/falhas/`, reduzida ao bloco
de verificação e com o e-mail trocado por um de exemplo.
"""
import pytest

from jobapplier.applicators.greenhouse import _pede_verificacao_humana

pytestmark = pytest.mark.e2e


def test_detecta_no_html_real(carregar_fixture):
    page = carregar_fixture("greenhouse_verificacao.html")
    assert _pede_verificacao_humana(page, page.content().lower())


def test_acha_as_oito_caixas(carregar_fixture):
    page = carregar_fixture("greenhouse_verificacao.html")
    assert len(page.query_selector_all("input[id^='security-input']")) == 8


def test_preenche_uma_letra_por_caixa(carregar_fixture):
    """O código de 8 caracteres vai um por campo, na ordem."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from finalizar import preencher_codigo

    page = carregar_fixture("greenhouse_verificacao.html")
    assert preencher_codigo(page, "7K2M9XQP")
    lido = "".join(page.input_value(f"#security-input-{i}") for i in range(8))
    assert lido == "7K2M9XQP"


def test_pagina_sem_verificacao_nao_dispara(carregar_fixture):
    """Falso positivo bloquearia a vaga para retentativa automática para sempre."""
    page = carregar_fixture("greenhouse_form.html")
    assert not _pede_verificacao_humana(page, page.content().lower())
