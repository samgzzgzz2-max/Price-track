""" 
Chedraui MX — Plataforma VTEX.
Usa el API de busqueda interno de VTEX (JSON, sin JS requerido).
URL API: https://www.chedraui.com.mx/api/catalog_system/pub/products/search?ft={query}
"""
from __future__ import annotations
import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from .base import BaseRetailerScraper, PriceRecord

BASE_URL = "https://www.chedraui.com.mx"
SEARCH_API = f"{BASE_URL}/api/catalog_system/pub/products/search"


class ChedrauiScraper(BaseRetailerScraper):
    RETAILER_ID = "chedraui"

    OUT_OF_STOCK_SIGNALS = [
        "sin stock", "agotado", "no disponible", "out of stock"
    ]

    def __init__(self):
        super().__init__()
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "es-MX,es;q=0.9",
                "Referer": BASE_URL,
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-origin",
            },
            timeout=30,
            follow_redirects=True
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=3, max=15))
    async def _search_api(self, query: str) -> list[dict]:
        """Usa la API JSON de VTEX para buscar productos."""
        resp = await self.client.get(SEARCH_API, params={
            "ft": query,
            "_from": 0,
            "_to": 9,
        })
        resp.raise_for_status()
        return resp.json()

    def _best_match(self, products: list[dict], sku_name: str) -> dict | None:
        sku_words = [w.lower() for w in sku_name.split() if len(w) > 2]
        best, best_score = None, 0
        for p in products:
            name = p.get("productName", "") + " " + p.get("productTitle", "")
            name = name.lower()
            score = sum(1 for w in sku_words if w in name)
            if score > best_score:
                best_score, best = score, p
        return best if best_score >= 2 else None

    def _extract_price_and_stock(self, product: dict) -> tuple[float | None, bool]:
        """Extrae precio y disponibilidad del JSON de VTEX."""
        try:
            items = product.get("items", [])
            if not items:
                return None, False
            # Tomar el primer item disponible
            for item in items:
                sellers = item.get("sellers", [])
                for seller in sellers:
                    offer = seller.get("commertialOffer", {})
                    price = offer.get("Price") or offer.get("ListPrice")
                    available = offer.get("AvailableQuantity", 0) > 0
                    if price and price > 0:
                        return float(price), available
        except Exception:
            pass
        return None, False

    async def scrape_sku(self, brand: str, sku_name: str, volume_ml: int,
                         search_queries: list[str]) -> PriceRecord:
        best_product = None

        for query in search_queries:
            try:
                products = await self._search_api(query)
                match = self._best_match(products, sku_name)
                if match:
                    best_product = match
                    break
            except Exception as e:
                logger.warning(f"[chedraui] Error en '{query}': {e}")
            await self.random_delay(2.0, 4.0)

        if not best_product:
            logger.warning(f"[chedraui] No encontrado: {sku_name}")
            return PriceRecord(
                retailer=self.RETAILER_ID, brand=brand, sku_name=sku_name,
                volume_ml=volume_ml, price_mxn=None, in_stock=False,
                url=f"{BASE_URL}/{search_queries[0].replace(' ', '-')}"
            )

        price, in_stock = self._extract_price_and_stock(best_product)
        prod_url = best_product.get("link", BASE_URL)
        if prod_url and not prod_url.startswith("http"):
            prod_url = BASE_URL + prod_url

        logger.info(f"[chedraui] {sku_name}: ${price} encontrado")
        return PriceRecord(
            retailer=self.RETAILER_ID, brand=brand, sku_name=sku_name,
            volume_ml=volume_ml, price_mxn=price, in_stock=in_stock,
            url=prod_url
        )

    async def close(self):
        await self.client.aclose()
