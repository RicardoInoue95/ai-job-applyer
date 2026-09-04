"""Registro de plataformas: o que coleta, o que candidata, e por que não.

Fonte única de verdade. Antes a informação estava em três lugares que podiam
divergir — e divergiram: `applicators.PLATAFORMAS` dizia que a Gupy tinha
automação enquanto o applicator dela rejeitava 100% dos links; o coletor do
LinkedIn morava em `applicators/linkedin.py`, onde ninguém procura por coletor;
e a decisão de "baralho ou envio automático" estava implícita na ausência de uma
entrada num dicionário.

O contrato é o mesmo para toda plataforma nova:

    coleta      →  filtro 4A  →  normalização  →  filtro 4B  →  score
                →  dossiê (currículo + PDF + carta)
                →  envio automático, SE a plataforma permitir
                →  senão, baralho: você abre o link e envia

O que muda de uma para outra é só a **última linha**, e a razão de mudar precisa
estar escrita. Ausência de automação por decisão (CAPTCHA, risco de conta) é
diferente de ausência por não ter sido implementada — a primeira não deve ser
"corrigida" num turno futuro, a segunda sim.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Envio(StrEnum):
    """Como a candidatura sai desta plataforma."""

    #: O sistema preenche e submete o formulário.
    AUTOMATICO = "automatico"
    #: Baralho: o dossiê fica pronto e o usuário envia pelo link.
    MANUAL = "manual"
    #: Applicator ainda não escrito. Diferente de MANUAL, que é decisão.
    PENDENTE = "pendente"


@dataclass(frozen=True)
class Plataforma:
    codigo: str
    rotulo: str
    #: Módulo em `jobapplier/collectors/` com a classe de coleta.
    coletor: str | None
    envio: Envio
    #: Por que o envio não é automático. Obrigatório quando não é AUTOMATICO —
    #: sem isso a decisão vira folclore e alguém a desfaz sem saber o custo.
    motivo: str = ""
    #: Módulo em `jobapplier/applicators/`, quando há envio automático.
    applicator: str | None = None

    @property
    def automatiza(self) -> bool:
        return self.envio is Envio.AUTOMATICO

    @property
    def coleta(self) -> bool:
        return self.coletor is not None


REGISTRO: dict[str, Plataforma] = {
    "greenhouse": Plataforma(
        codigo="greenhouse", rotulo="Greenhouse",
        coletor="greenhouse", applicator="greenhouse",
        envio=Envio.AUTOMATICO,
    ),
    "gupy": Plataforma(
        codigo="gupy", rotulo="Gupy",
        coletor="gupy", envio=Envio.MANUAL,
        motivo=(
            "O login é protegido por Cloudflare Turnstile, que não serve o "
            "desafio a browser automatizado: o widget não carrega e o botão de "
            "acessar fica permanentemente desabilitado. Nem o login manual "
            "dentro do Playwright conclui. Fazer funcionar exigiria mascarar "
            "`navigator.webdriver` — evasão de detecção, que este projeto não "
            "faz. A coleta segue: a API pública não tem controle a contornar."
        ),
    ),
    "linkedin": Plataforma(
        codigo="linkedin", rotulo="LinkedIn",
        coletor="linkedin", envio=Envio.MANUAL,
        motivo=(
            "Automatizar Easy Apply viola o User Agreement e arrisca restrição "
            "permanente de uma conta que é a identidade profissional real do "
            "usuário (invariante 6). A coleta é opt-in e depende de sessão "
            "salva por login manual."
        ),
    ),
    "lever": Plataforma(
        codigo="lever", rotulo="Lever",
        coletor="lever", envio=Envio.MANUAL,
        applicator="lever",
        motivo=(
            "Módulo 14 implementado, mas **assistido, não automático** — e a "
            "razão corrige o que este registro afirmava. Dizia-se aqui que o "
            "Lever era 'mesma família do Greenhouse: público, sem login, sem "
            "CAPTCHA', e era essa frase que o fazia parecer o melhor retorno por "
            "hora disponível. É falsa. Medido no formulário real de "
            "`jobs.lever.co/<slug>/<id>/apply`: `<div class=\"h-captcha\">` com "
            "sitekey, dois iframes do hCaptcha, campo oculto "
            "`h-captcha-response` e JavaScript que prende o botão de envio até "
            "existir token. O widget é renderizado, não é script carregado à toa."
            "\n\n"
            "O applicator preenche tudo — nome, contato, localização com "
            "autocomplete, empregador, links, currículo — e para no desafio, "
            "devolvendo AGUARDANDO_VERIFICACAO. Quem conclui é "
            "`scripts/finalizar.py`, com navegador visível."
            "\n\n"
            "Volume segue baixo: sondagem de 22 slugs devolveu 2 aderentes ao "
            "perfil de dados, e `coleta.empresas_lever` está vazio. O applicator "
            "existe para quando aparecer."
        ),
    ),
    "inhire": Plataforma(
        codigo="inhire", rotulo="inhire",
        coletor="inhire", envio=Envio.MANUAL,
        motivo=(
            "Coleta implementada: `api.inhire.app/job-posts/public/pages` com "
            "header `x-tenant`, sem autenticação. **Envio é manual, decidido por "
            "ensaio**: carregada só para observação, a página traz reCAPTCHA "
            "(14 ocorrências no HTML) e monta o formulário por JavaScript, sem "
            "nenhum campo no DOM inicial. Contornar o reCAPTCHA está fora de "
            "questão, e sem isso o applicator só produziria erro."
            "\n\n"
            "Volume não muda a conta: são 8 vagas no acervo inteiro contra 12 "
            "mil do Greenhouse. Mas as da Radix têm os melhores scores da fila "
            "(88, 87.6, 81.8), então o dossiê pronto vale — é o envio que é seu."
        ),
    ),
}


def obter(codigo: str) -> Plataforma | None:
    return REGISTRO.get((codigo or "").lower())


def com_automacao() -> list[str]:
    return [p.codigo for p in REGISTRO.values() if p.automatiza]


def com_coleta() -> list[str]:
    return [p.codigo for p in REGISTRO.values() if p.coleta]


def motivo_sem_automacao(codigo: str) -> str:
    """Por que esta plataforma não candidata sozinha. Vazio se ela candidata."""
    p = obter(codigo)
    if p is None:
        return f"Plataforma '{codigo}' não está no registro."
    return "" if p.automatiza else p.motivo
