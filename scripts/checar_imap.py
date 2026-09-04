"""Confere se o acesso ao e-mail está configurado e funcionando.

    .venv\\Scripts\\python.exe scripts\\checar_imap.py

Existe porque "configurei e não sei se funcionou" é o pior estado possível: a
sessão assistida seguiria pedindo o código à mão e a leitura de desfecho ficaria
vazia, sem nada dizendo por quê. Este script responde em cinco segundos, e
distingue os erros que pedem ações diferentes — senha errada, IMAP desativado na
conta, rede bloqueada.

**Não imprime senha nem código, nunca**, e abre a caixa somente para leitura.
"""
import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

with contextlib.suppress(Exception):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from jobapplier import verificacao

PASSOS = """
  1. Ative a verificação em duas etapas na sua conta Google.
     Sem ela o Google não oferece senha de app.
       https://myaccount.google.com/signinoptions/twosv

  2. Gere uma senha de app dedicada — 16 caracteres, sem espaços.
       https://myaccount.google.com/apppasswords

  3. Cole no .env (a senha de app, NUNCA a senha da conta):
       AIJOB_IMAP_USER=voce@gmail.com
       AIJOB_IMAP_PASS=abcdefghijklmnop
       AIJOB_IMAP_HOST=imap.gmail.com

  4. Rode este script de novo.
"""


def main() -> int:
    usuario, senha, servidor = verificacao.credenciais()

    # Tudo o que se diz sobre o segredo é calculado ANTES, para que nenhum
    # `print` deste arquivo sequer mencione a variável. A checagem que garante
    # isso (`tests/unit/test_verificacao.py`) é literal, e é simples porque o
    # código é — a tentativa anterior foi um analisador de AST cada vez mais
    # esperto perseguindo um código cada vez mais criativo.
    tamanho = len((senha or "").replace(" ", ""))
    descricao = f"preenchida, {tamanho} caracteres" if senha else "(vazia)"

    print(f"\n  usuário   {usuario or '(vazio)'}")
    print(f"  senha     {descricao}")
    print(f"  servidor  {servidor}")

    if not (usuario and senha):
        print("\n  Falta configurar." + PASSOS)
        return 1

    if tamanho != 16:
        # Erro comum e silencioso: colar a senha da conta em vez da de app.
        print(f"\n  ⚠️  senha de app do Gmail tem 16 caracteres, esta tem "
              f"{tamanho}.")
        print("     Se você colou a senha da conta, o login vai falhar.")

    print("\n  conectando...", flush=True)
    try:
        achado = verificacao.buscar_codigo()
    except verificacao.VerificacaoIndisponivel as exc:
        texto = str(exc).lower()
        print(f"\n  FALHOU: {exc}\n")
        if "authenticationfailed" in texto or "invalid credentials" in texto:
            print("  Causa provável: senha de app errada ou revogada.")
            print("  Gere outra em https://myaccount.google.com/apppasswords")
        elif "timed out" in texto or "getaddrinfo" in texto:
            print("  Causa provável: rede bloqueando a porta 993.")
        return 1
    except Exception as exc:
        print(f"\n  FALHOU: {type(exc).__name__}: {exc}")
        return 1

    print("  OK — conexão funcionou e a caixa foi lida (somente leitura).")
    if achado:
        # O código não é impresso: terminal fica em scrollback.
        print(f"  Há um código de verificação recente, de {achado.remetente}.")
    else:
        print("  Nenhum código de verificação recente — esperado fora de um envio.")

    print("\n  A partir de agora:")
    print("    scripts/finalizar.py  preenche o código sozinho; você só confere e envia")
    print("    o registro de desfecho passa a ter de onde ler\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
