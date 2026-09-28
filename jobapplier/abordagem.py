"""O que dizer ao responder um anúncio: e-mail, LinkedIn e WhatsApp.

A carta de apresentação (`agents/cover_letter.py`) responde a um formulário. Um
post pede outra coisa: uma mensagem curta, para uma pessoa, no canal que ela
escolheu. Três canais, três tamanhos — e o mesmo conteúdo factual.

**Nada aqui afirma o que o currículo não sustenta** (invariante 3). O texto é
montado de quatro fatos, todos do mestre: nome, cargo atual, as tecnologias
pedidas pela vaga que o candidato de fato usa, e o contato. Empresa e cargo vêm
do post; faltando, a saudação fica neutra em vez de inventar um nome.

Sem LLM de propósito, como a carta sem modelo: o texto é curto e factual, e um
parágrafo de entusiasmo genérico gerado por modelo seria pior que a frase seca.
Um modelo pode reescrever depois — o ponto é que **existe** mensagem pronta
sem depender de chave.

Limites que vêm dos canais, não de gosto:

- **LinkedIn**: convite com nota aceita 300 caracteres. A mensagem sai em 280
  para caber com folga; passando disso, o LinkedIn corta no meio da frase.
- **WhatsApp**: sem limite prático, mas mensagem longa de desconhecido não se
  lê. Fica em ~400.
- **E-mail**: o assunto é o que o post pediu, quando pediu — é por ele que o
  recrutador filtra a caixa.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

LIMITE_LINKEDIN = 280
LIMITE_WHATSAPP = 400

#: Um gabarito por idioma, numa tabela só — acrescentar idioma é acrescentar
#: chave, não caçar f-string no meio da função (mesma decisão de `cover_letter`).
_FRASES = {
    "pt": {
        "ola_com_nome": "Olá, {nome}!",
        "ola": "Olá!",
        "vi_post": "Vi o seu anúncio da vaga de {cargo}",
        "vi_post_empresa": "Vi o seu anúncio da vaga de {cargo} na {empresa}",
        "cliente": " — cliente {cliente}",
        "sou": "Sou {nome}, {cargo_atual}",
        "sou_empresa": "Sou {nome}, {cargo_atual} na {empresa_atual}",
        "tecnologias": "Das tecnologias do anúncio, trabalho com {lista}",
        "curriculo_anexo": "Segue o currículo em anexo.",
        "curriculo_posso": "Posso enviar o currículo por aqui, se ajudar.",
        "disposicao": "Fico à disposição.",
        "assunto_padrao": "{cargo} — {nome}",
        "candidatura": "Candidatura",
    },
    "en": {
        "ola_com_nome": "Hello, {nome}!",
        "ola": "Hello!",
        "vi_post": "I saw your post about the {cargo} role",
        "vi_post_empresa": "I saw your post about the {cargo} role at {empresa}",
        "cliente": " — client {cliente}",
        "sou": "I am {nome}, {cargo_atual}",
        "sou_empresa": "I am {nome}, {cargo_atual} at {empresa_atual}",
        "tecnologias": "Of the technologies in the post, I work with {lista}",
        "curriculo_anexo": "My resume is attached.",
        "curriculo_posso": "I can send my resume here if that helps.",
        "disposicao": "I am happy to talk whenever it suits you.",
        "assunto_padrao": "{cargo} — {nome}",
        "candidatura": "Application",
    },
}


def _tecnologias_em_comum(vaga, resume: dict) -> list[str]:
    """As que a vaga pede E o currículo tem. A interseção é o ponto: citar uma
    tecnologia pedida que o candidato não usa é exatamente o que a invariante 3
    proíbe."""
    from jobapplier import vocabulario as vocab

    normalizado = getattr(vaga, "normalizado_json", None) or {}
    tec_vaga = normalizado.get("tecnologias") or []
    tec_curriculo = {vocab.canonizar(t) for t in (resume.get("tecnologias") or [])}
    return [t for t in tec_vaga if vocab.canonizar(t) in tec_curriculo]


def _lista(itens: list[str], maximo: int, lingua: str) -> str:
    """`A, B e C` — sem "e mais 12", que lê como currículo despejado."""
    itens = itens[:maximo]
    if not itens:
        return ""
    if len(itens) == 1:
        return itens[0]
    conector = " e " if lingua == "pt" else " and "
    return ", ".join(itens[:-1]) + conector + itens[-1]


def _cargo_e_empresa_atuais(resume: dict) -> tuple[str, str]:
    experiencias = resume.get("experiencias") or []
    atual = next((e for e in experiencias if not e.get("data_fim")), None)
    atual = atual or (experiencias[0] if experiencias else {})
    return (atual.get("cargo") or "").strip(), (atual.get("empresa") or "").strip()


def _cargo_da_vaga(post, vaga) -> str:
    normalizado = getattr(vaga, "normalizado_json", None) or {}
    return (normalizado.get("cargo") or getattr(post, "titulo", "")
            or getattr(vaga, "titulo", "") or "").strip()


def _empresa_da_vaga(post, vaga) -> str:
    from jobapplier import empresas

    bruto = getattr(post, "empresa", "") or getattr(vaga, "empresa", "") or ""
    if bruto.startswith("("):     # "(empresa não informada)"
        return ""
    return empresas.nome_exibicao(bruto) or bruto


def _contato_do_candidato(resume: dict) -> list[str]:
    """Assinatura: só o que está no mestre (invariante 11)."""
    return [v for v in (resume.get("email"), resume.get("telefone"),
                        resume.get("linkedin")) if v]


def montar(post, vaga, resume: dict, dossie=None) -> dict:
    """As três mensagens, prontas para copiar.

    `resume` é o currículo **que vai junto** — o base já escolhido por perfil e
    idioma em `dossie.perfil_base`, não o mestre bruto. Foi assim que a carta
    parou de sair em português ao lado de um currículo em inglês.
    """
    from jobapplier import idioma as mod_idioma

    lingua = mod_idioma.detectar(resume.get("resumo_profissional") or "")
    t = _FRASES.get(lingua, _FRASES["pt"])

    cargo = _cargo_da_vaga(post, vaga)
    empresa = _empresa_da_vaga(post, vaga)
    nome = (resume.get("nome") or "").strip()
    cargo_atual, empresa_atual = _cargo_e_empresa_atuais(resume)
    comuns = _tecnologias_em_comum(vaga, resume)
    contato = getattr(post, "contato", None)
    tem_anexo = bool(dossie is not None and getattr(dossie, "pronto", False))

    return {
        "email": _email(t, post, contato, cargo, empresa, nome, cargo_atual,
                        empresa_atual, comuns, resume, lingua, tem_anexo),
        "linkedin": _linkedin(t, contato, cargo, empresa, nome, cargo_atual,
                              empresa_atual, comuns, lingua),
        "whatsapp": _whatsapp(t, contato, cargo, empresa, nome, cargo_atual,
                              empresa_atual, comuns, lingua),
    }


def _apresentacao(t, nome, cargo_atual, empresa_atual) -> str:
    if not cargo_atual:
        return ""
    if empresa_atual:
        return t["sou_empresa"].format(nome=nome, cargo_atual=cargo_atual,
                                       empresa_atual=empresa_atual)
    return t["sou"].format(nome=nome, cargo_atual=cargo_atual)


def _abertura(t, cargo, empresa) -> str:
    if cargo and empresa:
        return t["vi_post_empresa"].format(cargo=cargo, empresa=empresa)
    if cargo:
        return t["vi_post"].format(cargo=cargo)
    return t["vi_post"].format(cargo=t["candidatura"].lower())


def _email(t, post, contato, cargo, empresa, nome, cargo_atual, empresa_atual,
           comuns, resume, lingua, tem_anexo) -> dict:
    """Assunto + corpo + destinatário. O assunto pedido no post vence o padrão:
    é por ele que o recrutador filtra, e trocá-lo por um "melhor" é ignorar a
    única instrução explícita do anúncio."""
    assunto = (getattr(contato, "assunto", "") or "").strip()
    if not assunto:
        assunto = t["assunto_padrao"].format(cargo=cargo or t["candidatura"], nome=nome)

    saudacao = (t["ola_com_nome"].format(nome=getattr(contato, "autor", "").split()[0])
                if getattr(contato, "autor", "") else t["ola"])

    # O cliente final só entra no e-mail: mostra que o anúncio foi lido, e é
    # fato do post. Nas mensagens curtas não cabe (ver `_encurtar`).
    cliente = (getattr(post, "cliente", "") or "").strip()
    abertura = _abertura(t, cargo, empresa)
    if cliente and empresa:
        abertura += t["cliente"].format(cliente=cliente)
    corpo = [saudacao, "", abertura + "."]
    apresentacao = _apresentacao(t, nome, cargo_atual, empresa_atual)
    if apresentacao:
        corpo += ["", apresentacao + "."]
    if comuns:
        corpo += ["", t["tecnologias"].format(lista=_lista(comuns, 6, lingua)) + "."]
    corpo += ["", t["curriculo_anexo"] if tem_anexo else t["curriculo_posso"],
              t["disposicao"], "", nome]
    corpo += _contato_do_candidato(resume)

    return {
        "para": list(getattr(contato, "emails", []) or []),
        "assunto": assunto,
        "corpo": "\n".join(corpo).strip(),
        "anexar": "currículo em PDF" if tem_anexo else "",
    }


def _encurtar(partes: list[str], limite: int) -> str:
    """Monta a mensagem e corta pelo fim, frase inteira por vez.

    Cortar no meio da palavra é o que o próprio LinkedIn faz com reticências, e
    a última frase a cair é sempre a menos importante — a lista de tecnologias
    vem antes do pedido, e o pedido é o que precisa sobreviver.
    """
    texto = " ".join(p for p in partes if p).strip()
    if len(texto) <= limite:
        return texto
    while len(partes) > 2:
        partes.pop(-2)         # penúltima: tecnologias, depois apresentação
        texto = " ".join(p for p in partes if p).strip()
        if len(texto) <= limite:
            return texto
    return texto[: limite - 1].rstrip() + "…"


def _linkedin(t, contato, cargo, empresa, nome, cargo_atual, empresa_atual,
              comuns, lingua) -> dict:
    saudacao = (t["ola_com_nome"].format(nome=getattr(contato, "autor", "").split()[0])
                if getattr(contato, "autor", "") else t["ola"])
    partes = [
        saudacao,
        _abertura(t, cargo, empresa) + ".",
        (_apresentacao(t, nome, cargo_atual, empresa_atual) + ".") if cargo_atual else "",
        (t["tecnologias"].format(lista=_lista(comuns, 3, lingua)) + ".") if comuns else "",
        t["curriculo_posso"],
    ]
    texto = _encurtar(partes, LIMITE_LINKEDIN)
    return {
        "texto": texto,
        "caracteres": len(texto),
        "limite": LIMITE_LINKEDIN,
        "perfis": list(getattr(contato, "perfis_linkedin", []) or []),
    }


def _whatsapp(t, contato, cargo, empresa, nome, cargo_atual, empresa_atual,
              comuns, lingua) -> dict:
    partes = [
        t["ola"],
        _abertura(t, cargo, empresa) + ".",
        (_apresentacao(t, nome, cargo_atual, empresa_atual) + ".") if cargo_atual else "",
        (t["tecnologias"].format(lista=_lista(comuns, 4, lingua)) + ".") if comuns else "",
        t["curriculo_posso"],
    ]
    texto = _encurtar(partes, LIMITE_WHATSAPP)
    link = getattr(contato, "whatsapp_link", lambda: "")()
    from urllib.parse import quote

    return {
        "texto": texto,
        "caracteres": len(texto),
        "numeros": list(getattr(contato, "telefones", []) or []),
        # Link que abre a conversa com a mensagem já escrita. Abrir é seu.
        "link": f"{link}?text={quote(texto)}" if link else "",
    }


def pontos_de_atencao(post, conclusao: dict) -> list[str]:
    """O que o número não vê e o recrutador veria.

    Mesma régua do "revisar vaga é trabalho de RH" do projeto: o score mede
    sobreposição de palavra-chave, e o que decide aqui é outra coisa — salário
    abaixo do piso, senioridade que não é a sua, canal de resposta ausente.
    """
    from jobapplier import salario as mod_salario

    avisos: list[str] = []
    if conclusao.get("atencao"):
        avisos.append(conclusao["atencao"])

    faixa = mod_salario.carregar_faixa()
    publicada = mod_salario.extrair_faixa_publicada(
        f"{getattr(post, 'salario', '')} {getattr(post, 'descricao', '')}")
    if faixa and publicada and publicada[1] < faixa.minimo:
        avisos.append(
            f"O anúncio paga até R$ {publicada[1]:,.0f}".replace(",", ".")
            + f", abaixo do seu mínimo de R$ {faixa.minimo:,.0f}".replace(",", ".")
            + ".")

    nivel = (getattr(post, "senioridade", "") or "").lower()
    titulo = (getattr(post, "titulo", "") or "").lower()
    if "júnior" in f"{nivel} {titulo}" or "junior" in f"{nivel} {titulo}":
        avisos.append("A vaga é júnior — confira se a faixa e o escopo fazem "
                      "sentido para o seu momento.")

    for incerteza in getattr(post, "incertezas", []) or []:
        avisos.append(f"O post não diz: {incerteza}.")
    return avisos
