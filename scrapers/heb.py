"""
HEB MX — Dificultad: MEDIA.
Usa Playwright porque parte del contenido se carga con JavaScript.
URL de búsqueda: https://www.heb.com.mx/search?q={query}
"""
from __future__ import annotations

import re
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from playwright.async_api import async_playwright, Page, TimeoutError as PWTimeout
from .base import BaseRetailerScraper, PriceRecord

BASE_URL = "https://www.heb.com.mx"


class HEBScraper(BaseRetailerScraper):
    RETAILER_ID = "heb"

    PRICE_SELECTORS = [
        # HEB usa su propia plataforma
        "span.price-characteristic",
        "span[class*='price-characteristic']",
        "[data-automation*='price']",
        ".price .price-characteristic",
        ".prod-price-primary .price-characteristic",
        # Fallback: buscar cualquier span con patrón de precio
        "span.visuallyhidden + span",
    ]

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
                timezone_id="America/Monterrey",
                extra_http_headers={
                    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
                    "sec-ch-ua-platform": '"Windows"',
                    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
                    "sec-ch-ua-mobile": "?0",
                }
            )

            # Ocultar que es automatizado (HEB usa Akamai Bot Manager)
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['es-MX', 'es', 'en']});
                Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
                Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
                window.chrome = { runtime: {} };
            """)

            page = await context.new_page()
            # Bloquear recursos innecesarios para acelerar
            await page.route("**/*.{png,jpg,jpeg,gif,svg,webp,woff,woff2}", lambda r: r.abort())

            result = None
            for query in search_queries:
                try:
                    result = await self._search_page(page, query, sku_name, volume_ml)
                    if result:
                        break
                except Exception as e:
                    logger.warning(f"[heb] Error '{query}': {e}")
                await self.random_delay(3.0, 6.0)

            await browser.close()

        if not result:
            return PriceRecord(
                retailer=self.RETAILER_ID, brand=brand, sku_name=sku_name,
                volume_ml=volume_ml, price_mxn=None, in_stock=False,
                url=f"{BASE_URL}/search?q={search_queries[0].replace(' ', '%20')}"
            )
        price, in_stock, url = result
        logger.info(f"[heb] {sku_name}: ${price} {'✓' if in_stock else '✗'}")
        return PriceRecord(
            retailer=self.RETAILER_ID, brand=brand, sku_name=sku_name,
            volume_ml=volume_ml, price_mxn=price, in_stock=in_stock, url=url
        )

    async def _search_page(self, page: Page, query: str, sku_name: str,
                           volume_ml: int) -> tuple | None:
        url = f"{BASE_URL}/search?q={query.replace(' ', '%20')}"
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2500)  # Esperar renderizado JS
        except PWTimeout:
            logger.warning(f"[heb] Timeout cargando {url}")
            return None

        # Verificar bloqueo
        page_text = (await page.inner_text("body")).lower()
        if any(kw in page_text for kw in ["captcha", "robot", "acceso denegado"]):
            logger.warning("[heb] Posible bloqueo detectado.")
            return None

        # Buscar productos en la página
        product_cards = await page.query_selector_all(
            "div[class*='search-result-gridview-item'], "
            "li[class*='product'], "
            "div[class*='product-item'], "
            "article[class*='product']"
        )

        sku_words = [w.lower() for w in sku_name.split() if len(w) > 2]
        best_card = None
        best_score = 0

        for card in product_cards[:8]:
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

        # Extraer precio
        price_text = None
        for sel in self.PRICE_SELECTORS:
            price_el = await best_card.query_selector(sel)
            if price_el:
                price_text = await price_el.inner_text()
                break

        if not price_text:
            card_text_raw = await best_card.inner_text()
            m = re.search(r'\$\s*(\d{1,3}(?:\.\d{2})?)', card_text_raw)
            price_text = m.group(0) if m else None

        price = self.parse_price(price_text) if price_text else None

        # Detectar sin stock
        card_text_full = (await best_card.inner_text()).lower()
        in_stock = not any(s in card_text_full for s in [
            "sin stock", "agotado", "no disponible", "out of stock"
        ])

        # URL del producto
        link_el = await best_card.query_selector("a[href]")
        prod_url = BASE_URL + await link_el.get_attribute("href") if link_el else url

        return price, in_stock, prod_url

    async def close(self):
        pass
