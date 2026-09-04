"""Score nunca rejeita; automação exige score alto.

As duas metades da política, decididas juntas: abaixo do corte a vaga vira
`pendente` — possibilidade acessível baixando o filtro da fila — porque o score
nunca foi validado contra desfecho real, e descartar terminalmente por ele joga
fora vaga que só ele achou ruim. E ENVIAR sozinho exige mais confiança que
aprovar: o gate `threshold_auto` manda a faixa intermediária para o baralho.
"""
import inspect

from jobapplier import orchestrator


def test_pipeline_nao_produz_rejeitada_por_score():
    """A ramificação `else → rejeitada` foi removida. Se voltar, este teste
    quebra antes de a fila voltar a perder vaga em silêncio."""
    fonte = inspect.getsource(orchestrator._executar_pipeline)
    assert '"rejeitada"' not in fonte, "score voltou a rejeitar"
    assert '"pendente"' in fonte, "abaixo do corte tem que virar pendente"


def test_gate_de_automacao_existe_e_usa_threshold_auto():
    """Plataforma automatizável com score abaixo do corte vai para o baralho,
    não para o submit. É a metade 'score alto importa' da política."""
    fonte = inspect.getsource(orchestrator._executar_candidaturas)
    assert "threshold_auto" in fonte
    assert "abaixo_do_auto" in fonte
    # O gate desvia para o MESMO caminho da plataforma sem automação (dossiê +
    # pronta_envio_manual), não para um caminho novo que possa divergir.
    assert "if abaixo_do_auto or not applicators.suportada(plataforma):" in fonte


def test_threshold_auto_tem_default_conservador():
    """85, não 65: aprovar e enviar sozinho são níveis de confiança diferentes."""
    fonte = inspect.getsource(orchestrator._executar_candidaturas)
    assert '"threshold_auto", 85' in fonte


def test_pendente_e_possibilidade_e_esta_no_baralho():
    """'Possibilidade' só é possibilidade se houver onde vê-la: o baralho inclui
    pendente (o slider padrão a esconde), mas ela NÃO conta como "esperando por
    você" — grupo próprio, fora de exigem_sua_acao()."""
    from pathlib import Path

    from jobapplier import status

    assert status.de_vaga("pendente").grupo == "possibilidade"

    fila = Path(__file__).resolve().parents[2] / "ui" / "pages" / "5_Aplicar.py"
    fonte = fila.read_text(encoding="utf-8")
    assert '"pendente")' in fonte.split("NA_FILA")[1][:220], \
        "pendente precisa estar na fila do baralho"


def test_config_de_empresas_e_uniforme():
    """Um padrão só: `coleta.empresas_<p>` e `coleta.keywords_<p>` para toda
    plataforma. Foi a divergência (gupy.search_keywords, linkedin.search_queries)
    que motivou a unificação."""
    from jobapplier.config.manager import ConfigManager

    cm = ConfigManager.__new__(ConfigManager)  # sem tocar disco
    respostas = {"coleta": {"empresas_x": ["a"], "keywords_x": ["b"]}}
    cm.get = lambda *c, default=None: (
        respostas.get(c[0], {}).get(c[1], default) if len(c) == 2 else default
    )

    assert cm.empresas("x") == ["a"]
    assert cm.empresas("X") == ["a"], "case insensitive"
    assert cm.keywords("x") == ["b"]
    assert cm.empresas("inexistente") == []
    assert cm.keywords("inexistente") == []


def test_orquestrador_nao_le_mais_as_chaves_antigas():
    """`gupy.search_keywords` e `linkedin.search_queries` eram as divergentes.
    Se alguém voltar a lê-las, a config unificada vira letra morta."""
    fonte = inspect.getsource(orchestrator._executar_coleta)
    assert 'config.get("gupy", "search_keywords")' not in fonte
    assert 'config.get("linkedin", "search_queries")' not in fonte
    assert 'config.empresas(' in fonte
    assert 'config.keywords(' in fonte
