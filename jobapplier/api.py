"""API local para a extensão de navegador. Só escuta em 127.0.0.1.

O formulário de candidatura da Gupy fica atrás do login, e o login é protegido
por Cloudflare Turnstile que não serve o desafio a browser automatizado. Foi por
isso que 230 vagas da fila viraram "envio manual por design".

A extensão contorna isso sem contornar nada: ela roda **na sessão que o
candidato já autenticou**, no navegador dele. Não há login a automatizar, não há
detecção a evadir — é ele navegando, com ajuda.

**A divisão de trabalho.** A extensão é I/O: lê os campos do formulário e
escreve o que mandarem. Toda decisão sobre *o que* escrever fica aqui, no Python
que já tem teste — `_auto_answer`, o veto de pergunta sensível, a política de
pretensão, a régua de elegibilidade. Duplicar qualquer dessas regras em
JavaScript criaria a segunda cópia que este projeto passou o dia consertando.

**Por que as perguntas vêm da extensão e não do banco.** `questionForm` é `null`
na página pública da Gupy: as perguntas só existem depois do login. Então não há
o que pré-computar — a extensão lê o formulário real e pergunta como responder.
Sai mais robusto: funciona em qualquer plataforma sem mapa por site.

**Segurança.** Escuta só em loopback. As respostas carregam PII — CPF, telefone
— então expor em `0.0.0.0` publicaria isso na rede local. Há teste falhando se o
host padrão mudar.
"""
from __future__ import annotations

import json
import logging

from jobapplier import paths

logger = logging.getLogger(__name__)

#: Loopback, sempre. Ver a nota de segurança acima.
HOST = "127.0.0.1"
PORTA = 8787

#: Só as plataformas de vaga podem chamar. `*` deixaria qualquer página aberta
#: no navegador ler o CPF do candidato.
ORIGENS = [
    "https://*.gupy.io",
    "https://job-boards.greenhouse.io",
    "https://boards.greenhouse.io",
    "https://jobs.lever.co",
    "https://*.inhire.app",
    "https://www.linkedin.com",
]


def _resume() -> dict:
    return json.loads(paths.RESUME_JSON.read_text(encoding="utf-8"))


def _ids_gupy(url: str) -> set[int]:
    """`jobId` da Gupy, venha de onde vier na URL.

    O link do acervo é a página pública, `/job/<base64>`, onde o base64 é
    `{"jobId": 11510848, "source": "gupy_portal"}`. O formulário — que é onde a
    extensão roda — tem outra URL, e casar por prefixo devolvia 404 em toda vaga
    que o candidato de fato abriu. O `jobId` é o que sobrevive aos dois formatos
    e a cada passo do fluxo.
    """
    import base64
    from urllib.parse import urlsplit

    partes = [s for s in urlsplit(url or "").path.split("/") if s]
    ids: set[int] = set()
    for i, seg in enumerate(partes):
        if seg.isdigit():
            # Só numeral logo depois de `/job` ou `/jobs`. Aceitar qualquer
            # número do caminho lia `applications/749637585/steps/4205651511`
            # como dois candidatos a `jobId`: um acerto por coincidência
            # preencheria este formulário com a resposta de OUTRA vaga.
            if i and partes[i - 1] in ("job", "jobs"):
                ids.add(int(seg))
            continue
        try:
            bruto = base64.b64decode(seg + "=" * (-len(seg) % 4), validate=False)
            dados = json.loads(bruto)
        # Cego de propósito: quase todo segmento de caminho falha aqui, e falhar
        # é a resposta certa — "não é um jobId". Listar as exceções de
        # `b64decode` e `json.loads` seria precisão sem uso.
        except Exception:
            continue
        if isinstance(dados, dict) and str(dados.get("jobId", "")).isdigit():
            ids.add(int(dados["jobId"]))
    return ids


def _vaga_por_url(url: str):
    """Encontra a vaga pelo link.

    Duas passadas, da mais barata para a mais cara. Prefixo resolve Greenhouse e
    Lever, cujo link do formulário estende o da vaga. Não resolve a Gupy, e é aí
    que estão 230 das vagas da fila — por isso a segunda passada por `jobId`.
    """
    from sqlalchemy import or_

    from jobapplier.database.connection import get_session
    from jobapplier.database.models import Vaga

    limpo = (url or "").split("?")[0].rstrip("/")
    if not limpo:
        return None
    with get_session() as sessao:
        vaga = (sessao.query(Vaga)
                .filter(or_(Vaga.link == url, Vaga.link.like(f"{limpo}%")))
                .first())
        if vaga is None and (alvos := _ids_gupy(url)):
            # Só as vagas do mesmo subdomínio: é a empresa, e são poucas. Sem
            # isso seria decodificar o base64 do acervo inteiro a cada campo.
            from urllib.parse import urlsplit

            host = urlsplit(url).netloc
            candidatas = (sessao.query(Vaga)
                          .filter(Vaga.link.like(f"https://{host}/%")).all())
            vaga = next((v for v in candidatas if _ids_gupy(v.link) & alvos), None)
        if vaga is not None:
            sessao.expunge(vaga)
        return vaga


