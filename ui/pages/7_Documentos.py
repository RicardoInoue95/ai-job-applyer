"""Currículos e cartas: a página. O conteúdo mora em `_documentos.render`,
porque a mesma biblioteca aparece como seção de Configurações."""
import _bootstrap  # noqa: F401  # antes de qualquer import de jobapplier
import _documentos

_documentos.render()
