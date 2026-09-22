"""O Easy Apply do LinkedIn, assistido — sem login, sem enviar.

Página sintética (`fixtures/linkedin_easy_apply.html`) servida no lugar de
`linkedin.com/jobs/view/<id>/`: um diálogo com as perguntas e o campo "Upload
resume", e em volta a busca de vagas — que a extensão NÃO pode ler como
pergunta. O que se prova:

- a vaga é reconhecida pelo id da URL (o acervo guarda `/jobs/view/<id>/`);
- a extensão mostra o que sabe e espera o clique;
- no clique, preenche o que tem resposta, deixa em branco o que não tem, e
  anexa o PDF feito para a vaga no campo de arquivo — sem clicar em nada;
- "Avançar" continua onde estava.

Invariante 6: nunca faz login, nunca envia. Este teste não abre o LinkedIn.
"""
from pathlib import Path

import pytest

from tests.e2e.test_extensao_ponta_a_ponta import (  # noqa: F401
    EMPRESA,
    PERGUNTA_RADIO,
    PERGUNTA_TEXTO,
    api,
    navegador,
)

pytestmark = [pytest.mark.e2e, pytest.mark.db]

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "linkedin_easy_apply.html"
JOB_ID = "999000333"
URL_VAGA = f"https://www.linkedin.com/jobs/view/{JOB_ID}/"
URL_BUSCA = f"https://www.linkedin.com/jobs/search/?currentJobId={JOB_ID}&keywords=teste"

# PDF mínimo válido: o que importa é o nome e que chegue inteiro ao campo.
PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
       b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n")


@pytest.fixture
def acervo_linkedin():
    from jobapplier import aprendizado, paths
    from jobapplier.database.connection import get_session
    from jobapplier.database.models import RespostaAprendida, Vaga, VinculoCandidatura

    def _limpar():
        with get_session() as s:
            s.query(VinculoCandidatura).filter_by(
                referencia=JOB_ID).delete(synchronize_session=False)
            s.query(Vaga).filter_by(empresa=EMPRESA, plataforma="linkedin").delete(
                synchronize_session=False)
            s.query(RespostaAprendida).filter(
                RespostaAprendida.pergunta.ilike("%teste e2e%")
            ).delete(synchronize_session=False)
        for pdf in paths.RESUMES.glob("resume_e2e_*.pdf"):
            pdf.unlink()

    _limpar()
    with get_session() as s:
        vaga = Vaga(hash=f"e2e-li-{JOB_ID}", titulo="Vaga de teste e2e", empresa=EMPRESA,
                    plataforma="linkedin", fonte_vaga_id=JOB_ID, descricao="teste",
                    link=URL_VAGA, status="pronta_envio_manual", score=90)
        s.add(vaga)
        s.flush()
        vaga_id = vaga.id
        aprendizado.registrar(s, PERGUNTA_RADIO, "Não", empresa=EMPRESA,
                              opcoes=["Sim", "Não"])
        aprendizado.registrar(s, PERGUNTA_TEXTO, "Azul e2e", empresa=EMPRESA)
    paths.RESUMES.mkdir(parents=True, exist_ok=True)
    (paths.RESUMES / f"resume_e2e_{vaga_id}.pdf").write_bytes(PDF)
    yield vaga_id
    _limpar()


def _rotear(route, request):
    if request.url.startswith("https://www.linkedin.com/jobs/"):
        route.fulfill(status=200, content_type="text/html; charset=utf-8",
                      body=FIXTURE.read_text(encoding="utf-8"))
    else:
        route.abort()


@pytest.mark.parametrize("url", [URL_VAGA, URL_BUSCA], ids=["pagina_da_vaga", "busca_currentJobId"])
def test_easy_apply_preenche_e_anexa_o_curriculo_no_clique(api, acervo_linkedin, navegador, url):  # noqa: F811
    page = navegador.pages[0] if navegador.pages else navegador.new_page()
    page.route("https://www.linkedin.com/**", _rotear)
    page.goto(url, wait_until="load")

    # 1ª etapa: mostra e espera. A busca de vagas NÃO conta como pergunta.
    page.wait_for_selector("#aija-preencher", timeout=15000)
    previa = page.text_content("#aija-aviso") or ""
    assert "2 perguntas neste passo" in previa, previa
    assert "2 o sistema sabe responder" in previa
    assert "Anexa o currículo desta vaga" in previa
    assert f"resume_e2e_{acervo_linkedin}.pdf" in previa
    assert page.input_value("#e2e_cor") == "", "escreveu antes do clique"
    assert page.evaluate("document.querySelector('input[type=file]').files.length") == 0

    # 2ª etapa: o clique é do candidato.
    page.click("#aija-preencher")
    page.wait_for_function(
        "document.querySelector('input[type=file]').files.length === 1", timeout=15000)

    assert page.input_value("#e2e_cor") == "Azul e2e"
    assert page.is_checked("#e2e_nao") and not page.is_checked("#e2e_sim")
    assert page.input_value("#jobs-search-box") == "", "leu a busca como pergunta"
    anexado = page.evaluate("""() => { const f = document.querySelector('input[type=file]').files[0];
        return {nome: f.name, tipo: f.type, tamanho: f.size}; }""")
    assert anexado["nome"] == f"resume_e2e_{acervo_linkedin}.pdf"
    assert anexado["tipo"] == "application/pdf"
    assert anexado["tamanho"] == len(PDF)

    aviso = page.text_content("#aija-aviso") or ""
    assert "2 campos preenchidos" in aviso
    assert "Currículo anexado" in aviso

    # Nada avançou: o diálogo e o botão seguem como estavam.
    assert page.is_visible("div[role=dialog]")
    assert page.is_visible("button[aria-label='Continue to next step']")
