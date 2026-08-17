"""Gerador de PDF moderno usando ReportLab Platypus."""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class LayoutInvalidoError(Exception):
    """O PDF gerado tem problema grave de layout e não deve ser enviado."""

    def __init__(self, pdf_path, problemas, imagens=None):
        self.pdf_path = Path(pdf_path)
        self.problemas = list(problemas)
        self.imagens = list(imagens or [])
        detalhe = "; ".join(str(p) for p in self.problemas)
        onde = f" Inspecione: {self.imagens[0]}" if self.imagens else ""
        super().__init__(
            f"{self.pdf_path.name} reprovado na checagem de layout — {detalhe}.{onde}"
        )

# ── Paleta ────────────────────────────────────────────────────────────────────
NAVY  = "#1E3A5F"
BLUE  = "#2D6A9F"
GRAY1 = "#333333"
GRAY2 = "#666666"
GRAY3 = "#999999"
BGROW = "#F4F7FB"
WHITE = "#FFFFFF"

# ── Agrupamento de tecnologias ────────────────────────────────────────────────
# Keywords sem ambiguidade — sem letras soltas como "r"
_TECH_GROUPS = [
    ("Cloud & Big Data",   ["snowflake", "azure", "databricks", "bigquery", "redshift",
                             "synapse", "gcp", "aws", "emr"]),
    ("ETL & Pipelines",    ["etl", "elt", "azure data factory", "adf", "airbyte",
                             "fivetran", "glue", "nifi", "informatica", "pentaho"]),
    ("Linguagens",         ["python", "sql", "scala", "pyspark", "spark", "pandas",
                             "numpy", "java", "javascript", "typescript"]),
    ("Modelagem & Dados",  ["modelagem", "dbt", "data vault", "star schema", "kimball",
                             "dimensional", "lakehouse", "data mesh"]),
    ("Visualização & BI",  ["power bi", "tableau", "looker", "metabase", "qlik",
                             "data studio", "superset", "grafana"]),
    ("DevOps & Infra",     ["git", "github", "gitlab", "terraform", "iac", "docker",
                             "kubernetes", "jenkins", "azure devops", "linux",
                             "ci/cd", "helm", "ansible"]),
    ("Segurança & Redes",  ["sentinel", "siem", "wireshark", "owasp", "sonarqube",
                             "sonar qube", "pentest", "vnet", "private endpoint",
                             "firewall", "ids", "ips", "nist", "anpd"]),
    ("APIs & Integração",  ["api", "rest", "soap", "graphql", "webhook", "kafka",
                             "rabbitmq", "event hub"]),
]


def _match_tech(tech: str, keyword: str) -> bool:
    """Match seguro: exige palavra completa ou substring para keywords >= 3 chars."""
    t = tech.lower().strip()
    kw = keyword.lower().strip()
    if t == kw:
        return True
    if len(kw) < 3:
        return False
    return kw in t


def _group_techs(techs: list[str]) -> list[tuple[str, list[str]]]:
    assigned: set[str] = set()
    groups: list[tuple[str, list[str]]] = []
    for cat_name, keywords in _TECH_GROUPS:
        matched = [t for t in techs if t not in assigned
                   and any(_match_tech(t, kw) for kw in keywords)]
        for t in matched:
            assigned.add(t)
        if matched:
            groups.append((cat_name, matched))
    outros = [t for t in techs if t not in assigned]
    if outros:
        groups.append(("Outros", outros))
    return groups


# ── Helpers ───────────────────────────────────────────────────────────────────

def _esc(text) -> str:
    if not text:
        return ""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


