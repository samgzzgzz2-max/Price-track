"""
Chedraui MX — Dificultad: BAJA.
Usa la plataforma VTEX. HTML renderizado en el servidor, accesible con httpx.
URL de búsqueda: https://www.chedraui.com.mx/{query}?map=ft
"""
from __future__ import annotations
import httpx
from bs4 import BeautifulSoup
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from .base import BaseRetailerScraper, PriceRecord

BASE_URL = "https://www.chedraui.com.mx"


class ChedrauiScraper(BaseRetailerScraper):
    RETAILER_ID = "chedraui"

    # ── Selectores CSS / JSON (VTEX) ────────────────────────────────────────
    # Chedraui usa VTEX Store Framework. Los selectores se basan en clases VTEX.
    # Si cambian, busca en el HTML: el precio siempre está cerca de "sellingPrice" o "spotPrice".
    PRICE_SELECTORS = [
        # VTEX Store Framework (más común)
        "span.vtex-product-price-1-x-sellingPriceValue",
        "span.vtex-product-price-1-x-spotPrice",
        # Fallback: precio en span con clase que contiene "price"
        "[class*='sellingPrice'] span",
        "[class*='spotPrice'] span",
        # Fallback genérico
        "span.price",
        ".product-price .selling-price",
    ]

    STOCK_SELECTORS = [
        # VTEX: si hay botón "Agregar al carrito" → en stock
        "button[class*='add-to-cart-button']",
        "button[class*='buy-button']",
        ".vtex-store-components-3-x-buyButton",
    ]

    OUT_OF_STOCK_SIGNALS = [
        "sin stock", "agotado", "no disponible", "out of stock"
    ]

    def __init__(self):
        super().__init__()
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": self.random_ua(),
                "Accept-Language": "es-MX,es;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            timeout=30,
            follow_redirects=True
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=3, max=15))
    async def _fetch_search(self, query: str) -> BeautifulSoup:
        encoded = query.replace(" ", "%20")
        url = f"{BASE_URL}/{encoded}?map=ft"
        resp = await self.client.get(url)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml"), url

    def _extract_products(self, soup: BeautifulSoup) -> list[dict]:
        """Extrae lista de productos de la página de resultados."""
        products = []

        # VTEX: cada producto es un article o div con data-product-id
        items = (
            soup.find_all("article", class_=lambda c: c and "productSummary" in c) or
            soup.find_all("div", class_=lambda c: c and "productSummary" in c) or
            soup.find_all("article") or
            soup.find_all("li", class_=lambda c: c and "product" in str(c).lower())
        )

        for item in items[:10]:  # Primeros 10 resultados
            name_el = (
                item.find("span", class_=lambda c: c and "productBrand" in str(c)) or
                item.find("h2") or
                item.find("h3") or
                item.find(class_=lambda c: c and "name" in str(c).lower())
            )
            price_el = None
            for sel in self.PRICE_SELECTORS:
                price_el = item.select_one(sel)
                if price_el:
                    break

            link_el = item.find("a", href=True)

            if name_el and price_el:
                products.append({
                    "name": name_el.get_text(strip=True),
                    "price_text": price_el.get_text(strip=True),
                    "url": BASE_URL + link_el["href"] if link_el and link_el["href"].startswith("/") else (link_el["href"] if link_el else ""),
                    "html": str(item)
                })

        return products

    def _is_in_stock(self, item_html: str) -> bool:
        item_soup = BeautifulSoup(item_html, "lxml")
        # Señales de sin stock en el texto
        text = item_soup.get_text().lower()
        for signal in self.OUT_OF_STOCK_SIGNALS:
            if signal in text:
                return False
        # Si tiene botón de compra → en stock
        for sel in self.STOCK_SELECTORS:
            if item_soup.select_one(sel):
                return True
        return True  # Asumir en stock si no hay señal contraria

    def _best_match(self, products: list[dict], sku_name: str, volume_ml: int) -> dict | None:
        sku_words = [w.lower() for w in sku_name.split() if len(w) > 2]
        best = None
        best_score = 0

        for p in products:
            name = p["name"].lower()
            score = sum(1 for w in sku_words if w in name)
            if score > best_score:
                best_score = score
                best = p

        return best if best_score >= 2 else None

    async def scrape_sku(self, brand: str, sku_name: str, volume_ml: int,
                         search_queries: list[str]) -> PriceRecord:
        best_product = None

        for query in search_queries:
            try:
                soup, search_url = await self._fetch_search(query)
                products = self._extract_products(soup)
                match = self._best_match(products, sku_name, volume_ml)
                if match:
                    best_product = match
                    best_product["search_url"] = search_url
                    break
            except Exception as e:
                logger.warning(f"[chedraui] Error en '{query}': {e}")
            await self.random_delay(2.0, 4.0)

        if not best_product:
            logger.warning(f"[chedraui] No encontrado: {sku_name}")
            return PriceRecord(
                retailer=self.RETAILER_ID, brand=brand, sku_name=sku_name,
                volume_ml=volume_ml, price_mxn=None, in_stock=False,
                url=f"{BASE_URL}/{search_queries[0].replace(' ', '%20')}?map=ft"
            )

        price = self.parse_price(best_product["price_text"])
        in_stock = self._is_in_stock(best_product["html"])

        logger.info(f"[chedraui] {sku_name}: ${price} {'✓' if in_stock else '✗ sin stock'}")
        return PriceRecord(
            retailer=self.RETAILER_ID, brand=brand, sku_name=sku_name,
            volume_ml=volume_ml, price_mxn=price, in_stock=in_stock,
            url=best_product.get("url", best_product.get("search_url", ""))
        )

    async def close(self):
        await self.client.aclose()
