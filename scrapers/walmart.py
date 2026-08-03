"""
Walmart MX — Dificultad: MEDIA-ALTA.
Playwright + stealth. Sin proxies puede fallar ocasionalmente,
pero funciona desde GitHub Actions la mayoría del tiempo.
URL: https://www.walmart.com.mx/search?q={query}
"""
from __future__ import annotations
import re
from loguru import logger
from playwright.async_api import async_playwright, Page, TimeoutError as PWTimeout
from .base import BaseRetailerScraper, PriceRecord

BASE_URL = "https://www.walmart.com.mx"


class WalmartScraper(BaseRetailerScraper):
    RETAILER_ID = "walmart"

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
                }
            )

            # Intentar ocultar que es automatizado
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
                Object.defineProperty(navigator, 'languages', {get: () => ['es-MX', 'es', 'en']});
            """)

            page = await context.new_page()
            await page.route("**/*.{png,jpg,jpeg,gif,svg,webp,woff,woff2,mp4}", lambda r: r.abort())

            result = None
            for query in search_queries:
                try:
                    result = await self._search(page, query, sku_name, volume_ml)
                    if result:
                        break
                except Exception as e:
                    logger.warning(f"[walmart] Error '{query}': {e}")
                await self.random_delay(4.0, 8.0)

            await browser.close()

        if not result:
            return PriceRecord(retailer=self.RETAILER_ID, brand=brand, sku_name=sku_name,
                               volume_ml=volume_ml, price_mxn=None, in_stock=False,
                               url=f"{BASE_URL}/search?q={search_queries[0].replace(' ','%20')}")

        price, in_stock, url = result
        logger.info(f"[walmart] {sku_name}: ${price} {'✓' if in_stock else '✗'}")
        return PriceRecord(retailer=self.RETAILER_ID, brand=brand, sku_name=sku_name,
                           volume_ml=volume_ml, price_mxn=price, in_stock=in_stock, url=url)

    async def _search(self, page: Page, query: str, sku_name: str,
                      volume_ml: int) -> tuple | None:
        url = f"{BASE_URL}/search?q={query.replace(' ', '%20')}"
        try:
            await page.goto(url, wait_until="networkidle", timeout=45000)
        except PWTimeout:
            # Intentar con solo domcontentloaded
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)
            except Exception:
                return None

        # Verificar si Walmart bloqueó con CAPTCHA
        page_text = await page.inner_text("body")
        if "robot" in page_text.lower() or "captcha" in page_text.lower():
            logger.warning("[walmart] CAPTCHA detectado. Saltando.")
            return None

        # Walmart MX usa data-testid en su React app
        CARD_SELECTORS = [
            "[data-testid='list-view']",  # Vista lista
            "[data-testid='allotment-shelf']",
            "div[class*='Grid-module']",
            "div[class*='search-result-gridview']",
        ]

        cards = []
        for sel in CARD_SELECTORS:
            cards = await page.query_selector_all(sel)
            if cards:
                break

        if not cards:
            # Fallback: buscar por estructura común de productos
            cards = await page.query_selector_all("div[data-item-id], [data-automation-id*='product']")

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

        # Extraer precio — Walmart usa varios patrones
        price = None
        PRICE_SELS = [
            "[itemprop='price']",
            "[class*='price-characteristic']",
            "[class*='Price'] span[aria-hidden]",
            "div[class*='price'] span",
            "span[class*='w_iUH7']",   # Clase interna Walmart (puede cambiar)
        ]
        for sel in PRICE_SELS:
            price_el = await best_card.query_selector(sel)
            if price_el:
                attr_price = await price_el.get_attribute("content")
                text_price = attr_price or await price_el.inner_text()
                price = self.parse_price(text_price)
                if price:
                    break

        # Último fallback: regex en el texto completo
        if not price:
            card_text_full = await best_card.inner_text()
            m = re.search(r'\$\s*(\d{1,3}(?:[,.]?\d{3})*(?:\.\d{2})?)', card_text_full)
            if m:
                price = self.parse_price(m.group(0))

        card_text_lower = (await best_card.inner_text()).lower()
        in_stock = not any(s in card_text_lower for s in ["sin stock", "agotado", "no disponible"])

        link_el = await best_card.query_selector("a[href]")
        prod_url = BASE_URL + await link_el.get_attribute("href") if link_el else url

        return price, in_stock, prod_url

    async def close(self):
        pass