def referencia_externa(url: str) -> tuple[str, str] | None:
    """(plataforma, id da candidatura) a partir da URL do formulário.

    `https://x.gupy.io/candidates/applications/749637585/steps/…`
                                               └── é isto.
    """
    from urllib.parse import urlsplit

    partes = urlsplit(url or "")
    caminho = [s for s in partes.path.split("/") if s]
    if "gupy.io" in partes.netloc:
        for i, seg in enumerate(caminho[:-1]):
            if seg == "applications" and caminho[i + 1].isdigit():
                return "gupy", caminho[i + 1]
    return None


def _vinculo(sessao, url: str):
    from jobapplier.database.models import VinculoCandidatura

    ref = referencia_externa(url)
    if ref is None:
        return None
    return (sessao.query(VinculoCandidatura)
            .filter_by(plataforma=ref[0], referencia=ref[1]).one_or_none())


def _gravar_vinculo(sessao, url: str, vaga_id: int, origem: str) -> None:
    """Primeiro encontro manda. Um vínculo que veio de você (`origem='voce'`)
    nunca é sobrescrito por inferência — foi você quem viu a tela."""
    from jobapplier.database.models import VinculoCandidatura

    ref = referencia_externa(url)
    if ref is None:
        return
    existente = (sessao.query(VinculoCandidatura)
                 .filter_by(plataforma=ref[0], referencia=ref[1]).one_or_none())
    if existente is not None:
        if existente.origem == "voce" or origem != "voce":
            return
        existente.vaga_id, existente.origem = vaga_id, origem
        return
    sessao.add(VinculoCandidatura(plataforma=ref[0], referencia=ref[1],
                                  vaga_id=vaga_id, origem=origem))
    logger.info("Candidatura %s:%s vinculada à vaga %s (por %s).",
                ref[0], ref[1], vaga_id, origem)


def _candidatas(sessao, url: str, titulo_pagina: str = "") -> list:
    """Vagas plausíveis para esta URL, quando não dá para ter certeza.

    Serve ao desempate manual, não a um palpite: o PagBank tem duas vagas com o
    mesmo título, então a lista é oferecida para você escolher, nunca resolvida
    sozinha.
    """
    from urllib.parse import urlsplit

    from jobapplier.database.models import Vaga

    host = urlsplit(url or "").netloc
    if not host:
        return []
    return (sessao.query(Vaga)
            .filter(Vaga.link.like(f"https://{host}/%"))
            .order_by(Vaga.score.desc().nullslast())
            .limit(12).all())


def _resolver(sessao, url: str, sinais: dict):
    """(vaga, candidatas) — a vaga quando há certeza, senão o que oferecer.

    Cascata da certeza para a dúvida. Nunca deduz por título: repostagem com id
    novo é comum, e escolher a errada preencheria este formulário com a resposta
    de outra vaga.
    """
    from jobapplier.database.models import Vaga

    vaga = _vaga_por_url(url)                      # jobId na própria URL
    if vaga is not None:
        return vaga, []

    vinculo = _vinculo(sessao, url)                # já vinculada antes
    if vinculo is not None:
        alvo = sessao.get(Vaga, vinculo.vaga_id)
        if alvo is not None:
            sessao.expunge(alvo)
            return alvo, []

    for origem, valor in (("referrer", sinais.get("referrer", "")),
                          ("aba", sinais.get("vaga_da_aba", ""))):
        achada = _vaga_por_url(valor)
        if achada is not None:
            _gravar_vinculo(sessao, url, achada.id, origem)
            return achada, []

    return None, _candidatas(sessao, url, sinais.get("titulo", ""))


async def saude(request):
    from starlette.responses import JSONResponse

    return JSONResponse({"ok": True, "versao": 1})


