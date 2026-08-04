"""
Soriana MX — Dificultad: BAJA.
Plataforma propia. HTML accesible con httpx.
Busqueda: https://www.soriana.com/search?q={query}&start=0&sz=12
"""
from __future__ import annotations
import httpx
from bs4 import BeautifulSoup
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from .base import BaseRetailerScraper, PriceRecord

BASE_URL = "https://www.soriana.com"


class SorianaScraper(BaseRetailerScraper):
    RETAILER_ID = "soriana"

    PRICE_SELECTORS = [
        "span.price-sales",
        "span.value[content]",
        "[itemprop='price']",
        ".product-price .price",
        ".price-container .price",
        "span[class*='sales'] span.value",
    ]

    OUT_OF_STOCK_SIGNALS = ["sin stock", "agotado", "no disponible"]

    def __init__(self):
        super().__init__()
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Referer": BASE_URL,
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "upgrade-insecure-requests": "1",
            },
            timeout=30,
            follow_redirects=True
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=3, max=15))
    async def _fetch_search(self, query: str) -> tuple[BeautifulSoup, str]:
        encoded = query.replace(" ", "+")
        url = f"{BASE_URL}/search?q={encoded}&start=0&sz=12"
        resp = await self.client.get(url)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml"), url

    def _extract_products(self, soup: BeautifulSoup) -> list[dict]:
        products = []
        items = (
            soup.find_all("div", class_=lambda c: c and "product-tile" in str(c)) or
            soup.find_all("div", class_=lambda c: c and "product-item" in str(c)) or
            soup.find_all("article", class_=lambda c: c and "product" in str(c).lower())
        )
        for item in items[:10]:
            name_el = (
                item.find("div", class_=lambda c: c and "product-name" in str(c)) or
                item.find("h3") or item.find("h2") or item.find(class_="name")
            )
            price_el = None
            for sel in self.PRICE_SELECTORS:
                price_el = item.select_one(sel)
                if price_el:
                    break
            link_el = item.find("a", href=True)
            if name_el and price_el:
                price_text = price_el.get("content") or price_el.get_text(strip=True)
                products.append({
                    "name": name_el.get_text(strip=True),
                    "price_text": price_text,
                    "url": BASE_URL + link_el["href"] if link_el and link_el["href"].startswith("/") else (link_el["href"] if link_el else ""),
                    "html": str(item)
                })
        return products

    def _best_match(self, products: list[dict], sku_name: str) -> dict | None:
        sku_words = [w.lower() for w in sku_name.split() if len(w) > 2]
        best, best_score = None, 0
        for p in products:
            score = sum(1 for w in sku_words if w in p["name"].lower())
            if score > best_score:
                best_score, best = score, p
        return best if best_score >= 2 else None

    async def scrape_sku(self, brand: str, sku_name: str, volume_ml: int,
                         search_queries: list[str]) -> PriceRecord:
        best_product = None
        for query in search_queries:
            try:
                soup, url = await self._fetch_search(query)
                products = self._extract_products(soup)
                match = self._best_match(products, sku_name)
                if match:
                    best_product = match
                    break
            except Exception as e:
                logger.warning(f"[soriana] Error '{query}': {e}")
            await self.random_delay(2.0, 5.0)

        if not best_product:
            return PriceRecord(
                retailer=self.RETAILER_ID, brand=brand, sku_name=sku_name,
                volume_ml=volume_ml, price_mxn=None, in_stock=False,
                url=f"{BASE_URL}/search?q={search_queries[0].replace(' ', '+')}"
            )

        text_lower = BeautifulSoup(best_product["html"], "lxml").get_text().lower()
        in_stock = not any(s in text_lower for s in self.OUT_OF_STOCK_SIGNALS)
        price = self.parse_price(best_product["price_text"])
        logger.info(f"[soriana] {sku_name}: precio encontrado")
        return PriceRecord(
            retailer=self.RETAILER_ID, brand=brand, sku_name=sku_name,
            volume_ml=volume_ml, price_mxn=price, in_stock=in_stock,
            url=best_product.get("url", "")
        )

    async def close(self):
        await self.client.aclose()
