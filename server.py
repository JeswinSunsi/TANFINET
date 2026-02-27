"""
TANFINET - Network Monitor Server

HTTP file serving AND WebSocket relay run on a single port (8080).
No second port is needed, so only one firewall rule is required.

Usage:
    python server.py

Open on ANY device on the same network:
    Simulator  -> http://<LAN-IP>:8080/sim.html
    Dashboard  -> http://<LAN-IP>:8080/sla-dashboard.html
"""

import asyncio
import json
import mimetypes
import os
import smtplib
import socket
import ssl
import time
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-dotenv"])
    from dotenv import load_dotenv
    load_dotenv()

try:
    import websockets
    from websockets.http11 import Request, Response
    from websockets.datastructures import Headers
except ImportError:
    import subprocess, sys
    print("Installing 'websockets' package...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets"])
    import websockets
    from websockets.http11 import Request, Response
    from websockets.datastructures import Headers

PORT = 8080
DIR  = Path(__file__).parent.resolve()

# ── Email / Alert Configuration ──────────────────────────────────────────────
ALERT_TO: list[str] = ["jeswinsunsi@gmail.com"]  # list of recipient addresses
EMAIL_ENABLED: bool  = False                       # toggled live by the dashboard
SMTP_HOST       = "smtp.gmail.com"
SMTP_PORT       = 465
SMTP_USER       = "admin@msouqllc.com"
SMTP_FROM       = "info@msouqllc.com"
SMTP_PASSWORD   = os.environ.get("API_KEY", "")  # set env var APIKEY before running

# SLA thresholds (mirror the dashboard defaults)
SLA = {
    "maxLoss":    1.0,    # % packet loss
    "maxRTT":     300,    # ms
    "maxJitter":  20,     # ms
    "minSuccess": 99.0,   # % delivery success
    "minBW":      10,     # Mbps
}


VIOLATION_COOLDOWN = 300   # 5 minutes

_last_alert: dict[str, float] = {}

# -- Connected clients --------------------------------------------------------
CLIENTS: set = set()

