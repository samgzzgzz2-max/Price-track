"""
Capa de base de datos — Supabase (PostgreSQL gratuito).
También guarda un respaldo local en JSON por si Supabase falla.
"""
from __future__ import annotations
import json
import os
from datetime import datetime, date
from pathlib import Path
from typing import Optional
from loguru import logger
from supabase import create_client, Client
from scrapers.base import PriceRecord


class Database:
    def __init__(self):
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_KEY"]
        self.client: Client = create_client(url, key)
        self.backup_file = Path("data/prices_backup.json")
        self.backup_file.parent.mkdir(exist_ok=True)

    # ── Guardar precios ──────────────────────────────────────────────────────

    def save_price(self, record: PriceRecord) -> bool:
        """Inserta un precio en Supabase. Retorna True si fue exitoso."""
        row = {
            "scraped_at": datetime.utcnow().isoformat(),
            "scraped_date": date.today().isoformat(),
            "retailer": record.retailer,
            "brand": record.brand,
            "sku_name": record.sku_name,
            "volume_ml": record.volume_ml,
            "price_mxn": record.price_mxn,
            "in_stock": record.in_stock,
            "price_per_liter": record.price_per_liter,
            "url": record.url,
        }
        try:
            self.client.table("price_records").upsert(row, on_conflict="scraped_date,retailer,sku_name").execute()
            logger.debug(f"[db] Guardado: {record.retailer}/{record.sku_name} ${record.price_mxn}")
            return True
        except Exception as e:
            logger.error(f"[db] Error guardando en Supabase: {e}")
            self._save_backup(row)
            return False

    def save_all(self, records: list[PriceRecord]) -> int:
        """Guarda una lista de PriceRecord. Retorna cuántos se guardaron exitosamente."""
        saved = sum(1 for r in records if self.save_price(r))
        logger.info(f"[db] {saved}/{len(records)} registros guardados")
        return saved

    # ── Consultar precios ────────────────────────────────────────────────────

    def get_latest_prices(self) -> list[dict]:
        """Devuelve el precio más reciente de cada SKU/retailer."""
        try:
            resp = (
                self.client.table("price_records")
                .select("*")
                .order("scraped_at", desc=True)
                .limit(500)
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error(f"[db] Error consultando Supabase: {e}")
            return self._load_backup()

    def get_yesterday_prices(self) -> dict[str, dict]:
        """
        Devuelve precios de ayer como dict:
        { "walmart|Pinol Original 1L": {"price_mxn": 58.0, ...} }
        """
        try:
            yesterday = (datetime.utcnow().replace(hour=0, minute=0, second=0)
                        .__class__.today()).__class__.fromordinal(date.today().toordinal() - 1).isoformat()
            resp = (
                self.client.table("price_records")
                .select("*")
                .eq("scraped_date", yesterday)
                .execute()
            )
            result = {}
            for row in (resp.data or []):
                key = f"{row['retailer']}|{row['sku_name']}"
                result[key] = row
            return result
        except Exception as e:
            logger.error(f"[db] Error consultando ayer: {e}")
            return {}

    def get_price_history(self, days: int = 30) -> list[dict]:
        """Devuelve histórico de N días para gráficas."""
        try:
            from datetime import timedelta
            since = (datetime.utcnow() - timedelta(days=days)).date().isoformat()
            resp = (
                self.client.table("price_records")
                .select("scraped_date,retailer,brand,sku_name,price_mxn,price_per_liter,in_stock")
                .gte("scraped_date", since)
                .order("scraped_date")
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error(f"[db] Error obteniendo historial: {e}")
            return []

    def save_price_change(self, retailer: str, sku_name: str, brand: str,
                          price_old: float, price_new: float, pct_change: float):
        """Registra un cambio de precio en la tabla de alertas."""
        try:
            self.client.table("price_changes").insert({
                "changed_at": datetime.utcnow().isoformat(),
                "retailer": retailer,
                "sku_name": sku_name,
                "brand": brand,
                "price_old": price_old,
                "price_new": price_new,
                "pct_change": pct_change,
            }).execute()
        except Exception as e:
            logger.warning(f"[db] No se pudo guardar cambio de precio: {e}")

    # ── Backup local ─────────────────────────────────────────────────────────

    def _save_backup(self, row: dict):
        """Guarda en JSON local si Supabase falla."""
        try:
            existing = []
            if self.backup_file.exists():
                with open(self.backup_file) as f:
                    existing = json.load(f)
            existing.append(row)
            with open(self.backup_file, "w") as f:
                json.dump(existing, f, ensure_ascii=False, default=str)
        except Exception as e:
            logger.error(f"[db] Error en backup local: {e}")

    def _load_backup(self) -> list[dict]:
        if self.backup_file.exists():
            with open(self.backup_file) as f:
                return json.load(f)
        return []
