"""
Base scraper class — todas las cadenas heredan de aquí.
"""
from __future__ import annotations
import re
import random
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from loguru import logger


@dataclass
class PriceRecord:
    retailer: str
    brand: str
    sku_name: str
    volume_ml: int
    price_mxn: Optional[float]
    in_stock: bool
    url: str
    currency: str = "MXN"
    price_per_liter: Optional[float] = field(init=False)

    def __post_init__(self):
        if self.price_mxn and self.volume_ml:
            self.price_per_liter = round(self.price_mxn / self.volume_ml * 1000, 4)
        else:
            self.price_per_liter = None

    def is_valid(self) -> bool:
        """Validación básica: precio dentro de rango razonable para productos de limpieza MX."""
        if not self.in_stock:
            return True  # Sin stock es válido
        if self.price_mxn is None:
            return False
        return 5.0 <= self.price_mxn <= 800.0  # $5 a $800 MXN


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]


class BaseRetailerScraper(ABC):
    RETAILER_ID: str = ""

    def __init__(self):
        self.session = None

    @abstractmethod
    async def scrape_sku(self, brand: str, sku_name: str, volume_ml: int,
                         search_queries: list[str]) -> PriceRecord:
        """Busca un SKU específico y devuelve su precio."""
        ...

    async def random_delay(self, min_s: float = 2.0, max_s: float = 5.0):
        delay = random.uniform(min_s, max_s)
        logger.debug(f"[{self.RETAILER_ID}] Esperando {delay:.1f}s...")
        await asyncio.sleep(delay)

    @staticmethod
    def parse_price(text: str) -> Optional[float]:
        """Extrae el precio numérico de un string como '$34.50' o '34 pesos'."""
        if not text:
            return None
        # Eliminar espacios, signos de moneda, letras
        cleaned = re.sub(r'[^\d.,]', '', text.strip())
        # Normalizar separadores decimales (México usa punto o coma)
        cleaned = cleaned.replace(',', '')
        try:
            value = float(cleaned)
            return value if 5 <= value <= 9999 else None
        except ValueError:
            return None

    @staticmethod
    def random_ua() -> str:
        return random.choice(USER_AGENTS)
