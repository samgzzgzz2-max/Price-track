"""
Soriana MX — Dificultad: MEDIA-ALTA.
Playwright stealth (reemplaza httpx que era bloqueado por bot-detection).
URL de búsqueda: https://www.soriana.com/search?q={query}&start=0&sz=12
"""
from __future__ import annotations

import asyncio
import re
from loguru import logger
from playwright.async_api import async_playwright, Page, TimeoutError as PWTimeout
from .base import BaseRetailerScraper, PriceRecord

BASE_URL = "https://www.soriana.com"


class SorianaScraper(BaseRetailerScraper):
    RETAILER_ID = "soriana"

    async def scrape_sku(self, brand: str, sku_name: str, volume_ml: int,
                         search_queries: list[str]) -> PriceRecord:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--window-size=1920,1080",
                ]
            )
            context = await browser.new_context(
                user_agent=self.random_ua(),
                viewport={"width": 1920, "height": 1080},
                locale="es-MX",
                timezone_id="America/Mexico_City",
                extra_http_headers={
                    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
                    "sec-ch-ua-platform": '"Windows"',
                    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
                    "sec-ch-ua-mobile": "?0",
                }
            )

            # Ocultar automatización
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['es-MX', 'es', 'en']});
                Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
                Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
                window.chrome = { runtime: {} };
            """)

            page = await context.new_page()
            # Bloquear recursos pesados para acelerar
            await page.route("**/*.{png,jpg,jpeg,gif,svg,webp,woff,woff2,mp4}", lambda r: r.abort())

            result = None
            for query in search_queries:
                try:
                    result = await self._search(page, query, sku_name, volume_ml)
                    if result:
                        break
                except Exception as e:
                    logger.warning(f"[soriana] Error '{query}': {e}")
                await self.random_delay(3.0, 6.0)

            await browser.close()

        if not result:
            return PriceRecord(
                retailer=self.RETAILER_ID, brand=brand, sku_name=sku_name,
                volume_ml=volume_ml, price_mxn=None, in_stock=False,
                url=f"{BASE_URL}/search?q={search_queries[0].replace(' ', '%20')}&start=0&sz=12"
            )

        price, in_stock, url = result
        logger.info(f"[soriana] {sku_name}: ${price} {'✓' if in_stock else '✗'}")
        return PriceRecord(
            retailer=self.RETAILER_ID, brand=brand, sku_name=sku_name,
            volume_ml=volume_ml, price_mxn=price, in_stock=in_stock, url=url
        )

    async def _search(self, page: Page, query: str, sku_name: str,
                      volume_ml: int) -> tuple | None:
        url = f"{BASE_URL}/search?q={query.replace(' ', '%20')}&start=0&sz=12"
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=35000)
            await page.wait_for_timeout(3000)
        except PWTimeout:
            logger.warning(f"[soriana] Timeout: {url}")
            return None

        # Verificar bot-block o CAPTCHA
        page_text = (await page.inner_text("body")).lower()
        if any(kw in page_text for kw in ["captcha", "robot", "acceso denegado", "403"]):
            logger.warning("[soriana] Posible bloqueo detectado.")
            return None

        # Soriana usa Salesforce Commerce Cloud (SFCC)
        CARD_SELECTORS = [
            "div.product-tile",
            "div[class*='product-tile']",
            "div.product-grid-item",
            "li.product",
            "article.product",
        ]
        cards = []
        for sel in CARD_SELECTORS:
            cards = await page.query_selector_all(sel)
            if cards:
                break

        sku_words = [w.lower() for w in sku_name.split() if len(w) > 2]
        best_card = None
        best_score = 0

        for card in cards[:10]:
            try:
                card_text = (await card.inner_text()).lower()
                score = sum(1 for w in sku_words if w in card_text)
                if score > best_score:
                    best_score = score
                    best_card = card
            except Exception:
                continue

        if not best_card or best_score < 2:
            return None

        # Extraer precio — Soriana SFCC tiene varios patrones
        price = None
        PRICE_SELS = [
            "span.value[content]",          # SFCC: <span class="value" content="XX.00">
            "span.sales .value",
            "span.price-sales",
            ".price .value",
            ".product-price span",
            "[data-price]",
        ]
        for sel in PRICE_SELS:
            price_el = await best_card.query_selector(sel)
            if price_el:
                content_attr = await price_el.get_attribute("content")
                data_price = await price_el.get_attribute("data-price")
                text_val = content_attr or data_price or await price_el.inner_text()
                price = self.parse_price(text_val)
                if price:
                    break

        # Fallback regex en texto completo
        if not price:
            card_text_full = await best_card.inner_text()
            m = re.search(r'\$\s*(\d{1,3}(?:[,.]?\d{3})*(?:\.\d{2})?)', card_text_full)
            if m:
                price = self.parse_price(m.group(0))

        card_text_lower = (await best_card.inner_text()).lower()
        in_stock = not any(s in card_text_lower for s in [
            "sin stock", "agotado", "no disponible", "out of stock"
        ])

        link_el = await best_card.query_selector("a.thumb-link, a[href*='/p/'], a[href]")
        prod_url = url
        if link_el:
            href = await link_el.get_attribute("href")
            if href:
                prod_url = href if href.startswith("http") else BASE_URL + href

        return price, in_stock, prod_url

    async def close(self):
        pass
