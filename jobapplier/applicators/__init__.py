"""Módulo 13/14 — candidatura automatizada por plataforma.

Cada plataforma tem seu módulo; ``base`` concentra o contrato comum e o registro.
Use ``obter(plataforma)`` em vez de importar um applicator direto — assim o
orquestrador não precisa saber quais existem.
"""
from .base import (
    PLATAFORMAS,
    STATUS_VALIDOS,
    capturar_falha,
    obter,
    resultado,
    suportada,
)

__all__ = [
    "PLATAFORMAS",
    "STATUS_VALIDOS",
    "capturar_falha",
    "obter",
    "resultado",
    "suportada",
]