# -- Email alert helper ------------------------------------------------------
def send_violation_email(violations: list[dict]) -> None:
    """
    Send a violation alert email.

    Parameters
    ----------
    violations : list of dict
        Each dict has 'title' and 'detail' keys describing a single breach.
    """
    if not EMAIL_ENABLED:
        print("  [ALERT] Email alerts disabled by dashboard. Skipping.")
        return
    if not ALERT_TO:
        print("  [ALERT] No recipients configured. Skipping email.")
        return
    if not SMTP_PASSWORD:
        print("  [ALERT] SMTP password not set (env API_KEY). Skipping email.")
        return

    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    subject = f"TANFINET SLA Violation Alert – {ts}"

    # Build violation rows for the HTML table
    rows_html = ""
    for v in violations:
        rows_html += f"""
                <tr>
                  <td style="padding:10px 14px;border-bottom:1px solid #e5e7eb;font-weight:600;color:#b91c1c;white-space:nowrap;">
                    &#9888;&nbsp; {v['title']}
                  </td>
                  <td style="padding:10px 14px;border-bottom:1px solid #e5e7eb;color:#374151;">
                    {v['detail']}
                  </td>
                </tr>"""

    body_html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:40px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#ffffff;overflow:hidden;
                    box-shadow:0 2px 12px rgba(0,0,0,0.08);max-width:600px;">

        <!-- Header -->
        <tr>
          <td style="background:#1e293b;padding:28px 32px;">
            <img src="cid:tanfinet_logo" alt="TANFINET"
                 style="height:48px;display:block;margin-bottom:14px;">
            <p style="margin:0;font-size:11px;letter-spacing:2px;text-transform:uppercase;
                      color:#94a3b8;">Network Monitoring</p>
            <h1 style="margin:6px 0 0;font-size:22px;color:#f8fafc;font-weight:700;">
              TANFINET SLA Violation Alert
            </h1>
          </td>
        </tr>

        <!-- Alert banner -->
        <tr>
          <td style="background:#fef2f2;border-left:4px solid #dc2626;
                     padding:14px 32px;">
            <p style="margin:0;font-size:13px;color:#991b1b;">
              <strong>{len(violations)} violation{"s" if len(violations) != 1 else ""} detected</strong>
              &nbsp;·&nbsp; {ts}
            </p>
          </td>
        </tr>

        <!-- Body -->
        <tr>
          <td style="padding:28px 32px 8px;">
            <p style="margin:0 0 18px;font-size:14px;color:#374151;line-height:1.6;">
              The TANFINET compliance monitor has detected the following SLA
              breach{"es" if len(violations) != 1 else ""} in the latest
              network metrics cycle. Immediate review is recommended.
            </p>

            <!-- Violations table -->
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="border-collapse:collapse;border:1px solid #e5e7eb;
                          border-radius:8px;overflow:hidden;font-size:13px;">
              <thead>
                <tr style="background:#f9fafb;">
                  <th style="padding:10px 14px;text-align:left;color:#6b7280;
                             font-weight:600;border-bottom:1px solid #e5e7eb;
                             white-space:nowrap;">Violation</th>
                  <th style="padding:10px 14px;text-align:left;color:#6b7280;
                             font-weight:600;border-bottom:1px solid #e5e7eb;">Details</th>
                </tr>
              </thead>
              <tbody>{rows_html}
              </tbody>
            </table>
          </td>
        </tr>

        <!-- CTA -->
        <tr>
          <td style="padding:24px 32px;">
            <p style="margin:0 0 16px;font-size:13px;color:#6b7280;">
              Open the live dashboard for real-time metrics and historical trends.
            </p>
            <a href="http://localhost:8080/sla-dashboard.html"
               style="display:inline-block;background:#1e293b;color:#f8fafc;
                      text-decoration:none;font-size:13px;font-weight:600;
                      padding:10px 22px;border-radius:6px;letter-spacing:0.3px;">
              View SLA Dashboard &rarr;
            </a>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f9fafb;border-top:1px solid #e5e7eb;
                     padding:16px 32px;">
            <p style="margin:0;font-size:11px;color:#9ca3af;line-height:1.6;">
              This is an automated alert from <strong>TANFINET Network Monitor</strong>.
              Alerts are suppressed for {VIOLATION_COOLDOWN // 60}&nbsp;minutes after each
              notification to prevent flooding.
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""

    # Plain-text fallback
    plain_lines = [f"TANFINET SLA Violation Alert – {ts}", ""]
    for v in violations:
        plain_lines.append(f"  • {v['title']}: {v['detail']}")
    plain_lines += ["", "Please review the SLA dashboard for full details."]
    body_text = "\n".join(plain_lines)

    # Build MIME structure: mixed > related > (alternative > plain+html) + inline image
    msg_alt = MIMEMultipart("alternative")
    msg_alt.attach(MIMEText(body_text, "plain"))
    msg_alt.attach(MIMEText(body_html, "html"))

    msg_related = MIMEMultipart("related")
    msg_related.attach(msg_alt)

    logo_path = DIR / "logo2.png"
    if logo_path.is_file():
        with open(logo_path, "rb") as _f:
            _img = MIMEImage(_f.read(), "png")
        _img.add_header("Content-ID", "<tanfinet_logo>")
        _img.add_header("Content-Disposition", "inline", filename="logo2.png")
        msg_related.attach(_img)

    message = MIMEMultipart("mixed")
    message["From"]    = SMTP_FROM
    message["To"]      = ", ".join(ALERT_TO)
    message["Subject"] = subject
    message.attach(msg_related)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, ALERT_TO, message.as_string())
        print(f"  [ALERT] Violation email sent → {', '.join(ALERT_TO)}")
    except Exception as exc:
        print(f"  [ALERT] Failed to send email: {exc}")


# -- SLA violation checker ---------------------------------------------------
def check_violations(data: dict) -> list[dict]:
    """
    Inspect a metrics snapshot against SLA thresholds.
    Returns only the breaches whose cooldown has expired.
    """
    now = time.time()
    hits: list[dict] = []

    checks = [
        (
            "loss",
            data.get("lossRate", 0) > SLA["maxLoss"],
            "Packet Loss Breach",
            f"Loss rate {data.get('lossRate', 0):.2f}% exceeds limit of {SLA['maxLoss']}%",
        ),
        (
            "rtt",
            data.get("avgRTT", 0) > SLA["maxRTT"],
            "RTT Breach",
            f"Avg RTT {data.get('avgRTT', 0)}ms exceeds limit of {SLA['maxRTT']}ms",
        ),
        (
            "jitter",
            data.get("avgJitter", 0) > SLA["maxJitter"],
            "Jitter Breach",
            f"Avg jitter {data.get('avgJitter', 0)}ms exceeds limit of {SLA['maxJitter']}ms",
        ),
        (
            "success",
            data.get("successRate", 100) < SLA["minSuccess"],
            "Success Rate Breach",
            f"Delivery success {data.get('successRate', 100):.2f}% below minimum {SLA['minSuccess']}%",
        ),
        (
            "bw",
            data.get("bandwidth", 9999) < SLA["minBW"],
            "Bandwidth Warning",
            f"Bandwidth {data.get('bandwidth', 0)} Mbps below committed rate {SLA['minBW']} Mbps",
        ),
        (
            "downtime",
            bool(data.get("downtimeActive", False)),
            "NETWORK DOWNTIME ACTIVE",
            "All packets being dropped. SLA window impacted.",
        ),
    ]

    for key, breached, title, detail in checks:
        if breached:
            last = _last_alert.get(key, 0)
            if now - last >= VIOLATION_COOLDOWN:
                _last_alert[key] = now
                hits.append({"title": title, "detail": detail})
        else:
            # reset cooldown when metric recovers so next breach emails again
            _last_alert.pop(key, None)

    return hits


