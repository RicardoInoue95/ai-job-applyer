"""Renderização e verificação de layout de PDF.

Regra do projeto: **todo PDF gerado é renderizado em imagem e verificado.** PDFs
anteriores saíram com erro de layout que passou despercebido porque ninguém
olhava o resultado — o currículo ia para o recrutador quebrado.

Duas camadas, e as duas importam:

1. ``verificar_layout`` — checagens automáticas sobre a geometria do texto
   (transbordo de margem, sobreposição, página vazia, glifo faltante). Roda em
   toda geração, em produção, e nos testes. Pega regressão sem ninguém olhar.
2. ``renderizar`` — PNG por página, para inspeção humana. Automático não substitui
   o olho: espaçamento feio, hierarquia visual ruim e cor ilegível passam por
   qualquer assert.

Renderizador é o **pypdfium2** (Apache-2.0 / BSD-3), não PyMuPDF. PyMuPDF é AGPL,
o que seria um problema se o projeto virar produto — e o objetivo declarado é
permitir monetização futura.
"""
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DPI_PADRAO = 110

#: Margem útil da página em pontos. O gerador usa 1.4cm ≈ 40pt; a tolerância
#: aqui é mais frouxa para não acusar arredondamento do próprio ReportLab.
MARGEM_TOLERANCIA_PT = 8.0

#: Um currículo de uma a duas páginas é o esperado. Três já indica que a
#: otimização inflou o conteúdo; acima disso é erro de layout.
MAX_PAGINAS_ESPERADO = 3

#: Caractere de substituição — aparece quando a fonte não tem o glifo.
GLIFOS_INVALIDOS = ("�", "\x00")

#: Abertura de literal de lista seguida de string — assinatura de estrutura de
#: dados que vazou para o texto renderizado. Foi um defeito real: o LLM devolvia
#: `descricao` como string contendo o repr de uma lista e o PDF imprimia
#: ``['bullet um', 'bullet dois']`` num parágrafo corrido, com colchetes e
#: aspas, direto para o recrutador.
_RE_ESTRUTURA_VAZADA = re.compile(r"[\[\{]\s*['\"]")

#: Chave JSON dentro do texto — outra forma do mesmo vazamento.
_RE_CHAVE_JSON = re.compile(r"['\"]\w+['\"]\s*:\s*['\"]")


@dataclass(frozen=True)
class Problema:
    """Um achado de layout. ``grave=True`` deve impedir o uso do PDF."""

    tipo: str
    pagina: int
    detalhe: str
    grave: bool = True

    def __str__(self) -> str:
        sev = "GRAVE" if self.grave else "aviso"
        return f"[{sev}] p{self.pagina} {self.tipo}: {self.detalhe}"


def _abrir(pdf_path: Path):
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:  # pragma: no cover - dependência declarada
        raise RuntimeError(
            "pypdfium2 não instalado. Rode: pip install pypdfium2"
        ) from exc
    return pdfium.PdfDocument(str(pdf_path))


