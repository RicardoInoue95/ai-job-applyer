"""Coletor de vagas — LinkedIn.

A coleta vivia dentro de `applicators/linkedin.py`, onde ninguém procura por
coletor: quem abre `collectors/` para entender de onde vêm as vagas concluía que
o LinkedIn não coletava. O teste de contrato do registro de plataformas pegou
isso — declarava `coletor="linkedin"` para um módulo inexistente.

Este módulo é a porta de entrada; a raspagem continua em `applicators/linkedin.py`
porque depende da mesma sessão salva que a candidatura usa, e duplicar o
gerenciamento de sessão criaria dois lugares para expirar.

Diferente das outras plataformas em dois pontos que importam:

**É opt-in e depende de login manual.** Sem sessão gravada, devolve lista vazia
sem erro — o núcleo Greenhouse/Gupy/inhire funciona sem o LinkedIn (invariante 6).

**Cada vaga custa uma página aberta.** A lista de resultados não traz descrição,
e sem descrição a vaga não passa no filtro 4A — foi assim que 200 vagas viraram
192 `filtrada_4a` e 8 `erro`. Por isso há teto e ritmo entre aberturas: volume é
o que a detecção procura.
"""
import logging

from jobapplier.collectors.base import BaseCollector, CollectedJob

logger = logging.getLogger(__name__)

#: Queries padrão quando a config não define nenhuma.
QUERIES_PADRAO = ("Analista de Dados", "Engenheiro de Dados", "Analytics Engineer")

LOCAL_PADRAO = "São Paulo, BR"


class LinkedInCollector(BaseCollector):
    platform = "linkedin"

    def collect(self, company_slug: str) -> list[CollectedJob]:
        """O LinkedIn não coleta por empresa; a busca é por palavra-chave.

        Existe para satisfazer o contrato de `BaseCollector` — usar
        `collect_by_search`.
        """
        logger.debug("LinkedIn não coleta por slug; use collect_by_search.")
        return []

    def collect_by_search(self, queries: list[str] | None = None,
                          location: str = LOCAL_PADRAO,
                          max_per_query: int = 25) -> list[CollectedJob]:
        """Busca por palavra-chave usando a sessão salva.

        Descarta o que não tem título real ou descrição: gravar essas produz
        linha morta no banco, com custo de rede e de exposição, e zero vaga
        aproveitável.
        """
        from jobapplier.applicators.linkedin import collect_jobs, has_session

        if not has_session():
            logger.info("LinkedIn sem sessão gravada — coleta ignorada.")
            return []

        brutas = collect_jobs(list(queries or QUERIES_PADRAO), location=location,
                              max_per_query=max_per_query)

        vagas, descartadas = [], 0
        for bruta in brutas:
            if bruta.get("titulo_provisorio") or not (bruta.get("descricao") or "").strip():
                descartadas += 1
                continue
            vagas.append(CollectedJob(
                titulo=bruta["titulo"],
                empresa=bruta.get("empresa") or "",
                plataforma="linkedin",
                link=bruta["link"],
                descricao=bruta.get("descricao", ""),
                localizacao=bruta.get("localizacao"),
                fonte_vaga_id=bruta.get("fonte_vaga_id"),
            ))

        if descartadas:
            logger.warning(
                "LinkedIn: %d vaga(s) descartada(s) por falta de título real ou "
                "descrição — sem texto elas não passam do filtro 4A.", descartadas,
            )
        logger.info("LinkedIn: %d vaga(s) aproveitada(s).", len(vagas))
        return vagas
