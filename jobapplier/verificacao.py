"""Código de verificação de envio, lido da caixa de e-mail do candidato.

Existe para uma etapa específica: plataformas como a Adyen só submetem a
candidatura depois que o candidato digita um código de 8 caracteres enviado ao
e-mail dele. O formulário fica 100% preenchido e para ali.

**Onde está a linha.** O controle pergunta "há um humano decidindo mandar esta
candidatura?". Se o candidato está na frente da máquina e aprova aquela
candidatura, a resposta honesta é sim — e quem digita os oito caracteres é
detalhe, do mesmo jeito que o preenchimento automático de OTP do celular não
torna a pessoa um robô. Se o sistema puxasse o código sozinho e submetesse a
fila inteira de madrugada, a resposta seria não, e aí seria exatamente o que o
controle existe para impedir.

Por isso este módulo **só lê**. Ele não clica em enviar, e nada aqui submete
formulário. Quem submete é `scripts/finalizar.py`, com navegador visível, e o
clique final é do candidato no botão real da página.

**Escopo do acesso.** IMAP no Gmail dá a caixa inteira, então o alcance é
apertado no código, não na intenção: só mensagens recentes, só de remetentes
esperados, só o campo assunto/corpo procurando um padrão de código. O valor
encontrado nunca é logado — desde que o log passou a gravar em
`data/logs/*.jsonl`, logar seria deixá-lo em disco (invariante 11).
"""
from __future__ import annotations

import contextlib
import email
import imaplib
import logging
import re
from dataclasses import dataclass
from email.header import decode_header, make_header

from jobapplier.tempo import agora_utc

logger = logging.getLogger(__name__)

#: Janela de busca. Código de verificação é efêmero por definição; procurar
#: mensagem antiga só aumenta a chance de pegar o código de outra candidatura.
JANELA_MINUTOS = 15

#: Remetentes aceitos. Lista fechada de propósito: sem ela, qualquer e-mail com
#: um número de 6 a 8 dígitos viraria "o código" — inclusive um de banco.
REMETENTES = (
    "greenhouse.io",
    "us.greenhouse-mail.io",
    "myworkday.com",
    "lever.co",
    "adyen.com",
)

#: O código em si. Greenhouse usa 8 alfanuméricos maiúsculos; outras usam 6
#: dígitos. Exige fronteira de palavra para não recortar pedaço de URL ou id.
_PADROES = (
    re.compile(r"\b([A-Z0-9]{8})\b"),
    re.compile(r"\b(\d{6})\b"),
)

#: Palavras que precisam estar perto do código. Sem isso, o primeiro id de
#: rastreamento de 8 caracteres do rodapé passaria por código.
_CONTEXTO = ("code", "código", "codigo", "verification", "verificação",
             "verificacao", "confirm", "security")


class VerificacaoIndisponivel(RuntimeError):
    """IMAP não configurado ou inacessível. Mensagem diz o que fazer."""


@dataclass(frozen=True)
class Achado:
    codigo: str
    remetente: str
    assunto: str

    def __repr__(self) -> str:  # pragma: no cover - proteção contra log acidental
        """Nunca mostra o código.

        `logger.info("%s", achado)` e um traceback com variáveis locais são as
        duas formas fáceis de o código parar em `data/logs/*.jsonl`.
        """
        return f"Achado(codigo=<oculto>, remetente={self.remetente!r})"


def credenciais(config=None) -> tuple[str | None, str | None, str]:
    """(usuário, senha, servidor). Sem fallback para `config.json`.

    Segredo novo vai só para o `.env` (invariante 5), e este é o mais sensível
    que o projeto já pediu: dá acesso de leitura à caixa inteira. Use uma
    **senha de app** dedicada, nunca a senha da conta — ela é revogável sozinha.
    """
    from jobapplier.config.secrets import obter

    return (
        obter("IMAP_USER", config=config),
        obter("IMAP_PASS", config=config),
        obter("IMAP_HOST", config=config) or "imap.gmail.com",
    )


def configurado(config=None) -> bool:
    usuario, senha, _ = credenciais(config)
    return bool(usuario and senha)


def _texto(mensagem) -> str:
    """Assunto + corpo em texto puro. HTML entra sem as tags."""
    partes = [str(make_header(decode_header(mensagem.get("Subject") or "")))]
    for parte in mensagem.walk():
        if parte.get_content_maintype() != "text":
            continue
        try:
            bruto = parte.get_payload(decode=True) or b""
            texto = bruto.decode(parte.get_content_charset() or "utf-8",
                                 errors="replace")
        except Exception:
            continue
        if parte.get_content_subtype() == "html":
            texto = re.sub(r"<[^>]+>", " ", texto)
        partes.append(texto)
    return " ".join(partes)


