"""Dossiê de candidatura: currículo sob medida, carta e link, para uma vaga.

Separado do envio de propósito. O orquestrador gerava esses documentos dentro de
`run_applications`, **depois** da guarda que descarta plataforma sem automação —
então uma vaga da Gupy ou da Lever virava `sem_automacao` e não recebia nada. As
322 vagas da Gupy morriam ali, sem currículo, sem carta, sem nada que o usuário
pudesse usar.

O acoplamento era invisível enquanto o objetivo era "o robô candidata". Deixou de
ser quando ficou claro onde está o valor: currículo específico por vaga já basta,
e clicar em enviar são dois minutos. Descobrir e ranquear a vaga é o trabalho
caro; o envio é o barato — e é justamente o envio que depende de terceiros que
mudam seletor e ligam CAPTCHA.

Então o dossiê é o produto, e o envio automático é um extra sobre ele. Vaga sem
automação passa a valer tanto quanto as outras: o usuário abre o link e envia à
mão, com o currículo já otimizado para aquela vaga na mão.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from jobapplier import idioma, paths, perfis

logger = logging.getLogger(__name__)


@dataclass
class Dossie:
    """O que o sistema entrega para uma vaga, com ou sem automação."""

    vaga_id: int
    pdf_path: Path | None = None
    cover_letter_path: Path | None = None
    cover_letter_texto: str = ""
    perfil: str = ""
    ats_antes: float = 0.0
    ats_depois: float = 0.0
    keywords_adicionadas: list[str] | None = None
    erro: str = ""

    @property
    def pronto(self) -> bool:
        """Só o PDF é obrigatório: é ele que vai para o recrutador.

        Carta é opcional em boa parte dos formulários, e falhar a candidatura
        inteira por causa dela desperdiçaria a otimização já feita.
        """
        return self.pdf_path is not None and self.pdf_path.exists()

    @property
    def ganho_ats(self) -> float:
        return round(self.ats_depois - self.ats_antes, 1)


def _como_dict(valor) -> dict:
    """Campo JSON do banco como dict, seja lá o que estiver lá.

    A coluna aceita texto, e JSON válido não garante objeto: uma lista ou um
    número decodificam bem e quebram no `.get()` de quem chamou.
    """
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except json.JSONDecodeError:
            return {}
    return valor if isinstance(valor, dict) else {}


def perfil_base(vaga, resume_json: dict) -> tuple[str, dict]:
    """Currículo base para a vaga: perfil pelo cargo, idioma pelo texto da vaga.

    O base é **derivado** do currículo mestre por `perfis.montar`, não lido de um
    arquivo por perfil. Os quatro arquivos que existiam antes eram cópias
    integrais do mestre e apodreceram: quando o mestre foi reescrito, seguiram
    afirmando FIAP em andamento, omitindo o telefone e nomeando o cliente. O
    score lia o mestre e não via nada; só o PDF lia as cópias.
    """
    # O perfil sugerido pode vir de dois lugares: `extracao` o grava em
    # `normalizado_json` e o scorer em `score_breakdown_json`. O orquestrador lia
    # só o segundo e esta função só o primeiro, então a mesma vaga escolhia
    # perfis diferentes conforme o caminho — os dois olham os dois agora.
    sugerido = None
    for campo in ("normalizado_json", "score_breakdown_json"):
        dados = _como_dict(getattr(vaga, campo, None))
        sugerido = dados.get("perfil_base_sugerido")
        if sugerido:
            break

    perfil = perfis.resolver(sugerido)
    lingua = idioma.da_vaga(vaga)
    base = perfis.montar(perfil, lingua, resume_json)

    if lingua == "en":
        logger.info("Vaga %s está em inglês — currículo montado em inglês.",
                    getattr(vaga, "id", "?"))
    return perfil, base


def montar(vaga, resume_json: dict, client=None) -> Dossie:
    """Gera currículo otimizado, PDF e carta para a vaga. Não envia nada.

    Chamável para QUALQUER vaga, com ou sem automação na plataforma. Erro aqui
    devolve um `Dossie` com `erro` preenchido em vez de levantar: a esteira
    processa uma fila, e uma vaga problemática não pode derrubar as outras.
    """
    from jobapplier.agents.cover_letter import generate as gerar_carta
    from jobapplier.agents.resume_optimizer import optimize
    from jobapplier.generators.pdf import generate_pdf

    paths.garantir(paths.RESUMES, paths.COVER_LETTERS)
    dossie = Dossie(vaga_id=vaga.id)

    try:
        perfil, base = perfil_base(vaga, resume_json)
        dossie.perfil = perfil

        otimizado = optimize(base, vaga, client)
        dossie.ats_antes = otimizado.get("ats_antes", 0.0)
        dossie.ats_depois = otimizado.get("ats_depois", 0.0)
        dossie.keywords_adicionadas = otimizado.get("keywords_adicionadas", [])

        # Invariante 8: `generate_pdf` verifica o layout por padrão e levanta
        # em problema grave. Falha fechada — currículo quebrado não sai.
        destino = paths.RESUMES / f"resume_{perfil}_{vaga.id}.pdf"
        generate_pdf(otimizado["perfil_otimizado"], destino)
        dossie.pdf_path = destino

        logger.info(
            "Dossiê da vaga %s: ATS %.0f%% -> %.0f%% (+%d keywords)",
            vaga.id, dossie.ats_antes, dossie.ats_depois,
            len(dossie.keywords_adicionadas or []),
        )
    except Exception as exc:
        logger.error("Falha ao montar o dossiê da vaga %s: %s", vaga.id, exc)
        dossie.erro = f"{type(exc).__name__}: {exc}"
        return dossie

    # A carta é opcional: sem ela o PDF ainda serve, e perder a otimização já
    # feita por causa de um texto ausente seria desperdício.
    try:
        # `base`, não `resume_json`: é o currículo já escolhido por idioma e
        # perfil. Passar o mestre bruto mandava carta em português junto de
        # currículo em inglês — metade da fila, no mesmo envelope.
        texto = gerar_carta(base, vaga, client)
        if texto:
            caminho = paths.COVER_LETTERS / f"cover_letter_{vaga.id}.txt"
            caminho.write_text(texto, encoding="utf-8")
            dossie.cover_letter_texto = texto
            dossie.cover_letter_path = caminho
    except Exception as exc:
        logger.warning("Carta da vaga %s não gerada: %s", vaga.id, exc)

    return dossie
