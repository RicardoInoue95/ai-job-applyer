"""Coloca a raiz do repositório no sys.path para a UI achar ``jobapplier``.

``streamlit run ui/app.py`` põe ``ui/`` no sys.path, não a raiz. Sem isto,
``import jobapplier`` falha quando o Streamlit é chamado direto (``python run.py``
já exporta PYTHONPATH, mas não se deve depender só dele).

Importe como PRIMEIRA linha de ``app.py`` e de cada arquivo em ``pages/`` —
o Streamlit pode executar uma página isoladamente num deep-link, sem passar por
``app.py`` antes.

    import _bootstrap  # noqa: F401
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
