"""Nome de empresa para exibição, a partir do slug do board.

O slug é chave de API, não nome: o Greenhouse devolve `c6bank`, `quintoandar`,
`gitlab`. Gravado como está, ele vazava direto para a carta de apresentação —
"Prezada equipe de c6bank" — em 74 das 299 cartas já geradas. Um recrutador lê
isso como formulário automático, que é exatamente a impressão que a carta existe
para evitar.

A estratégia é `.title()` com um mapa de exceções, e não um mapa completo das 157
empresas. Título simples já acerta a maioria — `twilio`, `airbnb`, `affirm`,
`datadog`, `intercom` — e um mapa de 157 linhas seria mais uma cópia para
divergir do `config.json` (invariante 11). O mapa aqui só carrega o que o
título erra, e cresce quando alguém notar um caso novo.

Correto de verdade seria ler o nome do próprio board na coleta, e é o caminho
quando o Módulo 17 (`Empresa`) existir. Até lá, isto é honesto sobre o que é:
uma heurística com escape manual.
"""
from __future__ import annotations

import re

#: Só o que `.title()` erra. Não repita aqui empresa de uma palavra que já sai
#: certa — entrada redundante é entrada que envelhece sem ninguém perceber.
EXCECOES = {
    "c6bank": "C6 Bank",
    "quintoandar": "QuintoAndar",
    "xpinc": "XP Inc",
    "pagbank": "PagBank",
    "picpay": "PicPay",
    "ifood": "iFood",
    "mercadolibre": "Mercado Libre",
    "gitlab": "GitLab",
    "github": "GitHub",
    "jfrog": "JFrog",
    "pagerduty": "PagerDuty",
    "vtex": "VTEX",
    "bigdatacorp": "BigDataCorp",
}

#: Slug costuma vir com separador. "acme-tech" e "acme_tech" viram "Acme Tech".
_SEPARADOR = re.compile(r"[-_.]+")


def nome_exibicao(slug: object) -> str:
    """Nome apresentável da empresa. Devolve `""` para entrada vazia.

    Quem chama decide o texto de fallback: a carta usa "a empresa", e um rótulo
    de tela pode preferir outra coisa. Devolver um fallback aqui esconderia a
    ausência de quem precisa tratá-la.
    """
    bruto = str(slug or "").strip()
    if not bruto:
        return ""

    chave = bruto.lower()
    if chave in EXCECOES:
        return EXCECOES[chave]

    # Nome já escrito por humano ("C6 Bank", "Stefanini Group") não é slug e não
    # deve ser reprocessado: `.title()` estragaria "iFood" e "XP Inc".
    if bruto != chave:
        return bruto

    partes = [p for p in _SEPARADOR.split(chave) if p]
    return " ".join(EXCECOES.get(p, p.title()) for p in partes)
