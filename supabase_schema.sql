-- ================================================================
-- CPG Price Intelligence — Supabase Schema
-- Ejecutar esto en Supabase → SQL Editor → New Query → Run
-- ================================================================

-- Tabla principal de precios diarios
CREATE TABLE IF NOT EXISTS price_records (
    id              BIGSERIAL PRIMARY KEY,
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    scraped_date    DATE NOT NULL DEFAULT CURRENT_DATE,
    retailer        VARCHAR(50) NOT NULL,
    brand           VARCHAR(100) NOT NULL,
    sku_name        VARCHAR(200) NOT NULL,
    volume_ml       INTEGER,
    price_mxn       DECIMAL(10,2),
    in_stock        BOOLEAN NOT NULL DEFAULT TRUE,
    price_per_liter DECIMAL(10,4),
    url             TEXT,
    UNIQUE (scraped_date, retailer, sku_name)
);

-- Tabla de cambios de precio (historial de alertas)
CREATE TABLE IF NOT EXISTS price_changes (
    id          BIGSERIAL PRIMARY KEY,
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    retailer    VARCHAR(50) NOT NULL,
    sku_name    VARCHAR(200) NOT NULL,
    brand       VARCHAR(100),
    price_old   DECIMAL(10,2),
    price_new   DECIMAL(10,2),
    pct_change  DECIMAL(6,2),
    alert_sent  BOOLEAN DEFAULT FALSE
);

-- Vista: último precio conocido por SKU y retailer
CREATE OR REPLACE VIEW latest_prices AS
SELECT DISTINCT ON (retailer, sku_name)
    id, scraped_at, scraped_date, retailer, brand, sku_name,
    volume_ml, price_mxn, in_stock, price_per_liter, url
FROM price_records
ORDER BY retailer, sku_name, scraped_at DESC;

-- Vista: precios de hoy
CREATE OR REPLACE VIEW today_prices AS
SELECT * FROM price_records
WHERE scraped_date = CURRENT_DATE;

-- Vista: resumen diario por marca y cadena
CREATE OR REPLACE VIEW daily_summary AS
SELECT
    scraped_date,
    retailer,
    brand,
    COUNT(*)                    AS sku_count,
    COUNT(*) FILTER (WHERE in_stock)           AS in_stock_count,
    AVG(price_per_liter)        AS avg_ppl,
    MIN(price_per_liter)        AS min_ppl,
    MAX(price_per_liter)        AS max_ppl
FROM price_records
GROUP BY scraped_date, retailer, brand
ORDER BY scraped_date DESC, retailer, brand;

-- Índices para consultas frecuentes
CREATE INDEX IF NOT EXISTS idx_prices_date      ON price_records (scraped_date);
CREATE INDEX IF NOT EXISTS idx_prices_retailer  ON price_records (retailer);
CREATE INDEX IF NOT EXISTS idx_prices_brand     ON price_records (brand);
CREATE INDEX IF NOT EXISTS idx_prices_sku       ON price_records (sku_name);
CREATE INDEX IF NOT EXISTS idx_changes_date     ON price_changes (changed_at);

-- Row Level Security: solo acceso con la clave de servicio (anon no puede leer)
ALTER TABLE price_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE price_changes  ENABLE ROW LEVEL SECURITY;

-- Política: solo la Service Role puede insertar y leer
CREATE POLICY "Service role only" ON price_records
    FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role only" ON price_changes
    FOR ALL USING (auth.role() = 'service_role');

-- ================================================================
-- Datos de prueba opcionales (para verificar que todo funciona)
-- ================================================================
/*
INSERT INTO price_records (scraped_date, retailer, brand, sku_name, volume_ml, price_mxn, in_stock, price_per_liter)
VALUES
    (CURRENT_DATE, 'walmart',  'pinol',   'Pinol Original 1L',  1000, 58.0, true, 58.0),
    (CURRENT_DATE, 'heb',      'pinol',   'Pinol Original 1L',  1000, 60.0, true, 60.0),
    (CURRENT_DATE, 'chedraui', 'cloralex','Cloralex 2L',        2000, 42.0, true, 21.0),
    (CURRENT_DATE, 'meli',     'cloralex','Cloralex 2L',        2000, 55.0, true, 27.5);
*/