def _make_styles():
    from reportlab.lib.colors import HexColor
    from reportlab.lib.enums import TA_JUSTIFY, TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle

    return {
        "name":       ParagraphStyle("name",    fontName="Helvetica-Bold", fontSize=22,
                                     leading=26, textColor=HexColor(WHITE)),
        "subtitle":   ParagraphStyle("subtitle", fontName="Helvetica", fontSize=10,
                                     leading=15, textColor=HexColor("#B0CCEB")),
        "contact":    ParagraphStyle("contact",  fontName="Helvetica", fontSize=8,
                                     leading=12, textColor=HexColor("#C8DCF0")),
        "section":    ParagraphStyle("section",  fontName="Helvetica-Bold", fontSize=8.5,
                                     leading=11, textColor=HexColor(NAVY)),
        "job_title":  ParagraphStyle("job_title", fontName="Helvetica-Bold", fontSize=10,
                                     leading=13, textColor=HexColor(GRAY1)),
        "company":    ParagraphStyle("company",  fontName="Helvetica-Oblique", fontSize=9,
                                     leading=12, textColor=HexColor(BLUE)),
        "date":       ParagraphStyle("date",     fontName="Helvetica", fontSize=8.5,
                                     leading=13, textColor=HexColor(GRAY2),
                                     alignment=TA_RIGHT),
        "body":       ParagraphStyle("body",     fontName="Helvetica", fontSize=9,
                                     leading=13, textColor=HexColor(GRAY1),
                                     alignment=TA_JUSTIFY),
        "bullet":     ParagraphStyle("bullet",   fontName="Helvetica", fontSize=9,
                                     leading=13, textColor=HexColor(GRAY1),
                                     leftIndent=18, firstLineIndent=-10),
        "tech_cat":   ParagraphStyle("tech_cat", fontName="Helvetica-Bold", fontSize=8.5,
                                     leading=12, textColor=HexColor(NAVY)),
        "tech_val":   ParagraphStyle("tech_val", fontName="Helvetica", fontSize=8.5,
                                     leading=12, textColor=HexColor(GRAY1)),
        "edu_title":  ParagraphStyle("edu_title", fontName="Helvetica-Bold", fontSize=9,
                                     leading=12, textColor=HexColor(GRAY1)),
        "edu_inst":   ParagraphStyle("edu_inst", fontName="Helvetica-Oblique", fontSize=8.5,
                                     leading=12, textColor=HexColor(GRAY2)),
        "tags":       ParagraphStyle("tags",     fontName="Helvetica-Oblique", fontSize=8,
                                     leading=11, textColor=HexColor(GRAY3)),
        "cert":       ParagraphStyle("cert",     fontName="Helvetica", fontSize=8.5,
                                     leading=12, textColor=HexColor(GRAY1)),
    }


def normalizar_itens(valor) -> list[str]:
    """Converte descrição/conquistas em lista de strings, seja qual for a forma.

    Trata o caso que já quebrou currículos em produção: o LLM devolvendo a lista
    **serializada como string** — ``"['bullet um', 'bullet dois']"``. Sem isto, o
    PDF imprimia o repr literal, com colchetes, aspas e vírgulas, num parágrafo
    corrido. A defesa de verdade está em `resume_optimizer.optimize`, que
    normaliza na origem; aqui é a rede no limite da renderização, porque este é
    o último ponto antes de o arquivo ir para um recrutador.
    """
    if not valor:
        return []

    if isinstance(valor, (list, tuple)):
        return [str(v).strip() for v in valor if str(v).strip()]

    texto = str(valor).strip()

    # String que é um literal de lista/tupla Python ou array JSON.
    if texto[:1] in "[(" and texto[-1:] in "])":
        import ast

        try:
            interpretado = ast.literal_eval(texto)
        except (ValueError, SyntaxError):
            interpretado = None
        if isinstance(interpretado, (list, tuple)):
            logger.warning(
                "descricao/conquistas veio como string contendo lista serializada; "
                "desempacotado na renderização. Corrija a origem."
            )
            return [str(v).strip() for v in interpretado if str(v).strip()]

    return [texto]


