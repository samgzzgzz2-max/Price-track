"""
Mercado Libre — usa la API oficial (GRATIS, 25k calls/día).
No necesita Playwright ni proxies.
Documentación: https://developers.mercadolibre.com.mx/
"""
from __future__ import annotations
import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from .base import BaseRetailerScraper, PriceRecord

MELI_SITE = "MLM"  # México
MELI_API = "https://api.mercadolibre.com"


class MercadoLibreScraper(BaseRetailerScraper):
    RETAILER_ID = "meli"

    def __init__(self, access_token: str | None = None):
        super().__init__()
        self.access_token = access_token
        headers = {"User-Agent": self.random_ua()}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        self.client = httpx.AsyncClient(headers=headers, timeout=30)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    async def _search(self, query: str) -> list[dict]:
        """Llama al endpoint de búsqueda de MeLi."""
        url = f"{MELI_API}/sites/{MELI_SITE}/search"
        resp = await self.client.get(url, params={
            "q": query,
            "limit": 10,
            "condition": "new",
        })
        resp.raise_for_status()
        return resp.json().get("results", [])

    def _best_match(self, results: list[dict], sku_name: str, volume_ml: int) -> dict | None:
        """
        Devuelve el resultado más relevante.
        Filtra por: nombre contiene palabras clave del SKU, precio razonable.
        """
        sku_lower = sku_name.lower()
        volume_str = str(volume_ml)
        candidates = []

        for item in results:
            title = item.get("title", "").lower()
            price = item.get("price", 0)
            # Debe mencionar al menos 2 palabras del SKU
            words = [w for w in sku_lower.split() if len(w) > 2]
            matches = sum(1 for w in words if w in title)
            if matches >= 2 and 5 <= price <= 800:
                candidates.append((matches, item))

        if not candidates:
            return None
        # El de más coincidencias
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    async def scrape_sku(self, brand: str, sku_name: str, volume_ml: int,
                         search_queries: list[str]) -> PriceRecord:
        best_item = None
        for query in search_queries:
            try:
                results = await self._search(query)
                match = self._best_match(results, sku_name, volume_ml)
                if match:
                    best_item = match
                    break
            except Exception as e:
                logger.warning(f"[meli] Error buscando '{query}': {e}")
            await self.random_delay(1.0, 2.5)

        if not best_item:
            logger.warning(f"[meli] No encontrado: {sku_name}")
            return PriceRecord(
                retailer=self.RETAILER_ID, brand=brand, sku_name=sku_name,
                volume_ml=volume_ml, price_mxn=None, in_stock=False,
                url=f"https://listado.mercadolibre.com.mx/{search_queries[0].replace(' ', '-')}"
            )

        price = best_item.get("price")
        in_stock = best_item.get("available_quantity", 0) > 0
        permalink = best_item.get("permalink", "")

        logger.info(f"[meli] {sku_name}: ${price} {'✓' if in_stock else '✗ sin stock'}")
        return PriceRecord(
            retailer=self.RETAILER_ID, brand=brand, sku_name=sku_name,
            volume_ml=volume_ml, price_mxn=float(price) if price else None,
            in_stock=in_stock, url=permalink
        )

    async def close(self):
        await self.client.aclose()
