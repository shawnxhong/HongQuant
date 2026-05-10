"""SMTP email sender. No-ops when credentials are absent."""
from __future__ import annotations

import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .config import get_settings
from .logging import logger, setup_logging


def send_email(subject: str, body_markdown: str) -> bool:
    """Send an email. Returns True on success, False if unconfigured or on error."""
    setup_logging()
    s = get_settings()
    if not all([s.smtp_host, s.smtp_user, s.smtp_password, s.smtp_from, s.smtp_to]):
        logger.warning("SMTP not configured; skipping email: {}", subject)
        return False

    recipients = [r.strip() for r in (s.smtp_to or "").split(",") if r.strip()]
    if not recipients:
        logger.warning("SMTP_TO is empty; skipping email: {}", subject)
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = s.smtp_from
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(body_markdown, "plain", "utf-8"))
    msg.attach(MIMEText(_md_to_html(body_markdown), "html", "utf-8"))

    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(s.smtp_user, s.smtp_password)
            server.sendmail(s.smtp_from, recipients, msg.as_string())
        logger.info("Email sent: {}", subject)
        return True
    except Exception as exc:
        logger.error("Email send failed: {}", exc)
        return False


def _md_to_html(md: str) -> str:
    """Minimal markdown-to-HTML converter for the specific patterns we use."""
    lines = md.split("\n")
    html_lines: list[str] = ['<html><body style="font-family:monospace;max-width:800px">']

    in_table = False
    for line in lines:
        if line.startswith("## "):
            if in_table:
                html_lines.append("</table>")
                in_table = False
            html_lines.append(f"<h2>{_inline(line[3:])}</h2>")
        elif line.startswith("### "):
            if in_table:
                html_lines.append("</table>")
                in_table = False
            html_lines.append(f"<h3>{_inline(line[4:])}</h3>")
        elif line.startswith("# "):
            if in_table:
                html_lines.append("</table>")
                in_table = False
            html_lines.append(f"<h1>{_inline(line[2:])}</h1>")
        elif "|" in line and not line.strip().startswith("|---"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not in_table:
                html_lines.append('<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse">')
                in_table = True
                tag = "th"
            else:
                tag = "td"
            row = "".join(f"<{tag}>{_inline(c)}</{tag}>" for c in cells)
            html_lines.append(f"<tr>{row}</tr>")
        elif line.strip().startswith("|---"):
            pass  # separator row
        elif line.startswith("- ") or line.startswith("* "):
            if in_table:
                html_lines.append("</table>")
                in_table = False
            html_lines.append(f"<li>{_inline(line[2:])}</li>")
        elif line.strip() == "":
            if in_table:
                html_lines.append("</table>")
                in_table = False
            html_lines.append("<br>")
        else:
            if in_table:
                html_lines.append("</table>")
                in_table = False
            if line.strip():
                html_lines.append(f"<p>{_inline(line)}</p>")

    if in_table:
        html_lines.append("</table>")
    html_lines.append("</body></html>")
    return "\n".join(html_lines)


def _inline(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text
