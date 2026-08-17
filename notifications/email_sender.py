"""Módulo de notificações por e-mail — relatório diário de candidaturas."""
import logging
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def send_daily_report(email_config: dict) -> tuple[bool, str]:
    """
    Gera e envia o relatório diário de candidaturas.
    Retorna (ok, mensagem).
    """
    try:
        stats = _collect_stats()
        html = _build_html(stats)
        return _send(email_config, html, stats)
    except Exception as exc:
        logger.error("Erro ao enviar relatório: %s", exc)
        return False, str(exc)


def _collect_stats() -> dict:
    """Coleta estatísticas do banco para as últimas 24 horas."""
    from sqlalchemy import func

    from database.connection import get_session
    from database.models import Candidatura, Vaga

    since = datetime.utcnow() - timedelta(hours=24)

    with get_session() as session:
        total_candidaturas = session.query(func.count(Candidatura.id)).scalar() or 0
        enviadas_hoje = (
            session.query(func.count(Candidatura.id))
            .filter(Candidatura.status == "enviada", Candidatura.criado_em >= since)
            .scalar() or 0
        )
        pendentes = (
            session.query(func.count(Candidatura.id))
            .filter(Candidatura.status == "perguntas_pendentes")
            .scalar() or 0
        )
        erros_hoje = (
            session.query(func.count(Candidatura.id))
            .filter(Candidatura.status == "erro", Candidatura.criado_em >= since)
            .scalar() or 0
        )
        vagas_aprovadas = (
            session.query(func.count(Vaga.id))
            .filter(Vaga.status == "aprovada")
            .scalar() or 0
        )
        ats_avg = (
            session.query(func.avg(Candidatura.ats_score_otimizado))
            .filter(Candidatura.ats_score_otimizado.isnot(None))
            .scalar()
        )

        # Últimas 5 candidaturas enviadas
        recent = (
            session.query(Candidatura, Vaga)
            .join(Vaga, Candidatura.vaga_id == Vaga.id, isouter=True)
            .filter(Candidatura.status == "enviada")
            .order_by(Candidatura.criado_em.desc())
            .limit(5)
            .all()
        )
        recent_list = [
            {
                "titulo": vaga.titulo if vaga else f"Vaga #{cand.vaga_id}",
                "empresa": vaga.empresa if vaga else "?",
                "plataforma": vaga.plataforma if vaga else "?",
                "ats": f"{cand.ats_score_otimizado:.0f}%" if cand.ats_score_otimizado else "—",
                "data": cand.criado_em.strftime("%d/%m %H:%M") if cand.criado_em else "?",
            }
            for cand, vaga in recent
        ]

    return {
        "total_candidaturas": total_candidaturas,
        "enviadas_hoje": enviadas_hoje,
        "pendentes": pendentes,
        "erros_hoje": erros_hoje,
        "vagas_aprovadas": vagas_aprovadas,
        "ats_avg": f"{ats_avg:.1f}%" if ats_avg else "—",
        "recent": recent_list,
        "data": datetime.now().strftime("%d/%m/%Y"),
    }


def _build_html(stats: dict) -> str:
    rows = ""
    for r in stats["recent"]:
        rows += (
            f"<tr><td>{r['titulo']}</td><td>{r['empresa']}</td>"
            f"<td>{r['plataforma']}</td><td>{r['ats']}</td><td>{r['data']}</td></tr>"
        )

    return f"""
<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#333">
<h2 style="color:#1a73e8">AI Job Applier — Relatório {stats['data']}</h2>

<table style="width:100%;border-collapse:collapse;margin-bottom:20px">
  <tr>
    <td style="background:#e8f0fe;padding:12px;border-radius:8px;text-align:center">
      <div style="font-size:28px;font-weight:bold;color:#1a73e8">{stats['enviadas_hoje']}</div>
      <div style="font-size:12px;color:#666">Enviadas hoje</div>
    </td>
    <td style="background:#e6f4ea;padding:12px;border-radius:8px;text-align:center">
      <div style="font-size:28px;font-weight:bold;color:#34a853">{stats['total_candidaturas']}</div>
      <div style="font-size:12px;color:#666">Total histórico</div>
    </td>
    <td style="background:#fef7e0;padding:12px;border-radius:8px;text-align:center">
      <div style="font-size:28px;font-weight:bold;color:#f9ab00">{stats['vagas_aprovadas']}</div>
      <div style="font-size:12px;color:#666">Aguardando candidatura</div>
    </td>
    <td style="background:#fce8e6;padding:12px;border-radius:8px;text-align:center">
      <div style="font-size:28px;font-weight:bold;color:#ea4335">{stats['erros_hoje']}</div>
      <div style="font-size:12px;color:#666">Erros hoje</div>
    </td>
  </tr>
</table>

<p><strong>ATS Score médio:</strong> {stats['ats_avg']}</p>
<p><strong>Perguntas pendentes (manual):</strong> {stats['pendentes']}</p>

{"<h3>Últimas candidaturas enviadas</h3><table style='width:100%;border-collapse:collapse'><tr style='background:#f1f3f4'><th style='padding:8px;text-align:left'>Cargo</th><th>Empresa</th><th>Plataforma</th><th>ATS</th><th>Horário</th></tr>" + rows + "</table>" if rows else "<p>Nenhuma candidatura enviada recentemente.</p>"}

<hr style="margin-top:30px">
<p style="font-size:11px;color:#999">AI Job Applier — Relatório automático gerado em {stats['data']}</p>
</body></html>
"""


def _send(email_config: dict, html: str, stats: dict) -> tuple[bool, str]:
    subject = (
        f"AI Job Applier — {stats['enviadas_hoje']} candidatura(s) hoje "
        f"| {stats['vagas_aprovadas']} pendentes — {stats['data']}"
    )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = email_config["smtp_user"]
    msg["To"] = email_config.get("email_destino") or email_config["smtp_user"]
    msg.set_content("Relatório de candidaturas (versão HTML disponível).")
    msg.add_alternative(html, subtype="html")

    try:
        with smtplib.SMTP(email_config["smtp_host"], email_config["smtp_port"], timeout=15) as server:
            server.starttls()
            server.login(email_config["smtp_user"], email_config["smtp_pass"])
            server.send_message(msg)
        logger.info("Relatório enviado para %s", msg["To"])
        return True, "Relatório enviado com sucesso."
    except Exception as exc:
        logger.error("Falha SMTP: %s", exc)
        return False, str(exc)