async def identificar(request):
    """A vaga desta URL está no acervo? Devolve o que a extensão precisa mostrar."""
    from starlette.responses import JSONResponse

    vaga = _vaga_por_url(request.query_params.get("url", ""))
    if vaga is None:
        return JSONResponse({"conhecida": False}, status_code=404)

    pdfs = sorted(paths.RESUMES.glob(f"resume_*_{vaga.id}.pdf"))
    return JSONResponse({
        "conhecida": True,
        "id": vaga.id,
        "titulo": vaga.titulo,
        "empresa": vaga.empresa,
        "score": vaga.score,
        "status": vaga.status,
        "curriculo": pdfs[0].name if pdfs else None,
    })


async def responder(request):
    """Recebe os campos que a extensão leu e devolve o que escrever.

    Campo sem resposta volta com `valor: null` e vira pergunta manual — nunca um
    chute. É a invariante 3, e vale igual aqui e no applicator porque os dois
    chamam a mesma função.
    """
    from starlette.responses import JSONResponse

    from jobapplier.applicators.greenhouse import _auto_answer
    from jobapplier.config.manager import ConfigManager
    from jobapplier.database.connection import get_session

    corpo = await request.json()
    sinais = corpo.get("sinais") or {}
    url = corpo.get("url", "")

    with get_session() as sessao:
        vaga, candidatas = _resolver(sessao, url, sinais)
        # Materializa antes de sair da sessão: fora dela o objeto está expirado.
        opcoes = [{"id": v.id, "titulo": v.titulo, "empresa": v.empresa,
                   "score": v.score, "status": v.status} for v in candidatas]

    if vaga is None:
        # 409 e não 404: há vagas plausíveis, só não dá para saber qual. A
        # diferença importa porque a extensão oferece a escolha em vez de
        # desistir — e escolher sozinha preencheria o formulário de uma vaga
        # com as respostas de outra.
        logger.warning(
            "Extensão não identificou a vaga: %s | referrer=%s | título=%s "
            "| %d candidatas",
            url, sinais.get("referrer", "—"), sinais.get("titulo", "—"),
            len(opcoes))
        if opcoes:
            return JSONResponse({"erro": "vaga ambígua", "candidatas": opcoes},
                                status_code=409)
        return JSONResponse({"erro": "vaga desconhecida"}, status_code=404)

    normalizado = vaga.normalizado_json or {}
    if isinstance(normalizado, str):
        try:
            normalizado = json.loads(normalizado)
        except json.JSONDecodeError:
            normalizado = {}
    if not isinstance(normalizado, dict):
        normalizado = {}
    normalizado.setdefault("empresa", vaga.empresa)

    resume = _resume()
    dados = ConfigManager().get("dados_pessoais") or {}

    from jobapplier import aprendizado
    from jobapplier.database.connection import get_session

    respostas, manuais, aprendidas = [], [], 0
    with get_session() as sessao:
        for campo in corpo.get("campos") or []:
            rotulo = str(campo.get("label") or "")
            opcoes = campo.get("opcoes") or []
            valor = _auto_answer(
                rotulo,
                str(campo.get("tipo") or "input_text"),
                opcoes,
                resume, normalizado, dados,
            )
            # A política vem primeiro; o banco só entra onde ela não sabe. A
            # ordem importa: pretensão tem régua própria, e uma resposta antiga
            # sobrepondo a faixa atual repetiria o bug dos currículos-cópia.
            origem = "politica"
            if valor is None:
                valor = aprendizado.consultar(sessao, rotulo, vaga.empresa, opcoes)
                if valor is not None:
                    origem = "aprendida"
                    aprendidas += 1

            respostas.append({"label": rotulo, "seletor": campo.get("seletor"),
                              "valor": valor, "origem": origem})
            if valor is None and rotulo:
                manuais.append(rotulo)

    logger.info("Extensão pediu %d campos da vaga %s: %d respondidos "
                "(%d do banco de respostas).",
                len(respostas), vaga.id, len(respostas) - len(manuais), aprendidas)
    return JSONResponse({"vaga_id": vaga.id, "respostas": respostas,
                         "manuais": manuais, "aprendidas": aprendidas})


async def aprender(request):
    """Você digitou uma resposta à mão; o sistema guarda para a próxima vaga.

    É o que impede que "nome da mãe" seja redigitado nas 230 vagas da Gupy. Não
    fere a invariante 3: a resposta é sua, repetida literalmente — não há
    afirmação do sistema. O que governa onde ela pode ser repetida é a classe da
    pergunta, em `jobapplier/aprendizado.py`.
    """
    from starlette.responses import JSONResponse

    from jobapplier import aprendizado
    from jobapplier.database.connection import get_session

    corpo = await request.json()
    vaga = _vaga_por_url(corpo.get("url", ""))
    empresa = (vaga.empresa if vaga is not None else "") or ""

    gravadas = 0
    with get_session() as sessao:
        for campo in corpo.get("campos") or []:
            if aprendizado.registrar(sessao,
                                     str(campo.get("label") or ""),
                                     campo.get("valor"),
                                     empresa,
                                     campo.get("opcoes") or []):
                gravadas += 1
    return JSONResponse({"ok": True, "gravadas": gravadas})