def renderizar(
    pdf_path: Path,
    destino: Path | None = None,
    dpi: int = DPI_PADRAO,
) -> list[Path]:
    """Renderiza cada página do PDF em PNG. Retorna os caminhos gerados.

    Sem ``destino``, grava ao lado do PDF como ``<nome>_p1.png``, ``_p2.png``…
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    destino = Path(destino) if destino else pdf_path.parent
    destino.mkdir(parents=True, exist_ok=True)

    escala = dpi / 72.0
    saidas: list[Path] = []

    pdf = _abrir(pdf_path)
    try:
        for i in range(len(pdf)):
            imagem = pdf[i].render(scale=escala).to_pil()
            saida = destino / f"{pdf_path.stem}_p{i + 1}.png"
            imagem.save(saida)
            saidas.append(saida)
    finally:
        pdf.close()

    logger.info("Preview gerado: %d página(s) de %s", len(saidas), pdf_path.name)
    return saidas


def _blocos_de_texto(pagina) -> list[tuple[float, float, float, float, str]]:
    """Caixas de texto da página: (x0, y0, x1, y1, texto).

    Coordenadas em pontos, origem no canto inferior esquerdo (padrão PDF).
    """
    textpage = pagina.get_textpage()
    try:
        blocos = []
        n = textpage.count_rects()
        for i in range(n):
            caixa = textpage.get_rect(i)
            texto = textpage.get_text_bounded(*caixa)
            if texto and texto.strip():
                blocos.append((*caixa, texto))
        return blocos
    finally:
        textpage.close()


#: Seções que um currículo tem de ter para um ATS extrair estrutura. O PDF pode
#: estar visualmente impecável e ainda assim ser mal interpretado se um cabeçalho
#: sumiu — "gerar PDF bonito" e "PDF legível por ATS" não são a mesma coisa.
SECOES_OBRIGATORIAS = (
    ("experiencia", ("experiência profissional", "experiencia profissional")),
    ("competencias", ("competências", "competencias", "habilidades")),
)

#: Abaixo disto o PDF provavelmente virou imagem, e um ATS não lê nada.
MIN_CHARS_EXTRAIVEIS = 400

_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def verificar_ats(pdf_path: Path) -> list[Problema]:
    """Checagens de legibilidade por ATS, sobre o texto extraído.

    Complementa `verificar_layout`, que olha geometria. Um PDF pode passar na
    geometria e falhar aqui: sem texto extraível, sem cabeçalho de seção, sem
    contato — nenhum desses defeitos aparece a olho nu.
    """
    pdf_path = Path(pdf_path)
    problemas: list[Problema] = []

    pdf = _abrir(pdf_path)
    try:
        partes = []
        for idx in range(len(pdf)):
            tp = pdf[idx].get_textpage()
            try:
                partes.append(tp.get_text_range())
            finally:
                tp.close()
        texto = "\n".join(partes)
    finally:
        pdf.close()

    minusculo = texto.lower()

    if len(texto.strip()) < MIN_CHARS_EXTRAIVEIS:
        problemas.append(Problema(
            "sem_texto_extraivel", 1,
            f"apenas {len(texto.strip())} caracteres extraíveis — ATS não conseguirá "
            "ler este PDF (virou imagem?)",
        ))
        return problemas

    for nome, variantes in SECOES_OBRIGATORIAS:
        if not any(v in minusculo for v in variantes):
            problemas.append(Problema(
                "secao_ausente", 1,
                f"cabeçalho de seção '{nome}' não encontrado no texto extraído",
            ))

    if not _RE_EMAIL.search(texto):
        problemas.append(Problema(
            "contato_ausente", 1,
            "nenhum e-mail no texto extraível — o recrutador não tem como responder",
        ))

    # Ordem de leitura: o nome deve sair antes das seções. Se o extrator devolve
    # a experiência antes do cabeçalho, a ordem de leitura do PDF está trocada e
    # o ATS vai associar dados aos campos errados.
    pos_secao = min(
        (minusculo.find(v) for _, variantes in SECOES_OBRIGATORIAS
         for v in variantes if minusculo.find(v) >= 0),
        default=-1,
    )
    if pos_secao > 0 and not _RE_EMAIL.search(texto[:pos_secao]):
        problemas.append(Problema(
            "ordem_de_leitura", 1,
            "contato não aparece antes da primeira seção — ordem de leitura do "
            "PDF possivelmente fora de sequência",
            grave=False,
        ))

    return problemas


def verificar_layout(pdf_path: Path, incluir_ats: bool = True) -> list[Problema]:
    """Checagens automáticas de layout. Lista vazia = nenhum problema detectado.

    Não substitui olhar o PNG: pega quebra geométrica e vazamento de estrutura,
    não feiura. Com ``incluir_ats``, soma as checagens de legibilidade por ATS.
    """
    pdf_path = Path(pdf_path)
    problemas: list[Problema] = []

    pdf = _abrir(pdf_path)
    try:
        n_paginas = len(pdf)

        if n_paginas == 0:
            return [Problema("pdf_vazio", 0, "PDF sem nenhuma página")]

        if n_paginas > MAX_PAGINAS_ESPERADO:
            problemas.append(Problema(
                "paginas_excessivas", n_paginas,
                f"{n_paginas} páginas (esperado até {MAX_PAGINAS_ESPERADO}) — "
                "conteúdo provavelmente transbordou",
            ))

        for idx in range(n_paginas):
            pagina = pdf[idx]
            num = idx + 1
            largura, altura = pagina.get_width(), pagina.get_height()
            blocos = _blocos_de_texto(pagina)

            if not blocos:
                problemas.append(Problema(
                    "pagina_vazia", num,
                    "página sem nenhum texto extraível",
                ))
                continue

            for x0, y0, x1, y1, texto in blocos:
                amostra = texto.strip().replace("\n", " ")[:60]

                # Transbordo horizontal — a causa mais comum de texto cortado.
                if x1 > largura + MARGEM_TOLERANCIA_PT:
                    problemas.append(Problema(
                        "transbordo_horizontal", num,
                        f"texto passa {x1 - largura:.0f}pt da borda direita: {amostra!r}",
                    ))
                if x0 < -MARGEM_TOLERANCIA_PT:
                    problemas.append(Problema(
                        "transbordo_horizontal", num,
                        f"texto começa {abs(x0):.0f}pt antes da borda esquerda: {amostra!r}",
                    ))

                # Transbordo vertical — texto fora da área imprimível.
                if y1 > altura + MARGEM_TOLERANCIA_PT or y0 < -MARGEM_TOLERANCIA_PT:
                    problemas.append(Problema(
                        "transbordo_vertical", num,
                        f"texto fora da altura da página: {amostra!r}",
                    ))

                if any(g in texto for g in GLIFOS_INVALIDOS):
                    problemas.append(Problema(
                        "glifo_faltante", num,
                        f"caractere não representável na fonte: {amostra!r}",
                    ))

                if _RE_ESTRUTURA_VAZADA.search(texto) or _RE_CHAVE_JSON.search(texto):
                    problemas.append(Problema(
                        "estrutura_vazada", num,
                        f"lista ou dict serializado aparecendo como texto: {amostra!r}",
                    ))
    finally:
        pdf.close()

    if incluir_ats:
        try:
            problemas.extend(verificar_ats(pdf_path))
        except Exception as exc:
            logger.warning("Checagem de ATS falhou em %s: %s", pdf_path, exc)

    return problemas


def gerar_preview_e_verificar(
    pdf_path: Path,
    destino: Path | None = None,
    dpi: int = DPI_PADRAO,
) -> tuple[list[Path], list[Problema]]:
    """Renderiza e verifica em uma chamada. É o que a geração de PDF invoca.

    Nunca levanta por falha de preview: um PDF válido não deve ser descartado
    porque a renderização de inspeção falhou. Problemas graves são logados como
    error e devolvidos para quem chamou decidir.
    """
    imagens: list[Path] = []
    problemas: list[Problema] = []

    try:
        problemas = verificar_layout(pdf_path)
    except Exception as exc:
        logger.warning("Verificação de layout falhou em %s: %s", pdf_path, exc)

    try:
        imagens = renderizar(pdf_path, destino=destino, dpi=dpi)
    except Exception as exc:
        logger.warning("Preview de %s falhou: %s", pdf_path, exc)

    graves = [p for p in problemas if p.grave]
    if graves:
        logger.error(
            "PDF %s tem %d problema(s) GRAVE(S) de layout:\n%s",
            Path(pdf_path).name, len(graves), "\n".join(f"  {p}" for p in graves),
        )
    elif problemas:
        logger.warning(
            "PDF %s tem %d aviso(s) de layout:\n%s",
            Path(pdf_path).name, len(problemas), "\n".join(f"  {p}" for p in problemas),
        )
    else:
        logger.info("PDF %s sem problemas de layout detectados.", Path(pdf_path).name)

    return imagens, problemas
