"""
Motor de alertas — detecta cambios de precio y condiciones alarmantes.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from loguru import logger
from scrapers.base import PriceRecord


AlertType = Literal["price_up", "price_down", "out_of_stock", "back_in_stock", "high_gap"]


@dataclass
class Alert:
    alert_type: AlertType
    retailer: str
    brand: str
    sku_name: str
    message: str
    priority: Literal["alta", "media", "baja"]
    price_old: float | None = None
    price_new: float | None = None
    pct_change: float | None = None

    def whatsapp_text(self) -> str:
        icons = {
            "price_up": "🔺", "price_down": "🔻",
            "out_of_stock": "📦", "back_in_stock": "✅", "high_gap": "↔️"
        }
        icon = icons.get(self.alert_type, "⚠️")
        return (
            f"{icon} *{self.brand} — {self.sku_name}*\n"
            f"Cadena: {self.retailer.upper()}\n"
            f"{self.message}\n"
            f"Prioridad: {self.priority.upper()}"
        )


class AlertEngine:
    # Umbrales configurables
    PRICE_CHANGE_THRESHOLD_PCT = 5.0   # Alertar si precio cambia >5%
    HIGH_GAP_THRESHOLD_PCT = 25.0      # Alertar si gap entre cadenas >25%

    def __init__(self, yesterday_prices: dict[str, dict]):
        """
        yesterday_prices: dict con clave "retailer|sku_name" → row de la base de datos.
        """
        self.yesterday = yesterday_prices
        self.alerts: list[Alert] = []

    def analyze(self, records: list[PriceRecord]) -> list[Alert]:
        """Analiza los precios de hoy vs. ayer y genera alertas."""
        self.alerts = []

        # 1. Cambios de precio y sin stock
        for r in records:
            self._check_price_change(r)
            self._check_stock(r)

        # 2. Gaps entre cadenas (por SKU)
        self._check_gaps(records)

        logger.info(f"[alerts] {len(self.alerts)} alertas generadas")
        return self.alerts

    def _check_price_change(self, record: PriceRecord):
        if not record.price_mxn or not record.in_stock:
            return

        key = f"{record.retailer}|{record.sku_name}"
        yesterday = self.yesterday.get(key)
        if not yesterday or not yesterday.get("price_mxn"):
            return

        price_old = float(yesterday["price_mxn"])
        price_new = record.price_mxn
        pct = (price_new - price_old) / price_old * 100

        if abs(pct) < self.PRICE_CHANGE_THRESHOLD_PCT:
            return

        alert_type = "price_up" if pct > 0 else "price_down"
        priority = "alta" if abs(pct) > 15 else "media"

        self.alerts.append(Alert(
            alert_type=alert_type,
            retailer=record.retailer,
            brand=record.brand,
            sku_name=record.sku_name,
            message=f"Precio {'subió' if pct > 0 else 'bajó'} {abs(pct):.1f}%: ${price_old:.0f} → ${price_new:.0f} MXN",
            priority=priority,
            price_old=price_old,
            price_new=price_new,
            pct_change=round(pct, 2)
        ))

    def _check_stock(self, record: PriceRecord):
        key = f"{record.retailer}|{record.sku_name}"
        yesterday = self.yesterday.get(key)

        if not record.in_stock:
            # Si ayer estaba en stock y hoy no → alerta
            if yesterday and yesterday.get("in_stock"):
                self.alerts.append(Alert(
                    alert_type="out_of_stock",
                    retailer=record.retailer,
                    brand=record.brand,
                    sku_name=record.sku_name,
                    message=f"Sin stock hoy. Último precio: ${yesterday.get('price_mxn', '?'):.0f} MXN.",
                    priority="alta",
                ))
        else:
            # Si ayer estaba sin stock y hoy volvió
            if yesterday and not yesterday.get("in_stock"):
                self.alerts.append(Alert(
                    alert_type="back_in_stock",
                    retailer=record.retailer,
                    brand=record.brand,
                    sku_name=record.sku_name,
                    message=f"¡Volvió a stock! Precio: ${record.price_mxn:.0f} MXN.",
                    priority="media",
                ))

    def _check_gaps(self, records: list[PriceRecord]):
        """Por cada SKU, revisa el gap de precio entre cadenas."""
        # Agrupar por SKU
        sku_prices: dict[str, list[PriceRecord]] = {}
        for r in records:
            if r.in_stock and r.price_mxn:
                sku_prices.setdefault(r.sku_name, []).append(r)

        for sku_name, sku_records in sku_prices.items():
            if len(sku_records) < 2:
                continue
            prices = [r.price_mxn for r in sku_records if r.price_mxn]
            min_p, max_p = min(prices), max(prices)
            gap_pct = (max_p - min_p) / min_p * 100

            if gap_pct >= self.HIGH_GAP_THRESHOLD_PCT:
                min_r = next(r for r in sku_records if r.price_mxn == min_p)
                max_r = next(r for r in sku_records if r.price_mxn == max_p)
                brand = sku_records[0].brand
                self.alerts.append(Alert(
                    alert_type="high_gap",
                    retailer=f"{min_r.retailer} vs {max_r.retailer}",
                    brand=brand,
                    sku_name=sku_name,
                    message=(
                        f"Gap de {gap_pct:.0f}% entre cadenas: "
                        f"{min_r.retailer.upper()} ${min_p:.0f} vs "
                        f"{max_r.retailer.upper()} ${max_p:.0f} MXN"
                    ),
                    priority="media" if gap_pct < 35 else "alta",
                ))

    @property
    def high_priority_alerts(self) -> list[Alert]:
        return [a for a in self.alerts if a.priority == "alta"]

    @property
    def summary(self) -> str:
        up = sum(1 for a in self.alerts if a.alert_type == "price_up")
        down = sum(1 for a in self.alerts if a.alert_type == "price_down")
        oos = sum(1 for a in self.alerts if a.alert_type == "out_of_stock")
        gaps = sum(1 for a in self.alerts if a.alert_type == "high_gap")
        return f"📊 Resumen: {up} subidas · {down} bajas · {oos} sin stock · {gaps} gaps altos"
