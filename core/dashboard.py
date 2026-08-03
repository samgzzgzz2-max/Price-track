"""
Generador del dashboard HTML — toma los datos reales de la DB
y produce el archivo HTML que se publica en GitHub Pages.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from loguru import logger
from scrapers.base import PriceRecord
from core.alerts import Alert

RETAILERS_ORDER = ["walmart", "heb", "chedraui", "soriana", "meli"]
RETAILER_LABELS = {
    "walmart": "Walmart", "heb": "HEB", "chedraui": "Chedraui",
    "soriana": "Soriana", "meli": "M.Libre"
}
BRAND_COLORS = {
    "pinol": "#e07b39", "ensueno": "#8a4fcf",
    "cloralex": "#2d9cdb", "citrex": "#27ae60"
}


class DashboardGenerator:
    def __init__(self, records: list[PriceRecord], alerts: list[Alert],
                 history: list[dict], failed_retailers: list[str]):
        self.records = records
        self.alerts = alerts
        self.history = history
        self.failed_retailers = failed_retailers
        self.template_path = Path("core/dashboard_template.html")
        self.output_path = Path("docs/index.html")  # GitHub Pages sirve desde /docs

    def _build_price_matrix(self) -> dict:
        """
        Construye matriz: { brand: { sku_name: { retailer: {price, in_stock, ppl} } } }
        """
        matrix = {}
        for r in self.records:
            brand = matrix.setdefault(r.brand, {})
            sku = brand.setdefault(r.sku_name, {"volume_ml": r.volume_ml})
            sku[r.retailer] = {
                "price": r.price_mxn,
                "in_stock": r.in_stock,
                "ppl": r.price_per_liter,  # price per liter
                "url": r.url,
            }
        return matrix

    def _build_kpis(self) -> dict:
        """Calcula los KPI del header."""
        active_alerts = len(self.alerts)
        oos_count = sum(1 for r in self.records if not r.in_stock)
        price_changes = sum(1 for a in self.alerts if a.alert_type in ("price_up", "price_down"))

        # Gap máximo entre cadenas
        max_gap = 0
        max_gap_desc = ""
        sku_groups: dict[str, list[PriceRecord]] = {}
        for r in self.records:
            if r.in_stock and r.price_mxn:
                sku_groups.setdefault(r.sku_name, []).append(r)

        for sku_name, sku_records in sku_groups.items():
            prices = [r.price_mxn for r in sku_records]
            if len(prices) >= 2:
                mn, mx = min(prices), max(prices)
                gap = (mx - mn) / mn * 100
                if gap > max_gap:
                    max_gap = gap
                    min_r = next(r for r in sku_records if r.price_mxn == mn)
                    max_r = next(r for r in sku_records if r.price_mxn == mx)
                    max_gap_desc = f"{sku_name}: {min_r.retailer} vs {max_r.retailer}"

        # Mejor precio/litro
        best_ppl = None
        best_ppl_desc = ""
        for r in self.records:
            if r.in_stock and r.price_per_liter:
                if best_ppl is None or r.price_per_liter < best_ppl:
                    best_ppl = r.price_per_liter
                    best_ppl_desc = f"{r.sku_name} · {RETAILER_LABELS.get(r.retailer, r.retailer)}"

        return {
            "active_alerts": active_alerts,
            "oos_count": oos_count,
            "price_changes": price_changes,
            "max_gap": round(max_gap),
            "max_gap_desc": max_gap_desc,
            "best_ppl": best_ppl,
            "best_ppl_desc": best_ppl_desc,
            "skus_monitored": len(set(r.sku_name for r in self.records)),
        }

    def generate(self) -> str:
        """Genera el HTML completo con datos reales y lo guarda."""
        logger.info("[dashboard] Generando HTML...")

        price_matrix = self._build_price_matrix()
        kpis = self._build_kpis()

        # Serializar datos para el JS del dashboard
        js_data = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "price_matrix": price_matrix,
            "kpis": kpis,
            "alerts": [
                {
                    "type": a.alert_type,
                    "retailer": a.retailer,
                    "brand": a.brand,
                    "sku_name": a.sku_name,
                    "message": a.message,
                    "priority": a.priority,
                    "pct_change": a.pct_change,
                }
                for a in self.alerts
            ],
            "history": self.history[-500:],  # últimos 500 registros
            "failed_retailers": self.failed_retailers,
            "retailers": RETAILERS_ORDER,
            "retailer_labels": RETAILER_LABELS,
            "brand_colors": BRAND_COLORS,
        }

        # Leer template e inyectar datos
        with open(self.template_path) as f:
            template = f.read()

        html = template.replace(
            "/* INJECT_DATA */",
            f"const DATA = {json.dumps(js_data, ensure_ascii=False, default=str)};"
        )

        # Guardar
        self.output_path.parent.mkdir(exist_ok=True)
        with open(self.output_path, "w", encoding="utf-8") as f:
            f.write(html)

        logger.info(f"[dashboard] HTML guardado en {self.output_path}")
        return str(self.output_path)
