"""
Sistema de notificaciones — WhatsApp vía Twilio + reporte diario.
"""
from __future__ import annotations
import os
from datetime import datetime
from loguru import logger
from twilio.rest import Client as TwilioClient
from core.alerts import Alert


class Notifier:
    def __init__(self):
        self.account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        self.auth_token  = os.environ.get("TWILIO_AUTH_TOKEN", "")
        # Número WhatsApp sandbox de Twilio: whatsapp:+14155238886
        # Reemplazar con tu número Twilio cuando tengas cuenta aprobada
        self.from_number = os.environ.get("TWILIO_FROM", "whatsapp:+14155238886")
        # Tu WhatsApp personal — se configura como secret en GitHub Actions
        self.to_number   = os.environ.get("WHATSAPP_TO", "")
        self._client = None

    @property
    def client(self) -> TwilioClient:
        if not self._client:
            self._client = TwilioClient(self.account_sid, self.auth_token)
        return self._client

    def send_whatsapp(self, message: str) -> bool:
        """Envía un mensaje de WhatsApp. Retorna True si fue exitoso."""
        if not self.account_sid or not self.to_number:
            logger.warning("[notifier] Credenciales de Twilio no configuradas. Saltando WhatsApp.")
            return False
        try:
            msg = self.client.messages.create(
                from_=self.from_number,
                to=f"whatsapp:{self.to_number}" if not self.to_number.startswith("whatsapp") else self.to_number,
                body=message[:1500]  # WhatsApp límite
            )
            logger.info(f"[notifier] WhatsApp enviado: {msg.sid}")
            return True
        except Exception as e:
            logger.error(f"[notifier] Error WhatsApp: {e}")
            return False

    # ── Mensajes ─────────────────────────────────────────────────────────────

    def notify_scrape_failure(self, retailer: str, error: str):
        """Alerta cuando un scraper falla completamente."""
        msg = (
            f"🚨 *ERROR DE SCRAPING* — {datetime.now().strftime('%d %b %Y %H:%M')}\n\n"
            f"Cadena: *{retailer.upper()}*\n"
            f"Error: {error[:200]}\n\n"
            f"Los datos de hoy para esta cadena NO se actualizaron.\n"
            f"Revisa el log en GitHub Actions."
        )
        self.send_whatsapp(msg)

    def notify_daily_alerts(self, alerts: list[Alert], dashboard_url: str = ""):
        """
        Envía las alertas de alta prioridad por WhatsApp.
        Solo envía si hay alertas de alta prioridad para no spamear.
        """
        high = [a for a in alerts if a.priority == "alta"]
        if not high:
            logger.info("[notifier] Sin alertas de alta prioridad. No se envía WhatsApp.")
            return

        lines = [
            f"🔔 *CPG Price Intelligence — {datetime.now().strftime('%d %b %Y')}*",
            f"⚡ {len(high)} alerta(s) de alta prioridad:\n",
        ]
        for a in high[:5]:  # Máx 5 para no hacer el mensaje enorme
            lines.append(a.whatsapp_text())
            lines.append("")

        if len(high) > 5:
            lines.append(f"...y {len(high)-5} alertas más.")

        if dashboard_url:
            lines.append(f"\n📊 Dashboard: {dashboard_url}")

        self.send_whatsapp("\n".join(lines))

    def notify_daily_summary(self, total_records: int, alerts: list[Alert],
                              failed_retailers: list[str], dashboard_url: str = ""):
        """Reporte diario completo — se envía siempre, incluso si no hay alertas."""
        status = "✅ Exitoso" if not failed_retailers else f"⚠️ Parcial ({', '.join(failed_retailers)} fallaron)"

        up    = sum(1 for a in alerts if a.alert_type == "price_up")
        down  = sum(1 for a in alerts if a.alert_type == "price_down")
        oos   = sum(1 for a in alerts if a.alert_type == "out_of_stock")
        gaps  = sum(1 for a in alerts if a.alert_type == "high_gap")
        back  = sum(1 for a in alerts if a.alert_type == "back_in_stock")

        msg = (
            f"📋 *Reporte Diario CPG — {datetime.now().strftime('%d %b %Y')}*\n\n"
            f"Estado: {status}\n"
            f"SKUs actualizados: {total_records}\n\n"
            f"*Cambios detectados:*\n"
            f"🔺 Subidas de precio: {up}\n"
            f"🔻 Bajas de precio: {down}\n"
            f"📦 Sin stock: {oos}\n"
            f"✅ Volvieron al stock: {back}\n"
            f"↔️ Gaps altos entre cadenas: {gaps}\n"
        )
        if failed_retailers:
            msg += f"\n⚠️ *Cadenas con error hoy:* {', '.join(failed_retailers)}"
        if dashboard_url:
            msg += f"\n\n🔗 {dashboard_url}"

        self.send_whatsapp(msg)

    def notify_critical_scrape_failure(self, failed_retailers: list[str]):
        """Si TODOS los scrapers fallan, es urgente saberlo."""
        if not failed_retailers:
            return
        msg = (
            f"🚨🚨 *FALLO CRÍTICO DE SCRAPING* — {datetime.now().strftime('%d %b %Y %H:%M')}\n\n"
            f"Las siguientes cadenas NO se actualizaron hoy:\n"
            + "\n".join(f"• {r.upper()}" for r in failed_retailers) +
            f"\n\nRevisa GitHub Actions → CPG Scraper → último run."
        )
        self.send_whatsapp(msg)
