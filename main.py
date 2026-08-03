"""
CPG Price Intelligence — Scraper Principal
Corre diariamente vía GitHub Actions a las 2 AM hora México.
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from loguru import logger

from scrapers import MercadoLibreScraper, ChedrauiScraper, SorianaScraper, HEBScraper, WalmartScraper
from scrapers.base import PriceRecord
from core.database import Database
from core.alerts import AlertEngine
from core.notifier import Notifier
from core.dashboard import DashboardGenerator

# ── Configuración de logging ───────────────────────────────────────────────
logger.remove()
logger.add(sys.stdout, format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}")
logger.add("logs/scraper_{time:YYYY-MM-DD}.log", rotation="1 day", retention="30 days")

# ── Cargar catálogo de productos ───────────────────────────────────────────
with open("products.json") as f:
    CATALOG = json.load(f)

# ── URL del dashboard publicado (GitHub Pages) ──────────────────────────
REPO_NAME = os.environ.get("GITHUB_REPOSITORY", "usuario/cpg-scraper")
DASHBOARD_URL = f"https://{REPO_NAME.split('/')[0]}.github.io/{REPO_NAME.split('/')[1]}/"


# ── Scrapers activos ───────────────────────────────────────────────────────
def get_scrapers() -> dict:
    scrapers = {
        "meli":     MercadoLibreScraper(access_token=os.environ.get("MELI_ACCESS_TOKEN")),
        "chedraui": ChedrauiScraper(),
        "soriana":  SorianaScraper(),
        "heb":      HEBScraper(),
        "walmart":  WalmartScraper(),
    }
    return scrapers


# ── Scraping de todos los SKUs para un retailer ────────────────────────────
async def scrape_retailer(scraper_id: str, scraper, catalog: dict) -> tuple[list[PriceRecord], str | None]:
    """Devuelve (records, error_message). error_message es None si todo fue bien."""
    records = []
    logger.info(f"━━━ Iniciando {scraper_id.upper()} ━━━")
    try:
        for brand_id, brand_data in catalog["brands"].items():
            for sku in brand_data["skus"]:
                try:
                    record = await scraper.scrape_sku(
                        brand=brand_id,
                        sku_name=sku["name"],
                        volume_ml=sku["volume_ml"],
                        search_queries=sku["search_queries"],
                    )
                    if record.is_valid():
                        records.append(record)
                        status = "✓" if record.in_stock else "✗ sin stock"
                        price_str = f"${record.price_mxn:.0f}" if record.price_mxn else "n/d"
                        logger.info(f"  [{scraper_id}] {sku['name']}: {price_str} {status}")
                    else:
                        logger.warning(f"  [{scraper_id}] {sku['name']}: precio inválido ({record.price_mxn}), descartando")
                except Exception as e:
                    logger.error(f"  [{scraper_id}] Error en {sku['name']}: {e}")

        logger.info(f"━━━ {scraper_id.upper()} completado: {len(records)} SKUs ━━━")
        return records, None

    except Exception as e:
        error_msg = f"Fallo total en {scraper_id}: {str(e)[:200]}"
        logger.error(error_msg)
        return records, error_msg
    finally:
        try:
            await scraper.close()
        except Exception:
            pass


# ── Main ───────────────────────────────────────────────────────────────────
async def main():
    start_time = datetime.now()
    logger.info(f"🚀 CPG Scraper iniciando — {start_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")

    # Inicializar servicios
    db = Database()
    notifier = Notifier()
    scrapers = get_scrapers()

    # Scrapers que corren en paralelo (los sin Playwright)
    # Los de Playwright corren secuencialmente para no saturar el runner de GitHub Actions
    PARALLEL_SCRAPERS = {"meli", "chedraui", "soriana"}
    SEQUENTIAL_SCRAPERS = {"heb", "walmart"}

    all_records: list[PriceRecord] = []
    failed_retailers: list[str] = []

    # ── Paralelo ────────────────────────────────────────────────────────────
    parallel_tasks = {
        sid: scrape_retailer(sid, scraper, CATALOG)
        for sid, scraper in scrapers.items()
        if sid in PARALLEL_SCRAPERS
    }
    parallel_results = await asyncio.gather(*parallel_tasks.values(), return_exceptions=True)

    for sid, result in zip(parallel_tasks.keys(), parallel_results):
        if isinstance(result, Exception):
            logger.error(f"[{sid}] Excepción no capturada: {result}")
            failed_retailers.append(sid)
            notifier.notify_scrape_failure(sid, str(result))
        else:
            records, error = result
            all_records.extend(records)
            if error:
                failed_retailers.append(sid)
                notifier.notify_scrape_failure(sid, error)

    # ── Secuencial (Playwright) ─────────────────────────────────────────────
    for sid in SEQUENTIAL_SCRAPERS:
        if sid not in scrapers:
            continue
        records, error = await scrape_retailer(sid, scrapers[sid], CATALOG)
        all_records.extend(records)
        if error:
            failed_retailers.append(sid)
            notifier.notify_scrape_failure(sid, error)
        await asyncio.sleep(5)  # Pausa entre browsers

    logger.info(f"\n✅ Scraping completo: {len(all_records)} registros en {len(scrapers) - len(failed_retailers)}/{len(scrapers)} cadenas")

    # ── Guardar en base de datos ────────────────────────────────────────────
    saved = db.save_all(all_records)

    # ── Motor de alertas ────────────────────────────────────────────────────
    yesterday_prices = db.get_yesterday_prices()
    alert_engine = AlertEngine(yesterday_prices)
    alerts = alert_engine.analyze(all_records)

    # Guardar cambios en la DB
    for a in alerts:
        if a.alert_type in ("price_up", "price_down") and a.pct_change:
            db.save_price_change(
                retailer=a.retailer, sku_name=a.sku_name, brand=a.brand,
                price_old=a.price_old, price_new=a.price_new, pct_change=a.pct_change
            )

    # ── Generar dashboard HTML ─────────────────────────────────────────────
    history = db.get_price_history(days=30)
    dashboard_gen = DashboardGenerator(all_records, alerts, history, failed_retailers)
    dashboard_path = dashboard_gen.generate()

    # ── Notificaciones ──────────────────────────────────────────────────────
    # Alertas de alta prioridad (inmediatas)
    notifier.notify_daily_alerts(alerts, DASHBOARD_URL)

    # Resumen diario (siempre)
    notifier.notify_daily_summary(saved, alerts, failed_retailers, DASHBOARD_URL)

    # Si TODOS fallaron — urgente
    if len(failed_retailers) == len(scrapers):
        notifier.notify_critical_scrape_failure(failed_retailers)

    # ── Resumen en log ──────────────────────────────────────────────────────
    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info(f"\n{'='*50}")
    logger.info(f"📊 RESUMEN FINAL")
    logger.info(f"   Tiempo total: {elapsed:.0f}s")
    logger.info(f"   Registros guardados: {saved}")
    logger.info(f"   Alertas generadas: {len(alerts)}")
    logger.info(f"   Cadenas fallidas: {failed_retailers or 'ninguna'}")
    logger.info(f"   Dashboard: {dashboard_path}")
    logger.info(f"{'='*50}")

    # Código de salida: 1 si todos fallaron (para que GitHub Actions marque como error)
    if len(failed_retailers) == len(scrapers):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