#: O código vem DEPOIS da palavra de contexto ("your code is XXXX"), e perto.
#: Uma janela larga em volta deixaria o primeiro id de 8 caracteres do texto
#: enxergar um "verification code" que só aparece uma frase adiante — foi assim
#: que "Reference ZZZZ0000 ... Your verification code is 7K2M9XQP" devolvia
#: ZZZZ0000, preenchendo o campo com convicção e o valor errado.
_ALCANCE_DEPOIS = 60
#: Um pouco de folga para "XXXX is your code", que é raro mas existe.
_ALCANCE_ANTES = 25


def extrair_codigo(texto: str) -> str | None:
    """O código dentro do texto, ou None.

    Escolhe o candidato mais próximo de uma palavra de contexto, e só aceita
    quem estiver dentro do alcance. Um e-mail de candidatura tem vários trechos
    de 8 caracteres maiúsculos — id de vaga, hash de rastreamento —, então
    "tem contexto em algum lugar do parágrafo" não basta.
    """
    if not texto:
        return None
    baixo = texto.lower()

    marcas = [(m.start(), m.end())
              for p in _CONTEXTO for m in re.finditer(re.escape(p), baixo)]
    if not marcas:
        return None

    melhor: tuple[int, str] | None = None
    for padrao in _PADROES:
        for m in padrao.finditer(texto):
            for ini_marca, fim_marca in marcas:
                if fim_marca <= m.start():
                    distancia = m.start() - fim_marca
                    limite = _ALCANCE_DEPOIS
                else:
                    distancia = ini_marca - m.end()
                    limite = _ALCANCE_ANTES
                if 0 <= distancia <= limite and (melhor is None or distancia < melhor[0]):
                    melhor = (distancia, m.group(1))
        if melhor is not None:
            # Padrão mais específico primeiro: achado um código de 8, não vale
            # trocar por um de 6 dígitos que por acaso esteja mais colado.
            break
    return melhor[1] if melhor else None


def buscar_codigo(config=None, remetentes: tuple[str, ...] = REMETENTES,
                  janela_minutos: int = JANELA_MINUTOS) -> Achado | None:
    """Lê a caixa e devolve o código mais recente, ou None se não houver.

    Somente leitura: a caixa é aberta com `readonly=True`, então nada é marcado,
    movido ou apagado — se algo der errado aqui, o e-mail do usuário continua
    exatamente como estava.
    """
    usuario, senha, servidor = credenciais(config)
    if not (usuario and senha):
        raise VerificacaoIndisponivel(
            "IMAP não configurado. Defina AIJOB_IMAP_USER e AIJOB_IMAP_PASS no "
            ".env com uma senha de app dedicada (Gmail: Conta > Segurança > "
            "Senhas de app). Nunca use a senha da conta."
        )

    desde = (agora_utc()).strftime("%d-%b-%Y")
    try:
        conexao = imaplib.IMAP4_SSL(servidor)
    except Exception as exc:
        raise VerificacaoIndisponivel(f"não consegui falar com {servidor}: {exc}") from exc

    try:
        conexao.login(usuario, senha)
        conexao.select("INBOX", readonly=True)

        achados: list[Achado] = []
        for remetente in remetentes:
            ok, dados = conexao.search(None, "FROM", f'"{remetente}"',
                                       "SINCE", desde)
            if ok != "OK" or not dados or not dados[0]:
                continue
            # Do mais novo para o mais velho: o código mais recente é o daquela
            # candidatura, e os anteriores já expiraram.
            for num in reversed(dados[0].split()):
                ok, bruto = conexao.fetch(num, "(RFC822)")
                if ok != "OK" or not bruto or not isinstance(bruto[0], tuple):
                    continue
                mensagem = email.message_from_bytes(bruto[0][1])
                if not _recente(mensagem, janela_minutos):
                    break
                codigo = extrair_codigo(_texto(mensagem))
                if codigo:
                    achados.append(Achado(
                        codigo=codigo, remetente=remetente,
                        assunto=str(make_header(decode_header(
                            mensagem.get("Subject") or ""))),
                    ))
                    break
        # Sem `codigo` no log, aqui e em qualquer lugar.
        logger.info("Busca de verificação: %d remetente(s) com código recente.",
                    len(achados))
        return achados[0] if achados else None
    finally:
        # Falha no logout não pode mascarar o resultado nem a exceção original;
        # a conexão morre sozinha de qualquer jeito.
        with contextlib.suppress(Exception):
            conexao.logout()


def _recente(mensagem, janela_minutos: int) -> bool:
    from email.utils import parsedate_to_datetime

    try:
        quando = parsedate_to_datetime(mensagem.get("Date"))
    except Exception:
        return False
    if quando is None:
        return False
    if quando.tzinfo is not None:
        quando = quando.replace(tzinfo=None) - quando.utcoffset()
    idade = (agora_utc() - quando).total_seconds() / 60
    return -2 <= idade <= janela_minutos
