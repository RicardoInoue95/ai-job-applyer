"""Análise do perfil do LinkedIn: o que ele diz, o que o mestre diz, o que as vagas pedem.

O perfil chega pela extensão, lido do DOM da página do PRÓPRIO candidato
(`extensao/linkedin.js`), quando ele clica em "Analisar meu perfil". Nada aqui
abre o LinkedIn, nem com a sessão salva: leitura automatizada da conta é o que a
invariante 6 evita, e a extensão rodando na aba que o candidato abriu é a mesma
assistência que ela já presta na Gupy.

Três frentes, na ordem do que mais custa se estiver errado:

1. **Fato** — cargo, empresa, data e formação divergindo do mestre. O
   recrutador cruza o perfil com o currículo, e divergência lê como descuido ou
   como mentira. Mesma régua da invariante 11: o mestre manda.
2. **Vocabulário** — tecnologia que as vagas da fila pedem, o currículo tem, e o
   perfil não menciona. A busca do LinkedIn casa termo literal; o que não está
   escrito não é encontrado.
3. **Régua do tutorial** (`docs/TUTORIAL_LINKEDIN.md`) — título com cargo e
   stack, "Sobre" com peso nas primeiras linhas, competências suficientes.

O que esta análise **nunca** sugere é acrescentar ao perfil o que o mestre não
sustenta (invariante 3). Tecnologia pedida pelo mercado e ausente do mestre vira
`lacuna` — informação para o candidato, não ajuste de texto.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from urllib.parse import urlsplit

from jobapplier import paths, vocabulario
from jobapplier.tempo import agora_utc

#: Onde o último perfil lido fica. Em `data/`, nunca versionado (invariante 4).
ARQUIVO = paths.DATA / "perfil_linkedin.json"

#: Vagas que definem "o mercado que você quer": as que passaram nos filtros e
#: estão na fila. `pendente` fica de fora — possibilidade não é alvo.
STATUS_MERCADO = ("aprovada", "pronta_envio_manual", "pronta_para_revisao")

#: Quantas tecnologias do mercado entram na comparação.
TOPO_MERCADO = 15
#: Quantas das mais pedidas o título deveria citar, e o tamanho mínimo do
#: "Sobre" — a régua do tutorial.
MINIMO_NO_TITULO = 2
MINIMO_SOBRE = 300


@dataclass
class Ajuste:
    #: 1 = fato errado ou seção vazia; 2 = vocabulário; 3 = polimento.
    prioridade: int
    #: fato | titulo | sobre | competencias | experiencia
    area: str
    problema: str
    #: Texto pronto para colar, tirado do mestre. Vazio quando o ajuste é
    #: remover algo, não acrescentar.
    sugestao: str = ""


@dataclass
class Analise:
    lido_em: str
    url: str
    ajustes: list[Ajuste] = field(default_factory=list)
    #: (tecnologia, nº de vagas da fila que a pedem), do mais para o menos.
    mercado: list[tuple[str, int]] = field(default_factory=list)
    #: Pedidas pelo mercado e ausentes do MESTRE. Não viram ajuste de perfil.
    lacunas: list[str] = field(default_factory=list)
    #: Quantas das tecnologias do mercado o perfil já menciona.
    cobertura: tuple[int, int] = (0, 0)

    def como_dict(self) -> dict:
        d = asdict(self)
        d["ajustes"] = sorted(d["ajustes"], key=lambda a: (a["prioridade"], a["area"]))
        return d


# ── Identidade ────────────────────────────────────────────────────────────────

def slug(url: str) -> str:
    """`ricardo-x` de `https://www.linkedin.com/in/ricardo-x/?locale=pt`."""
    partes = [p for p in urlsplit(url or "").path.split("/") if p]
    if len(partes) >= 2 and partes[0] == "in":
        return partes[1].casefold()
    return ""


def e_meu_perfil(url: str, mestre: dict) -> bool:
    """A página lida é a do candidato? Perfil de terceiro não entra: a extensão
    tem permissão em `/in/*` porque não há como restringi-la a um slug."""
    meu = slug(mestre.get("linkedin") or "")
    return bool(meu) and slug(url) == meu


# ── Persistência ──────────────────────────────────────────────────────────────

def gravar(perfil: dict, url: str) -> dict:
    registro = {"lido_em": agora_utc().isoformat(timespec="seconds"),
                "url": url, "perfil": perfil}
    paths.garantir(ARQUIVO.parent)
    ARQUIVO.write_text(json.dumps(registro, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    return registro


def carregar() -> dict | None:
    if not ARQUIVO.exists():
        return None
    dados = json.loads(ARQUIVO.read_text(encoding="utf-8"))
    return dados if isinstance(dados, dict) else None


# ── Mercado ───────────────────────────────────────────────────────────────────

def mercado(sessao, limite: int = TOPO_MERCADO) -> list[tuple[str, int]]:
    """Tecnologias mais pedidas pelas vagas da fila, canonizadas."""
    from jobapplier.database.models import Vaga

    contagem: Counter[str] = Counter()
    linhas = (sessao.query(Vaga.normalizado_json)
              .filter(Vaga.status.in_(STATUS_MERCADO)).all())
    for (bruto,) in linhas:
        dados = bruto
        if isinstance(dados, str):
            try:
                dados = json.loads(dados)
            except json.JSONDecodeError:
                continue
        if not isinstance(dados, dict):
            continue
        vistas = {vocabulario.canonizar(t) for t in (dados.get("tecnologias") or [])
                  if isinstance(t, str) and t.strip()}
        contagem.update(vistas)
    return contagem.most_common(limite)


# ── Análise ───────────────────────────────────────────────────────────────────

def _norma(texto: str) -> str:
    return re.sub(r"\s+", " ", (texto or "")).strip().casefold()


def _anos(texto: str) -> set[int]:
    """Anos num período como `ago de 2025 - o momento · 1 ano 2 meses`."""
    return {int(a) for a in re.findall(r"(?<!\d)((?:19|20)\d{2})(?!\d)", texto or "")}


def _ano_de(data: str | None) -> int | None:
    """`08/2025` → 2025. Também aceita `2025` e `2025-08`."""
    m = re.search(r"(19|20)\d{2}", data or "")
    return int(m.group(0)) if m else None


def _tecnologias_no_perfil(perfil: dict) -> set[str]:
    texto = " ".join([
        perfil.get("titulo") or "",
        perfil.get("sobre") or "",
        *[e.get("descricao") or "" for e in perfil.get("experiencias") or []],
        *[e.get("cargo") or "" for e in perfil.get("experiencias") or []],
    ])
    vistas = set(vocabulario.tecnologias_em(texto))
    vistas |= {vocabulario.canonizar(c) for c in perfil.get("competencias") or []
               if isinstance(c, str) and c.strip()}
    return vistas


def _fatos(perfil: dict, mestre: dict) -> list[Ajuste]:
    ajustes: list[Ajuste] = []
    no_perfil = perfil.get("experiencias") or []
    por_empresa = {_norma(e.get("empresa")): e for e in no_perfil if e.get("empresa")}

    for exp in mestre.get("experiencias") or []:
        empresa = exp.get("empresa") or ""
        achada = por_empresa.get(_norma(empresa))
        periodo = f"{exp.get('data_inicio') or ''} – {exp.get('data_fim') or 'atual'}"
        if achada is None:
            ajustes.append(Ajuste(
                1, "experiencia",
                f"'{empresa}' está no currículo e não aparece no perfil.",
                f"{exp.get('cargo')} · {empresa} · {periodo}"))
            continue
        if _norma(achada.get("cargo")) != _norma(exp.get("cargo")):
            ajustes.append(Ajuste(
                1, "experiencia",
                f"Cargo na {empresa}: o perfil diz '{achada.get('cargo')}', "
                f"o currículo diz '{exp.get('cargo')}'.",
                exp.get("cargo") or ""))
        ano = _ano_de(exp.get("data_inicio"))
        anos_perfil = _anos(achada.get("periodo") or "")
        if ano and anos_perfil and ano not in anos_perfil:
            ajustes.append(Ajuste(
                1, "experiencia",
                f"Data na {empresa}: o perfil mostra {sorted(anos_perfil)}, "
                f"o currículo começa em {exp.get('data_inicio')}.",
                periodo))

    empresas_mestre = {_norma(e.get("empresa")) for e in mestre.get("experiencias") or []}
    for e in no_perfil:
        if e.get("empresa") and _norma(e["empresa"]) not in empresas_mestre:
            ajustes.append(Ajuste(
                2, "experiencia",
                f"'{e['empresa']}' só existe no LinkedIn. Ou entra no currículo "
                "mestre, ou sai do perfil — as duas fontes têm de dizer o mesmo."))

    formacoes_perfil = _norma(" ".join(
        f"{f.get('instituicao') or ''} {f.get('curso') or ''}"
        for f in perfil.get("formacao") or []))
    for f in mestre.get("formacao") or []:
        inst = f.get("instituicao") or ""
        # Só a sigla/primeira palavra forte: "FIAP" casa com o nome completo.
        chave = next((p for p in re.findall(r"[A-Za-zÀ-ú]{3,}", inst)
                      if p.isupper()), inst.split(" ")[0] if inst else "")
        if chave and _norma(chave) not in formacoes_perfil:
            ajustes.append(Ajuste(
                1, "fato",
                f"Formação '{f.get('curso')}' ({inst}) não aparece no perfil.",
                f"{f.get('curso')} · {inst} · {f.get('data_conclusao') or ''}"))
    return ajustes


def _vocabulario(perfil: dict, mestre: dict,
                 mercado_: list[tuple[str, int]]) -> tuple[list[Ajuste], list[str], tuple[int, int]]:
    """UM ajuste com todas as tecnologias faltantes, não um por tecnologia.

    Oito cartões "adicionar X" são uma lista de afazeres com oito itens — o
    tédio que a Finalidade proíbe. Uma lista só, com a contagem de vagas ao
    lado, diz o mesmo e cabe numa olhada.
    """
    no_perfil = _tecnologias_no_perfil(perfil)
    no_mestre = {vocabulario.canonizar(t) for t in mestre.get("tecnologias") or []}
    no_titulo = set(vocabulario.tecnologias_em(perfil.get("titulo") or ""))

    faltam, lacunas, cobertas = [], [], 0
    for posicao, (tec, n) in enumerate(mercado_):
        if tec in no_perfil:
            cobertas += 1
        elif tec not in no_mestre:
            lacunas.append(tec)
        else:
            faltam.append((tec, n, posicao < 5 and tec not in no_titulo))

    ajustes: list[Ajuste] = []
    if faltam:
        lista = ", ".join(f"{t} ({n})" for t, n, _ in faltam)
        para_titulo = [t for t, _, no_topo in faltam if no_topo]
        sugestao = "Adicionar em Competências: " + ", ".join(t for t, _, _ in faltam)
        if para_titulo:
            sugestao += ("\nE no título, por estarem entre as 5 mais pedidas: "
                         + ", ".join(para_titulo))
        ajustes.append(Ajuste(
            2, "competencias",
            f"{len(faltam)} tecnologia(s) que a fila pede (nº de vagas) e o "
            f"currículo tem, mas o perfil não menciona: {lista}.",
            sugestao))
    return ajustes, lacunas, (cobertas, len(mercado_))


def _regua(perfil: dict, mestre: dict, mercado_: list[tuple[str, int]]) -> list[Ajuste]:
    ajustes: list[Ajuste] = []
    no_mestre = {vocabulario.canonizar(t) for t in mestre.get("tecnologias") or []}
    pedidas_e_tidas = [t for t, _ in mercado_ if t in no_mestre]
    cargo_atual = ((mestre.get("experiencias") or [{}])[0].get("cargo") or "").strip()
    sugestao_titulo = " | ".join(
        p for p in [cargo_atual, ", ".join(pedidas_e_tidas[:4])] if p)

    titulo = perfil.get("titulo") or ""
    if not titulo.strip():
        ajustes.append(Ajuste(1, "titulo", "O perfil está sem título.", sugestao_titulo))
    else:
        top5 = [t for t, _ in mercado_[:5]]
        citadas = [t for t in vocabulario.tecnologias_em(titulo) if t in top5]
        if len(citadas) < MINIMO_NO_TITULO:
            ajustes.append(Ajuste(
                2, "titulo",
                f"O título cita {len(citadas)} das 5 tecnologias mais pedidas "
                f"({', '.join(top5)}). É o campo que a busca mais pesa.",
                sugestao_titulo))

    sobre = perfil.get("sobre") or ""
    resumo = mestre.get("resumo_profissional") or ""
    if not sobre.strip():
        ajustes.append(Ajuste(1, "sobre", "A seção 'Sobre' está vazia.", resumo))
    elif len(sobre.strip()) < MINIMO_SOBRE:
        ajustes.append(Ajuste(
            3, "sobre",
            f"'Sobre' tem {len(sobre.strip())} caracteres; abaixo de "
            f"{MINIMO_SOBRE} costuma ser só o título repetido.", resumo))

    if not perfil.get("competencias"):
        pedidas = ", ".join(pedidas_e_tidas[:8])
        ajustes.append(Ajuste(1, "competencias", "A seção 'Competências' está vazia.",
                              f"Adicionar: {pedidas}" if pedidas else ""))
    return ajustes


def analisar(perfil: dict, mestre: dict, mercado_: list[tuple[str, int]],
             url: str = "", lido_em: str = "") -> Analise:
    """Compara o perfil com o mestre e com o mercado. Não toca rede nem banco."""
    analise = Analise(lido_em=lido_em or agora_utc().isoformat(timespec="seconds"),
                      url=url, mercado=list(mercado_))
    analise.ajustes += _fatos(perfil, mestre)
    voc, lacunas, cobertura = _vocabulario(perfil, mestre, mercado_)
    analise.ajustes += voc
    analise.lacunas = lacunas
    analise.cobertura = cobertura
    analise.ajustes += _regua(perfil, mestre, mercado_)
    analise.ajustes.sort(key=lambda a: (a.prioridade, a.area))
    return analise
