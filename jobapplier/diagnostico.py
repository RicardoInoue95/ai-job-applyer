"""Está tudo de pé? Uma resposta só, para todas as telas.

O sistema tem quatro partes que podem estar fora — contêiner do banco, migrations,
API local, dados do candidato — e até aqui cada uma falhava no seu próprio canto:
o banco parado virava traceback do SQLAlchemy na página, o schema atrasado só
aparecia no log do orquestrador, a API fora do ar virava "não respondeu" no aviso
da extensão, e currículo ausente só na hora de gerar o PDF.

Quem usa não deve precisar saber de qual das quatro veio o problema. Aqui cada
checagem devolve um erro do catálogo, com o que fazer — e a mesma lista serve a
`/saude`, à interface e à extensão. Uma fonte, três telas.

**Toda checagem é barata e sem efeito.** É chamada a cada abertura de página e a
cada carga da extensão: nada aqui escreve, abre browser ou toca rede de terceiro.
A idade da coleta sai do banco, não de uma requisição.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from jobapplier import erros, paths
from jobapplier.tempo import agora_utc

#: A partir de quantas horas sem coletar a fila é velha o bastante para avisar.
#: Seis: é o intervalo da varredura de encerradas, então passar disso significa
#: que nem a checagem de vaga morta rodou.
HORAS_COLETA_VELHA = 6


@dataclass
class Checagem:
    nome: str
    ok: bool
    #: Erro do catálogo quando `ok` é falso. Nunca preenchido junto com ok=True.
    erro: erros.Erro | None = None
    #: O caso concreto — "há 5 dias", "revisão 007 de 009".
    detalhe: str = ""
    #: Falha que não impede usar. Coleta velha atrapalha; banco fora, não deixa.
    aviso: bool = False

    def como_dict(self) -> dict:
        d = {"nome": self.nome, "ok": self.ok, "aviso": self.aviso}
        if self.erro is not None:
            d["erro"] = self.erro.como_dict(self.detalhe)
        elif self.detalhe:
            d["detalhe"] = self.detalhe
        return d


@dataclass
class Estado:
    checagens: list[Checagem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Só o que impede de trabalhar conta. Aviso não derruba o estado."""
        return all(c.ok or c.aviso for c in self.checagens)

    @property
    def bloqueios(self) -> list[Checagem]:
        return [c for c in self.checagens if not c.ok and not c.aviso]

    @property
    def avisos(self) -> list[Checagem]:
        return [c for c in self.checagens if not c.ok and c.aviso]

    def como_dict(self) -> dict:
        return {"ok": self.ok, "versao": 1,
                "checagens": [c.como_dict() for c in self.checagens]}


def _checar_banco() -> Checagem:
    from sqlalchemy import text

    from jobapplier.database.connection import get_session

    try:
        with get_session() as s:
            s.execute(text("select 1"))
    # Cego de propósito: driver, rede, DNS e contêiner parado levantam exceções
    # de famílias diferentes, e para quem lê a resposta é a mesma — não está no ar.
    except Exception as exc:
        return Checagem("banco", False, erros.BANCO_FORA, f"({type(exc).__name__})")
    return Checagem("banco", True)


def _checar_schema() -> Checagem:
    from jobapplier.database import schema

    try:
        estado = schema.verificar()
    except Exception:
        # Sem banco não há como saber a revisão. Quem reporta isso é a checagem
        # do banco; repetir aqui daria dois bloqueios para uma causa.
        return Checagem("schema", True, detalhe="não verificado (banco fora)")
    if estado.em_head:
        return Checagem("schema", True, detalhe=f"revisão {estado.aplicada}")
    return Checagem("schema", False, erros.SCHEMA_ATRASADO,
                    f"(aplicada {estado.aplicada}, esperada {estado.esperada})")


def _checar_curriculo() -> Checagem:
    if paths.RESUME_JSON.exists():
        return Checagem("curriculo", True)
    return Checagem("curriculo", False, erros.CURRICULO_AUSENTE)


def _checar_config() -> Checagem:
    from jobapplier.config.manager import ConfigManager

    config = ConfigManager()
    faltando = [nome for nome, valor in (
        ("cargos alvo", (config.get("coleta") or {}).get("cargos_alvo")),
        ("dados pessoais", config.get("dados_pessoais")),
    ) if not valor]
    if not faltando:
        return Checagem("config", True)
    # Só o NOME do que falta. O valor de `dados_pessoais` é CPF e telefone, e
    # isto vai para log e para a tela (invariante 12).
    return Checagem("config", False, erros.CONFIG_INCOMPLETA,
                    f"({', '.join(faltando)})")


def _checar_llm() -> Checagem:
    from jobapplier.config.manager import ConfigManager
    from jobapplier.llm import provedores_configurados

    if (ConfigManager().get("llm") or {}).get("modo_sem_api"):
        return Checagem("llm", True, detalhe="modo sem API, por escolha")
    if provedores_configurados():
        return Checagem("llm", True)
    # Aviso e não bloqueio: o pipeline inteiro roda sem LLM.
    return Checagem("llm", False, erros.SEM_PROVEDOR_LLM, aviso=True)


def _checar_coleta() -> Checagem:
    from sqlalchemy import func

    from jobapplier.database.connection import get_session
    from jobapplier.database.models import Vaga

    try:
        with get_session() as s:
            ultima = s.query(func.max(Vaga.ultima_coleta_em)).scalar()
    except Exception:
        return Checagem("coleta", True, detalhe="não verificada (banco fora)")
    if ultima is None:
        return Checagem("coleta", False, erros.COLETA_VELHA, "(nunca coletou)",
                        aviso=True)
    horas = (agora_utc().replace(tzinfo=None) - ultima).total_seconds() / 3600
    if horas <= HORAS_COLETA_VELHA:
        return Checagem("coleta", True, detalhe=ultima.strftime("%d/%m às %H:%M"))
    quando = f"há {horas / 24:.0f} dia(s)" if horas >= 48 else f"há {horas:.0f}h"
    return Checagem("coleta", False, erros.COLETA_VELHA, f"({quando})", aviso=True)


#: Ordem de dependência: sem banco, schema e coleta não têm o que dizer.
_CHECAGENS = (_checar_banco, _checar_schema, _checar_curriculo, _checar_config,
              _checar_llm, _checar_coleta)


def verificar() -> Estado:
    """Roda tudo. Uma checagem que explode não derruba as outras.

    Se o diagnóstico puder falhar, ele deixa de ser o lugar onde se olha quando
    algo está errado — que é a única razão de ele existir.
    """
    estado = Estado()
    for checar in _CHECAGENS:
        try:
            estado.checagens.append(checar())
        except Exception as exc:
            estado.checagens.append(
                Checagem(checar.__name__.removeprefix("_checar_"), True,
                         detalhe=f"checagem falhou ({type(exc).__name__})",
                         aviso=True))
    return estado
