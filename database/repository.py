from datetime import datetime

from sqlalchemy.orm import Session

from .models import CacheGemini, Vaga


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
        inserted = 0
        skipped = 0
        for vaga in vagas:
            if not self.exists_by_hash(vaga.hash):
                self.session.add(vaga)
                inserted += 1
            else:
                skipped += 1
        self.session.flush()
        return inserted, skipped

    def list_novas(self) -> list[Vaga]:
        return self.session.query(Vaga).filter(Vaga.status == "nova").all()

    def count(self) -> int:
        return self.session.query(Vaga).count()


class CacheGeminiRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, chave_hash: str) -> CacheGemini | None:
        now = datetime.utcnow()
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
            existing.criado_em = datetime.utcnow()
        else:
            self.session.add(entry)
        self.session.flush()

    def purge_expired(self) -> int:
        now = datetime.utcnow()
        deleted = (
            self.session.query(CacheGemini)
            .filter(CacheGemini.expira_em <= now)
            .delete()
        )
        self.session.flush()
        return deleted
