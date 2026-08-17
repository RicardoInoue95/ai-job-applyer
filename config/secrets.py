"""Segredos vindos do ambiente, com fallback para data/config.json.

Antes: a API key do Gemini vivia em texto plano em ``data/config.json``, junto
com CPF e dados de diversidade. A única proteção era ``data/`` no .gitignore.

Agora: variáveis de ambiente (via ``.env``) têm precedência. O fallback para
config.json existe só para não quebrar instalações que ainda não migraram — ele
emite aviso uma vez por chave para você saber que ainda há segredo em disco.

Fase 1 substitui isso por tabela ``credenciais(usuario_id, provedor,
payload_cifrado)`` com Fernet, que é o desenho multi-usuário. Este módulo é a
fachada estável: os chamadores não mudam quando a implementação mudar.
"""
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

ENV_PATH = Path(".env")
PREFIXO = "AIJOB_"

_env_carregado = False
_avisos_emitidos: set[str] = set()


def carregar_env(path: Path = ENV_PATH, sobrescrever: bool = False) -> int:
    """Carrega pares KEY=VALUE de um arquivo .env para os.environ.

    Implementação mínima em vez de python-dotenv: são 20 linhas e evita uma
    dependência para algo que o projeto usa em um único ponto.

    Suporta comentários (#), linhas vazias, ``export KEY=v`` e valores entre
    aspas simples ou duplas. Retorna quantas chaves foram definidas.
    """
    global _env_carregado

    if not path.exists():
        _env_carregado = True
        return 0

    definidas = 0
    for linha_num, linha in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(), start=1
    ):
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        if linha.startswith("export "):
            linha = linha[len("export "):].strip()
        if "=" not in linha:
            logger.warning("%s:%d ignorada (sem '='): %r", path, linha_num, linha)
            continue

        chave, _, valor = linha.partition("=")
        chave = chave.strip()
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]

        if sobrescrever or chave not in os.environ:
            os.environ[chave] = valor
            definidas += 1

    _env_carregado = True
    logger.debug("%d variáveis carregadas de %s", definidas, path)
    return definidas


def _garantir_env() -> None:
    if not _env_carregado:
        carregar_env()


def gravar_env(nome_env: str, valor: str, path: Path = ENV_PATH) -> None:
    """Grava/atualiza uma chave no .env e no processo atual.

    Usado pelo wizard do Streamlit: chave de API digitada na UI vai para o .env
    (fora do git) em vez de data/config.json em texto plano. Preserva comentários
    e a ordem das linhas existentes.
    """
    chave_completa = f"{PREFIXO}{nome_env}"
    linha_nova = f"{chave_completa}={valor}"

    linhas: list[str] = []
    if path.exists():
        linhas = path.read_text(encoding="utf-8-sig").splitlines()

    for i, linha in enumerate(linhas):
        nua = linha.strip()
        if nua.startswith("export "):
            nua = nua[len("export "):].strip()
        if nua.split("=", 1)[0].strip() == chave_completa:
            linhas[i] = linha_nova
            break
    else:
        if linhas and linhas[-1].strip():
            linhas.append("")
        linhas.append(linha_nova)

    path.write_text("\n".join(linhas) + "\n", encoding="utf-8")

    # Reflete de imediato no processo, para não exigir restart do Streamlit.
    os.environ[chave_completa] = valor
    logger.info("Segredo %s gravado em %s", chave_completa, path)


def obter(
    nome_env: str,
    *caminho_config: str,
    default: str | None = None,
    config=None,
) -> str | None:
    """Busca um segredo: ambiente primeiro, config.json depois.

    ``nome_env`` é o sufixo após AIJOB_ (ex: "GEMINI_API_KEY").
    ``caminho_config`` é o caminho aninhado no config.json (ex: "gemini", "api_key").
    ``config`` é um ConfigManager específico; omitido, usa o padrão. Existe para
    que ``ConfigManager(path=X).get_gemini_key()`` continue consultando X no
    fallback em vez de silenciosamente ler outro arquivo.
    """
    _garantir_env()

    chave_completa = f"{PREFIXO}{nome_env}"
    valor = os.environ.get(chave_completa)
    if valor:
        return valor

    if caminho_config:
        if config is None:
            from config.manager import ConfigManager

            config = ConfigManager()

        valor = config.get(*caminho_config)
        if valor:
            if chave_completa not in _avisos_emitidos:
                _avisos_emitidos.add(chave_completa)
                logger.warning(
                    "Segredo '%s' lido de data/config.json em texto plano. "
                    "Mova para .env como %s e remova do JSON.",
                    ".".join(caminho_config), chave_completa,
                )
            return valor

    return default


def gemini_api_key(config=None) -> str | None:
    return obter("GEMINI_API_KEY", "gemini", "api_key", config=config)


def database_url(config=None) -> str:
    return (
        obter("DATABASE_URL", "database_url", config=config)
        or "postgresql://jobapplier:jobapplier@localhost:5432/jobapplier"
    )


def smtp_credenciais(config=None) -> tuple[str | None, str | None]:
    return (
        obter("SMTP_USER", "email", "smtp_user", config=config),
        obter("SMTP_PASS", "email", "smtp_pass", config=config),
    )
