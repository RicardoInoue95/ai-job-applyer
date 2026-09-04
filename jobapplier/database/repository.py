
from sqlalchemy.orm import Session

from jobapplier.tempo import agora_utc

from .models import CacheGemini, Candidatura, Vaga


class CandidaturaRepository:
    """Desfecho de candidatura, um registro por (vaga, ciclo).

    Grava por atualização quando o par já existe. Antes era sempre `INSERT`, e a
    constraint `uq_candidaturas_vaga_ciclo` — que existe de propósito, para a
    idempotência ser garantida pelo banco e não por checagem em código —
    transformava isso num bug sério:

    o **modo sombra grava uma candidatura `simulada`**, e o modo sombra é o
    padrão que o próprio projeto manda rodar "por algumas semanas" antes de
    ligar o envio. Passadas essas semanas, toda vaga tocada em sombra ficava
    impossível de candidatar de verdade: o `INSERT` batia na constraint, a vaga
    virava `erro`, e o tratamento de erro tentava inserir *outra* candidatura na
    mesma chave — falha dupla, com a exceção original perdida. Havia 60 vagas
    nesse estado.

    Atualizar é o certo, não um contorno: simulação e envio real são a **mesma**
    tentativa naquela vaga. Recandidatura deliberada é o que incrementa `ciclo`,
    exatamente como o comentário da constraint descreve.
    """

    def __init__(self, session: Session):
        self.session = session

    def registrar(self, vaga_id: int, ciclo: int = 1, **campos) -> Candidatura:
        """Cria ou atualiza o registro daquela tentativa e devolve a linha."""
        cand = (
            self.session.query(Candidatura)
            .filter(Candidatura.vaga_id == vaga_id, Candidatura.ciclo == ciclo)
            .one_or_none()
        )
        if cand is None:
            cand = Candidatura(vaga_id=vaga_id, ciclo=ciclo, **campos)
            self.session.add(cand)
            return cand

        for chave, valor in campos.items():
            setattr(cand, chave, valor)
        cand.atualizado_em = agora_utc()
        return cand


class VagaRepository:
    def __init__(self, session: Session):
        self.session = session

    def exists_by_hash(self, hash_: str) -> bool:
        return (
            self.session.query(Vaga).filter(Vaga.hash == hash_).first() is not None
        )

    def create(self, vaga: Vaga) -> Vaga:
        self.session.add(vaga)
        self.session.flush()
        return vaga

    def bulk_create_if_not_exists(self, vagas: list[Vaga]) -> tuple[int, int]:
        """Insere as vagas novas. Retorna (inseridas, ignoradas).

        Dedup por identidade da plataforma quando existe `fonte_vaga_id`, caindo
        para o `hash` legado quando não existe. A identidade é preferida porque
        sobrevive a link com parâmetro extra, republicação e mudança de título.

        Duas consultas no total, não uma por linha. A versão anterior fazia um
        SELECT por vaga: com ~150 slugs do Greenhouse produzindo milhares de
        vagas por ciclo, eram milhares de round-trips.
        """
        if not vagas:
            return 0, 0

        agora = agora_utc()

        hashes = {v.hash for v in vagas if v.hash}
        identidades = {
            (v.plataforma.lower(), v.fonte_vaga_id)
            for v in vagas
            if v.fonte_vaga_id
        }

        existentes_hash: set[str] = set()
        if hashes:
            existentes_hash = {
                h for (h,) in self.session.query(Vaga.hash).filter(Vaga.hash.in_(hashes))
            }

        existentes_id: set[tuple[str, str]] = set()
        if identidades:
            ids_procurados = {i[1] for i in identidades}
            existentes_id = {
                (p.lower(), fid)
                for p, fid in self.session.query(Vaga.plataforma, Vaga.fonte_vaga_id)
                .filter(Vaga.fonte_vaga_id.in_(ids_procurados))
                if fid
            }

        inserted = skipped = 0
        # Também deduplica dentro do próprio lote: a busca por keyword do Gupy
        # devolve a mesma vaga em keywords diferentes.
        vistos_hash: set[str] = set()
        vistos_id: set[tuple[str, str]] = set()

        for vaga in vagas:
            identidade = (
                (vaga.plataforma.lower(), vaga.fonte_vaga_id)
                if vaga.fonte_vaga_id else None
            )

            # As duas checagens somam, não se substituem. Usar identidade EM VEZ
            # de hash quebrava a coleta inteira: linhas coletadas antes da
            # migration 004 têm fonte_vaga_id nulo, então a busca por identidade
            # não as encontrava, a inserção seguia, e o unique legado do hash
            # estourava — derrubando o lote e, com ele, todo o ciclo de coleta.
            duplicada = (
                vaga.hash in existentes_hash
                or vaga.hash in vistos_hash
                or (identidade is not None
                    and (identidade in existentes_id or identidade in vistos_id))
            )

            if duplicada:
                skipped += 1
                continue

            vaga.primeira_coleta_em = vaga.primeira_coleta_em or agora
            vaga.ultima_coleta_em = agora
            self.session.add(vaga)
            inserted += 1

            if identidade is not None:
                vistos_id.add(identidade)
            if vaga.hash:
                vistos_hash.add(vaga.hash)

        self.session.flush()
        return inserted, skipped

    def marcar_revistas(self, vagas: list[Vaga]) -> int:
        """Atualiza `ultima_coleta_em` das vagas já conhecidas que reapareceram.

        Serve para saber que a vaga continua publicada. Sem isso não há como
        distinguir "vaga ainda aberta" de "vaga que saiu do ar", e portanto não há
        como preencher `encerrada_em`.
        """
        if not vagas:
            return 0

        agora = agora_utc()
        ids = [v.fonte_vaga_id for v in vagas if v.fonte_vaga_id]
        hashes = [v.hash for v in vagas if not v.fonte_vaga_id and v.hash]

        atualizadas = 0
        if ids:
            atualizadas += (
                self.session.query(Vaga)
                .filter(Vaga.fonte_vaga_id.in_(ids))
                .update({"ultima_coleta_em": agora}, synchronize_session=False)
            )
        if hashes:
            atualizadas += (
                self.session.query(Vaga)
                .filter(Vaga.hash.in_(hashes))
                .update({"ultima_coleta_em": agora}, synchronize_session=False)
            )
        return atualizadas

    def list_novas(self) -> list[Vaga]:
        return self.session.query(Vaga).filter(Vaga.status == "nova").all()

    def count(self) -> int:
        return self.session.query(Vaga).count()


class CacheGeminiRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, chave_hash: str) -> CacheGemini | None:
        now = agora_utc()
        return (
            self.session.query(CacheGemini)
            .filter(
                CacheGemini.chave_hash == chave_hash,
                CacheGemini.expira_em > now,
            )
            .first()
        )

    def set(self, entry: CacheGemini) -> None:
        existing = (
            self.session.query(CacheGemini)
            .filter(CacheGemini.chave_hash == entry.chave_hash)
            .first()
        )
        if existing:
            existing.resposta = entry.resposta
            existing.expira_em = entry.expira_em
            existing.criado_em = agora_utc()
        else:
            self.session.add(entry)
        self.session.flush()

    def purge_expired(self) -> int:
        now = agora_utc()
        deleted = (
            self.session.query(CacheGemini)
            .filter(CacheGemini.expira_em <= now)
            .delete()
        )
        self.session.flush()
        return deleted
