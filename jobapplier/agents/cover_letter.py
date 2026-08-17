"""Módulo 6 — Geração de Cover Letter personalizada."""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jobapplier.llm import LLMClient

logger = logging.getLogger(__name__)

COVER_LETTER_PROMPT = """Você é um especialista em redação de cartas de apresentação para vagas de tecnologia no Brasil.

CANDIDATO:
Nome: {nome}
Cargo atual: {cargo_atual}
Tecnologias principais: {techs}

VAGA:
Empresa: {empresa}
Título: {titulo}
Senioridade: {senioridade}
Tecnologias da vaga: {techs_vaga}
Setor: {setor}

Escreva uma carta de apresentação profissional em português com:
- Máximo 300 palavras
- Tom profissional mas genuíno, sem exageros
- Primeiro parágrafo: apresentação e interesse genuíno na empresa/vaga
- Segundo parágrafo: 2-3 realizações concretas alinhadas à vaga (use apenas fatos do currículo)
- Terceiro parágrafo: motivação específica para esta empresa e disponibilidade
- Sem fórmulas genéricas como "venho por meio desta"
- Não use "prezado(a)" — comece direto com o conteúdo

Retorne SOMENTE o texto da carta, sem assunto, sem cabeçalho, sem assinatura."""


def montar_sem_llm(resume_json: dict, vaga) -> str:
    """Cover letter montada a partir de fatos do currículo, sem modelo.

    Não tenta imitar texto gerado: é curta, factual e diz apenas o que o
    currículo sustenta — cargo atual, tempo de experiência e quais
    tecnologias pedidas na vaga o candidato de fato usa. Uma carta genérica
    fingindo entusiasmo seria pior que nenhuma; esta é honesta sobre o que é.

    Existe porque muitos formulários têm campo obrigatório de carta.
    """
    from jobapplier import vocabulario as vocab

    normalizado = getattr(vaga, "normalizado_json", None) or {}
    experiencias = resume_json.get("experiencias") or []
    cargo_atual = experiencias[0].get("cargo", "") if experiencias else ""
    nome = resume_json.get("nome", "")
    empresa = getattr(vaga, "empresa", "") or "a empresa"
    titulo = normalizado.get("cargo") or getattr(vaga, "titulo", "") or "a vaga"

    tec_vaga = normalizado.get("tecnologias") or []
    tec_curriculo = {vocab.canonizar(t) for t in (resume_json.get("tecnologias") or [])}
    em_comum = [t for t in tec_vaga if t in tec_curriculo]

    linhas = [f"Prezada equipe de {empresa},", ""]
    abertura = f"Escrevo para me candidatar à vaga de {titulo}."
    if cargo_atual:
        abertura += f" Atuo hoje como {cargo_atual}."
    linhas.append(abertura)

    if em_comum:
        linhas += ["", "Tenho experiência prática com as tecnologias centrais da vaga: "
                   + ", ".join(em_comum[:8]) + "."]

    conquistas = [c for e in experiencias for c in (e.get("conquistas") or [])]
    if conquistas:
        linhas += ["", conquistas[0].rstrip(".") + "."]

    linhas += ["", "Fico à disposição para conversar sobre como posso contribuir.",
               "", "Atenciosamente,", nome]
    return "\n".join(linhas)


def generate(resume_json: dict, vaga, client: "LLMClient | None" = None) -> str | None:
    """Gera cover letter. Sem ``client``, monta a versão factual sem modelo."""
    if client is None:
        return montar_sem_llm(resume_json, vaga)

    normalizado = getattr(vaga, "normalizado_json", None) or {}

    experiencias = resume_json.get("experiencias", [])
    cargo_atual = experiencias[0].get("cargo", "") if experiencias else ""
    techs_candidato = ", ".join(resume_json.get("tecnologias", [])[:12])
    techs_vaga = ", ".join(normalizado.get("tecnologias", [])[:10])

    prompt = COVER_LETTER_PROMPT.format(
        nome=resume_json.get("nome", ""),
        cargo_atual=cargo_atual,
        techs=techs_candidato,
        empresa=getattr(vaga, "empresa", ""),
        titulo=getattr(vaga, "titulo", ""),
        senioridade=normalizado.get("senioridade", "Pleno"),
        techs_vaga=techs_vaga,
        setor=normalizado.get("setor_empresa", "Tecnologia"),
    )

    try:
        texto = client.generate(prompt, temperature=0.4)
        return texto.strip() if texto else None
    except Exception as exc:
        logger.error("Erro ao gerar cover letter para vaga id=%s: %s", getattr(vaga, "id", "?"), exc)
        return None