# -- WebSocket relay ---------------------------------------------------------
async def relay(websocket):
    global ALERT_TO, EMAIL_ENABLED
    CLIENTS.add(websocket)
    try:
        async for message in websocket:
            # ── Parse JSON frame ─────────────────────────────────────────
            try:
                data = json.loads(message)
            except (json.JSONDecodeError, TypeError):
                data = None

            # ── Dashboard config message (not relayed) ───────────────────
            if isinstance(data, dict) and data.get("type") == "config":
                if "emailEnabled" in data:
                    EMAIL_ENABLED = bool(data["emailEnabled"])
                    print(f"  [CONFIG] Email alerts {'enabled' if EMAIL_ENABLED else 'disabled'}")
                if "alertTo" in data:
                    recipients = [r.strip() for r in data["alertTo"] if isinstance(r, str) and r.strip()]
                    ALERT_TO = recipients
                    print(f"  [CONFIG] Alert recipients updated: {', '.join(ALERT_TO) or '(none)'}")
                continue  # config messages are never relayed

            # ── Violation detection ──────────────────────────────────────
            if isinstance(data, dict):
                violations = check_violations(data)
                if violations:
                    for v in violations:
                        print(f"  [VIOLATION] {v['title']}: {v['detail']}")
                    # Run email in a thread so it doesn't block the event loop
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(
                        None, send_violation_email, violations
                    )

            # ── Relay to all other connected clients ─────────────────────
            dead = set()
            for client in CLIENTS - {websocket}:
                try:
                    await client.send(message)
                except Exception:
                    dead.add(client)
            CLIENTS.difference_update(dead)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        CLIENTS.discard(websocket)

# -- HTTP handler (WebSocket upgrade requests pass through) ------------------
async def http_handler(connection, request: Request):
    # WebSocket upgrade requests must pass through - return None to proceed
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return None

    # Resolve file path safely
    raw = request.path.split("?")[0].lstrip("/") or "sim.html"
    try:
        target = (DIR / raw).resolve()
        target.relative_to(DIR)  # blocks path traversal
    except ValueError:
        return Response(403, "Forbidden",
                        Headers([("Content-Type", "text/plain")]),
                        b"403 Forbidden")

    if target.is_file():
        body = target.read_bytes()
        mime, _ = mimetypes.guess_type(str(target))
        return Response(
            200, "OK",
            Headers([
                ("Content-Type",   mime or "application/octet-stream"),
                ("Content-Length", str(len(body))),
            ]),
            body,
        )

    return Response(404, "Not Found",
                    Headers([("Content-Type", "text/plain")]),
                    b"404 Not Found")

# -- LAN IP helper -----------------------------------------------------------
def get_lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()

# -- Entry point -------------------------------------------------------------
async def main():
    lan = get_lan_ip()
    async with websockets.serve(
        relay, "0.0.0.0", PORT,
        process_request=http_handler,
    ):
        print()
        print("  +------------------------------------------------------+")
        print("  |          TANFINET Network Monitor Server             |")
        print("  +------------------------------------------------------+")
        print()
        print("  This device (localhost):")
        print(f"    Simulator  ->  http://localhost:{PORT}/sim.html")
        print(f"    Dashboard  ->  http://localhost:{PORT}/sla-dashboard.html")
        print()
        print("  Other devices on your network:")
        print(f"    Simulator  ->  http://{lan}:{PORT}/sim.html")
        print(f"    Dashboard  ->  http://{lan}:{PORT}/sla-dashboard.html")
        print()
        print(f"  HTTP + WebSocket on a single port ({PORT}). Only port 8080 needed.")
        print("  Press Ctrl+C to stop.")
        print()
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
