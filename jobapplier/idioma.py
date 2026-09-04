"""Idioma da vaga: currículo em português para vaga em inglês perde duas vezes.

Perde no parsing — o ATS casa termo literal, e "Engenharia de Dados" não bate com
"Data Engineering" — e perde na leitura, porque quem escreveu a vaga em inglês
provavelmente conduz o processo em inglês.

Isso não é hipótese: das 11.870 vagas coletadas, **3.980 títulos do Greenhouse
estão em inglês** contra 439 em português. E as empresas mais desejadas do
mercado brasileiro de dados — Nubank, iFood, QuintoAndar — publicam em inglês
mesmo para vagas em São Paulo.

A detecção é por palavra funcional, não por dicionário técnico. "Data",
"pipeline" e "Snowflake" aparecem nos dois idiomas; "de", "para", "com" e "the",
"with", "you" não. Contar palavra técnica classificaria toda vaga como inglês.

O que o idioma detectado decide: qual currículo mestre `jobapplier.perfis` monta
(`data/resume.json` ou `data/resume_en.json`, traduzido uma vez à mão) e, quando
há um provedor de LLM, a instrução de idioma no prompt do otimizador. Tradução
em tempo de execução foi recusada: custaria uma chamada por vaga e devolveria
texto diferente a cada rodada, impossível de revisar antes de enviar.

**Indefinido não é inglês.** Vaga bilíngue e texto curto ficam sem veredito de
propósito, e o currículo em português — o padrão — prevalece. Chutar mandaria
currículo em inglês para recrutador brasileiro sem deixar rastro.
"""
from __future__ import annotations

import re

#: Palavras funcionais, que não migram entre idiomas. Termo técnico fica de fora
#: de propósito: "data", "pipeline" e "cloud" aparecem nos dois.
_PT = frozenset(["de", "da", "do", "das", "dos", "para", "com", "sem", "por", "em", "na", "no", "nas", "nos", "que", "não", "é", "são", "será", "você", "seu", "sua", "nossos", "nossa", "como", "mais", "suas", "dele", "ela", "nós", "somos", "temos", "ter", "experiência", "conhecimento", "atuação", "vaga", "sobre", "requisitos", "desejável", "diferencial", "responsabilidades", "benefícios", "trabalho", "equipe", "empresa"])

_EN = frozenset(["the", "and", "or", "with", "for", "you", "your", "our", "we", "are", "is", "will", "be", "have", "has", "of", "to", "in", "on", "at", "as", "from", "this", "that", "they", "their", "about", "role", "team", "company", "experience", "requirements", "responsibilities", "benefits", "work", "skills", "who", "what", "looking"])

_PALAVRA = re.compile(r"[a-zà-ÿ]+", re.IGNORECASE)

#: Abaixo disto a amostra é curta demais para decidir. Título sozinho tem ~6
#: palavras e quase nenhuma funcional — chutar ali erraria muito.
MINIMO_PALAVRAS = 25

#: Margem para declarar um vencedor. Vaga bilíngue ("Data Engineer | Atuação
#: híbrida em São Paulo") fica genuinamente indefinida, e forçar um idioma seria
#: pior que admitir a dúvida.
MARGEM = 1.4


def detectar(*textos: str) -> str:
    """``"pt"``, ``"en"`` ou ``"indefinido"``.

    Recebe vários trechos (título, descrição) e os concatena — título sozinho
    raramente tem palavra funcional suficiente.
    """
    texto = " ".join(t for t in textos if t)
    if not texto.strip():
        return "indefinido"

    palavras = [p.lower() for p in _PALAVRA.findall(texto)]
    if len(palavras) < MINIMO_PALAVRAS:
        return "indefinido"

    pt = sum(1 for p in palavras if p in _PT)
    en = sum(1 for p in palavras if p in _EN)

    if pt == 0 and en == 0:
        return "indefinido"
    if pt >= en * MARGEM:
        return "pt"
    if en >= pt * MARGEM:
        return "en"
    return "indefinido"


def da_vaga(vaga) -> str:
    """Idioma de uma vaga, a partir do título e da descrição."""
    return detectar(getattr(vaga, "titulo", "") or "",
                    getattr(vaga, "descricao", "") or "")


#: Nome do idioma para instruir o modelo. Instrução em português mesmo para
#: saída em inglês: o resto do prompt é em português, e misturar idioma de
#: instrução piora a aderência.
NOME = {"pt": "português", "en": "inglês"}


def instrucao_para(codigo: str) -> str:
    """Trecho de prompt que fixa o idioma de saída. Vazio se indefinido.

    Só o texto livre é traduzido. Nome de empresa, cargo formal, tecnologia e
    data ficam como estão — traduzir "Coordenador de Dados" para "Data
    Coordinator" criaria divergência com o LinkedIn e com a carteira, e
    divergência de cargo é o descarte mais barato que existe.
    """
    nome = NOME.get(codigo)
    if not nome:
        return ""
    return (
        f"\n\nIDIOMA DE SAÍDA: escreva resumo profissional e descrições de "
        f"experiência em {nome}, porque a vaga está em {nome}. "
        f"NÃO traduza: nome de empresa, cargo formal, nome de tecnologia, "
        f"instituição de ensino e datas — eles precisam bater com o LinkedIn e "
        f"com o registro formal."
    )


def descompasso(idioma_vaga: str, idioma_curriculo: str = "pt") -> str:
    """Aviso quando a vaga está num idioma e o currículo em outro. Vazio se ok.

    Existe porque o descompasso é invisível: o PDF sai bonito, o ATS não casa os
    termos, e não há erro em lugar nenhum.

    Lado indefinido não gera aviso. Sem saber o idioma de um dos dois não há como
    afirmar que divergem, e avisar na dúvida treinaria a ignorar o aviso.
    """
    indefinidos = ("indefinido", "")
    if idioma_vaga in indefinidos or idioma_curriculo in indefinidos:
        return ""
    if idioma_vaga == idioma_curriculo:
        return ""
    arquivo = {"pt": "resume.json", "en": "resume_en.json"}.get(idioma_vaga)
    onde = f" Confira data/{arquivo}." if arquivo else ""
    return (
        f"Vaga em {NOME.get(idioma_vaga, idioma_vaga)}, currículo em "
        f"{NOME.get(idioma_curriculo, idioma_curriculo)}: o currículo mestre "
        f"naquele idioma não foi carregado.{onde}"
    )