async def vincular(request):
    """Você diz qual é a vaga; o sistema não pergunta de novo.

    É o desempate do caso que nenhuma inferência resolve: o PagBank tem duas
    vagas "Analista de Dados Pl." e a página do formulário não distingue. Origem
    `voce` porque foi você quem viu a tela — é o único vínculo que inferência
    nenhuma pode sobrescrever depois.
    """
    from starlette.responses import JSONResponse

    from jobapplier.database.connection import get_session
    from jobapplier.database.models import Vaga

    corpo = await request.json()
    url = corpo.get("url", "")
    vaga_id = corpo.get("vaga_id")
    if referencia_externa(url) is None:
        return JSONResponse({"erro": "url sem id de candidatura"}, status_code=400)

    with get_session() as sessao:
        if sessao.get(Vaga, vaga_id) is None:
            return JSONResponse({"erro": "vaga inexistente"}, status_code=404)
        _gravar_vinculo(sessao, url, int(vaga_id), "voce")
    return JSONResponse({"ok": True, "vaga_id": vaga_id})


async def curriculo(request):
    """Serve o PDF daquela vaga, para a extensão anexar."""
    from starlette.responses import FileResponse, JSONResponse

    vaga_id = request.path_params["vaga_id"]
    pdfs = sorted(paths.RESUMES.glob(f"resume_*_{vaga_id}.pdf"))
    if not pdfs:
        return JSONResponse({"erro": "sem currículo gerado"}, status_code=404)
    return FileResponse(pdfs[0], filename=pdfs[0].name,
                        media_type="application/pdf")


async def marcar_enviada(request):
    """Você enviou pelo navegador; o sistema registra.

    Sem isto o envio pela extensão seria invisível: `ja_candidatado()` não
    bloquearia um reenvio e o funil contaria a menos — foi exatamente o bug que
    `scripts/finalizar.py` teve por chamar o applicator direto.
    """
    from starlette.responses import JSONResponse

    from jobapplier.applicators.base import REVISAO_MANUAL
    from jobapplier.database.connection import get_session
    from jobapplier.database.models import Vaga
    from jobapplier.database.repository import CandidaturaRepository

    vaga_id = request.path_params["vaga_id"]
    with get_session() as sessao:
        if sessao.get(Vaga, vaga_id) is None:
            return JSONResponse({"erro": "vaga inexistente"}, status_code=404)
        # REVISAO_MANUAL e não ENVIADA_CONFIRMADA: quem afirma é o candidato, e
        # o sistema não viu a página de confirmação. Falso "enviada" é pior que
        # erro — bloqueia a vaga para sempre.
        # A procedência vai no texto e não numa coluna nova: `registrar` faz
        # `setattr` do que recebe, e um campo que não existe no modelo seria
        # aceito em silêncio e nunca gravado.
        CandidaturaRepository(sessao).registrar(
            vaga_id=vaga_id, status=REVISAO_MANUAL,
            erro="enviada por você pela extensão; sem prova na página")
        sessao.get(Vaga, vaga_id).status = "enviada_manual"
    return JSONResponse({"ok": True})


def criar_app():
    from starlette.applications import Starlette
    from starlette.middleware.cors import CORSMiddleware
    from starlette.routing import Route

    app = Starlette(routes=[
        Route("/saude", saude),
        Route("/vaga", identificar),
        Route("/responder", responder, methods=["POST"]),
        Route("/aprender", aprender, methods=["POST"]),
        Route("/vincular", vincular, methods=["POST"]),
        Route("/vaga/{vaga_id:int}/curriculo", curriculo),
        Route("/vaga/{vaga_id:int}/enviada", marcar_enviada, methods=["POST"]),
    ])
    app.add_middleware(
        CORSMiddleware, allow_origin_regex=r"https://([\w-]+\.)*"
        r"(gupy\.io|greenhouse\.io|lever\.co|inhire\.app|linkedin\.com)",
        allow_methods=["GET", "POST"], allow_headers=["*"])
    return app


def servir(host: str = HOST, porta: int = PORTA) -> None:
    import uvicorn

    logger.info("API da extensão em http://%s:%d", host, porta)
    uvicorn.run(criar_app(), host=host, port=porta, log_level="warning")