def _render_description(desc, styles) -> list:
    """Converte descrição (string ou lista) em elementos Platypus formatados como bullets."""
    from reportlab.platypus import Paragraph, Spacer

    if not desc:
        return []

    # Normaliza para lista de linhas
    if isinstance(desc, list):
        lines = [str(linha).strip() for linha in desc if str(linha).strip()]
    else:
        text = str(desc).strip()
        # Divide por \n explícito
        if "\n" in text:
            lines = [linha.strip() for linha in text.split("\n") if linha.strip()]
        # Divide por ". " se texto for longo e tiver múltiplas frases
        elif len(text) > 120 and ". " in text:
            raw = [s.strip() for s in text.split(". ") if s.strip()]
            lines = [f if f.endswith(".") else f + "." for f in raw]
        else:
            lines = [text]

    # Remove marcadores existentes para re-renderizar uniformemente
    cleaned = []
    for linha in lines:
        sem_marcador = linha.lstrip("•·◆▪-– ").strip()
        if sem_marcador:
            cleaned.append(sem_marcador)

    if not cleaned:
        return []

    # Uma linha curta → parágrafo simples
    if len(cleaned) == 1:
        return [Paragraph(_esc(cleaned[0]), styles["body"])]

    # Múltiplas linhas → bullets com hanging indent
    elements = []
    for line in cleaned:
        elements.append(Paragraph(f"• {_esc(line)}", styles["bullet"]))
        elements.append(Spacer(1, 1))
    return elements


def _section_bar(label: str, styles, doc_width):
    """Faixa com barra azul à esquerda e fundo cinza muito suave."""
    from reportlab.lib.colors import HexColor
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, Table, TableStyle

    bar  = Table([[""]], colWidths=[0.35*cm])
    bar.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), HexColor(BLUE)),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING",   (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
    ]))
    label_p = Paragraph(label.upper(), styles["section"])
    row = Table([[bar, label_p]], colWidths=[0.35*cm, doc_width - 0.35*cm])
    row.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), HexColor(BGROW)),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (0, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",  (1, 0), (1, -1), 8),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
    ]))
    return row


def _exp_header(cargo, empresa, inicio, fim, styles, doc_width):
    """Linha: cargo + empresa (esquerda) | datas (direita) — largura fixa correta."""
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, Table, TableStyle

    date_str = f"{_esc(inicio)} – {_esc(fim) or 'Presente'}"
    date_w = 3.6 * cm          # largura real em pontos

    left_p = Paragraph(
        f"{_esc(cargo)}<br/>"
        f"<font color='{BLUE}'><i>{_esc(empresa)}</i></font>",
        styles["job_title"],
    )
    right_p = Paragraph(date_str, styles["date"])

    tbl = Table([[left_p, right_p]], colWidths=[doc_width - date_w, date_w])
    tbl.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING",   (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 2),
    ]))
    return tbl


def _tech_table(groups, styles, doc_width):
    """Tabela 2 colunas: categoria (bold) | valores."""
    from reportlab.lib.colors import HexColor
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, Table, TableStyle

    cat_w = 3.8 * cm
    val_w = doc_width - cat_w

    rows = []
    for cat, vals in groups:
        rows.append([
            Paragraph(_esc(cat), styles["tech_cat"]),
            Paragraph(_esc(", ".join(vals)), styles["tech_val"]),
        ])

    tbl = Table(rows, colWidths=[cat_w, val_w])
    cmds = [
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
    ]
    for i in range(0, len(rows), 2):
        cmds.append(("BACKGROUND", (0, i), (-1, i), HexColor(BGROW)))
    tbl.setStyle(TableStyle(cmds))
    return tbl


# ── Gerador principal ─────────────────────────────────────────────────────────

def generate_pdf(
    resume: dict,
    output_path: Path,
    preview: bool = True,
    estrito: bool = True,
) -> Path:
    """Gera o PDF do currículo. Sempre renderiza um preview e verifica o layout.

    Regra do projeto: nenhum PDF sai sem imagem de inspeção e sem checagem
    automática. Currículos já foram enviados com layout quebrado justamente por
    não haver nem uma coisa nem outra.

    ``estrito=True`` (padrão) levanta ``LayoutInvalidoError`` quando a checagem
    acha problema grave — falha fechada, para um currículo quebrado não chegar a
    um recrutador. O orquestrador captura e marca a vaga como erro, para revisão
    humana. Use ``estrito=False`` apenas em inspeção manual, quando você quer o
    arquivo justamente para olhar o defeito.
    """
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        HRFlowable,
        KeepTogether,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    L = R = 1.8 * cm
    T = B = 1.6 * cm
    PAGE_W, _ = A4
    DOC_W = PAGE_W - L - R   # largura útil em pontos

    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        leftMargin=L, rightMargin=R, topMargin=T, bottomMargin=B,
        title=resume.get("nome", "Currículo"),
    )
    styles = _make_styles()
    story  = []

    # ── Cabeçalho ─────────────────────────────────────────────────────────────
    nome = _esc(resume.get("nome", ""))
    cargo_atual = ""
    if resume.get("experiencias"):
        cargo_atual = _esc(resume["experiencias"][0].get("cargo", ""))

    contact_parts = []
    if resume.get("email"):
        contact_parts.append(_esc(resume["email"]))
    if resume.get("telefone"):
        contact_parts.append(_esc(resume["telefone"]))
    if resume.get("linkedin"):
        slug = resume["linkedin"].rstrip("/").split("/")[-1]
        contact_parts.append(f"linkedin.com/in/{_esc(slug)}")
    if resume.get("localizacao"):
        contact_parts.append(_esc(resume["localizacao"]))

    header_content = Table(
        [
            [Paragraph(nome, styles["name"])],
            [Paragraph(cargo_atual, styles["subtitle"])] if cargo_atual else [Spacer(1, 2)],
            [Spacer(1, 6)],
            [Paragraph("   ·   ".join(contact_parts), styles["contact"])],
        ],
        colWidths=[DOC_W],
    )
    header_content.setStyle(TableStyle([
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING",   (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 1),
    ]))
    header = Table([[header_content]], colWidths=[DOC_W])
    header.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), HexColor(NAVY)),
        ("LEFTPADDING",  (0, 0), (-1, -1), 18),
        ("RIGHTPADDING", (0, 0), (-1, -1), 18),
        ("TOPPADDING",   (0, 0), (-1, -1), 16),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 16),
    ]))
    story.append(header)
    story.append(Spacer(1, 8))

    # ── Resumo Profissional ───────────────────────────────────────────────────
    resumo = resume.get("resumo_profissional", "")
    if resumo:
        story.append(_section_bar("Resumo Profissional", styles, DOC_W))
        story.append(Spacer(1, 4))
        story.append(Paragraph(_esc(resumo), styles["body"]))
        story.append(Spacer(1, 8))

    # ── Experiência Profissional ──────────────────────────────────────────────
    experiencias = resume.get("experiencias", [])
    if experiencias:
        story.append(_section_bar("Experiência Profissional", styles, DOC_W))
        for i, exp in enumerate(experiencias):
            block = [Spacer(1, 5)]
            block.append(_exp_header(
                exp.get("cargo", ""), exp.get("empresa", ""),
                exp.get("data_inicio", ""), exp.get("data_fim", ""),
                styles, DOC_W,
            ))

            desc = exp.get("descricao", "")
            conquistas = normalizar_itens(exp.get("conquistas", []))

            # Merge desc + conquistas em uma lista unificada de bullets (max 7)
            all_items = []
            if desc:
                itens_desc = normalizar_itens(desc)
                if len(itens_desc) > 1:
                    all_items.extend(itens_desc)
                else:
                    # Item único: ainda pode ser um parágrafo corrido que vale
                    # quebrar em bullets por linha ou por frase.
                    texto = itens_desc[0]
                    if "\n" in texto or (len(texto) > 120 and ". " in texto):
                        separador = "\n" if "\n" in texto else ". "
                        all_items.extend(
                            [s.strip() for s in texto.split(separador) if s.strip()]
                        )
                    else:
                        all_items.append(texto)
            # Só adiciona conquistas se descricao tem < 6 bullets (cap total em 6)
            if conquistas and len(all_items) < 6:
                slots = 6 - len(all_items)
                all_items.extend(conquistas[:slots])
            all_items = all_items[:6]  # hard cap

            if all_items:
                block.append(Spacer(1, 3))
                block.extend(_render_description(all_items, styles))

            exp_techs = exp.get("tecnologias", [])
            if exp_techs:
                block.append(Spacer(1, 3))
                block.append(Paragraph(_esc(" · ".join(exp_techs)), styles["tags"]))

            story.append(KeepTogether(block))

            if i < len(experiencias) - 1:
                story.append(Spacer(1, 3))
                story.append(HRFlowable(width="100%", thickness=0.5,
                                        color=HexColor("#DDDDDD"), spaceAfter=0))

        story.append(Spacer(1, 8))

    # ── Competências Técnicas ─────────────────────────────────────────────────
    techs = resume.get("tecnologias", [])
    if techs:
        story.append(_section_bar("Competências Técnicas", styles, DOC_W))
        story.append(Spacer(1, 4))
        story.append(_tech_table(_group_techs(techs), styles, DOC_W))
        story.append(Spacer(1, 8))

    # ── Formação + Certificações lado a lado ─────────────────────────────────
    formacao = resume.get("formacao", [])
    certs = resume.get("certificacoes", [])
    idiomas = resume.get("idiomas", [])

    if formacao or certs:
        # Coluna esquerda: Formação
        left_items = []
        if formacao:
            left_items.append(_section_bar("Formação Acadêmica", styles, DOC_W))
            left_items.append(Spacer(1, 4))
            for f in formacao:
                curso  = _esc(f.get("curso", ""))
                inst   = _esc(f.get("instituicao", ""))
                data   = _esc(f.get("data_conclusao", ""))
                suffix = " (em andamento)" if f.get("em_andamento") else ""
                date_part = f" — {data}{suffix}" if data else suffix
                left_items.append(Paragraph(curso, styles["edu_title"]))
                left_items.append(Paragraph(f"{inst}{date_part}", styles["edu_inst"]))
                left_items.append(Spacer(1, 4))

        # Coluna direita: Certificações
        right_items = []
        if certs:
            right_items.append(_section_bar("Certificações", styles, DOC_W))
            right_items.append(Spacer(1, 4))
            from collections import defaultdict
            by_emissor: dict[str, list[str]] = defaultdict(list)
            for c in certs:
                by_emissor[c.get("emissor", "")].append(c.get("nome", ""))
            for emissor, nomes in by_emissor.items():
                emissor_str = f" <font color='{GRAY3}'>— <i>{_esc(emissor)}</i></font>" if emissor else ""
                for nome_c in nomes:
                    right_items.append(Paragraph(
                        f"<b>{_esc(nome_c)}</b>{emissor_str}",
                        styles["cert"],
                    ))
                    right_items.append(Spacer(1, 2))

        if left_items and right_items:
            half = DOC_W / 2 - 0.3 * cm
            try:
                col_tbl = Table(
                    [[left_items, right_items]],
                    colWidths=[half, half],
                )
                from reportlab.platypus import TableStyle as TS
                col_tbl.setStyle(TS([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING",  (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING",   (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
                ]))
                story.append(col_tbl)
            except Exception:
                story.extend(left_items)
                story.extend(right_items)
        else:
            story.extend(left_items)
            story.extend(right_items)

        story.append(Spacer(1, 8))

    # ── Idiomas ───────────────────────────────────────────────────────────────
    if idiomas:
        story.append(_section_bar("Idiomas", styles, DOC_W))
        story.append(Spacer(1, 4))
        parts = [
            f"<b>{_esc(i.get('nome',''))}</b> — {_esc(i.get('nivel',''))}"
            for i in idiomas
        ]
        story.append(Paragraph("   ·   ".join(parts), styles["body"]))

    doc.build(story)
    logger.info("PDF gerado: %s", output_path)

    if preview:
        from jobapplier.generators.preview import gerar_preview_e_verificar

        imagens, problemas = gerar_preview_e_verificar(output_path)
        graves = [p for p in problemas if p.grave]
        if graves and estrito:
            raise LayoutInvalidoError(output_path, graves, imagens)

    return output_path
