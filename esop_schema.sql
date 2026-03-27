-- ESOP: EVE Salvage Operation Planner
-- Supabase schema — run in Supabase SQL Editor

-- ─── Operations ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS esop_operations (
    id              SERIAL PRIMARY KEY,
    op_ref          VARCHAR(50) UNIQUE,
    title           VARCHAR(300) NOT NULL,
    system_name     VARCHAR(200),
    region          VARCHAR(200),
    site_type       VARCHAR(100) DEFAULT 'anomaly',
    -- anomaly, mission_l1, mission_l2, mission_l3, mission_l4, combat_site, deadspace, wormhole, other
    site_name       VARCHAR(200),
    difficulty      VARCHAR(50) DEFAULT 'standard',
    -- rookie, standard, superior, overseer, escalation
    status          VARCHAR(30) DEFAULT 'planned',
    -- planned, in_progress, complete, abandoned
    ship_used       VARCHAR(200),
    character_name  VARCHAR(200),
    toon_id         BIGINT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    total_wreck_count   INTEGER DEFAULT 0,
    salvage_runs        INTEGER DEFAULT 1,
    estimated_isk       NUMERIC(20,2) DEFAULT 0,
    actual_isk          NUMERIC(20,2) DEFAULT 0,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_esop_ops_status     ON esop_operations(status);
CREATE INDEX IF NOT EXISTS idx_esop_ops_region     ON esop_operations(region);
CREATE INDEX IF NOT EXISTS idx_esop_ops_completed  ON esop_operations(completed_at);

-- ─── Wrecks ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS esop_wrecks (
    id              SERIAL PRIMARY KEY,
    operation_id    INTEGER NOT NULL REFERENCES esop_operations(id) ON DELETE CASCADE,
    ship_class      VARCHAR(100) NOT NULL,
    -- frigate, destroyer, cruiser, battlecruiser, battleship, capital, structure, drone
    ship_name       VARCHAR(200),
    faction         VARCHAR(100),
    quantity        INTEGER DEFAULT 1,
    salvaged_count  INTEGER DEFAULT 0,
    unsalvageable_count INTEGER DEFAULT 0,
    expected_yield_isk  NUMERIC(20,2) DEFAULT 0,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_esop_wrecks_op    ON esop_wrecks(operation_id);
CREATE INDEX IF NOT EXISTS idx_esop_wrecks_class ON esop_wrecks(ship_class);

-- ─── Salvage Items ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS esop_salvage_items (
    id              SERIAL PRIMARY KEY,
    operation_id    INTEGER NOT NULL REFERENCES esop_operations(id) ON DELETE CASCADE,
    item_name       VARCHAR(300) NOT NULL,
    item_type_id    INTEGER,
    tier            VARCHAR(20) DEFAULT 't1',
    quantity        INTEGER DEFAULT 1,
    unit_value_isk  NUMERIC(20,2) DEFAULT 0,
    total_value_isk NUMERIC(20,2) GENERATED ALWAYS AS (quantity * unit_value_isk) STORED,
    sold            BOOLEAN DEFAULT FALSE,
    sold_at         TIMESTAMPTZ,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_esop_items_op   ON esop_salvage_items(operation_id);
CREATE INDEX IF NOT EXISTS idx_esop_items_name ON esop_salvage_items(item_name);
CREATE INDEX IF NOT EXISTS idx_esop_items_sold ON esop_salvage_items(sold);

-- ─── Yield Reference Data ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS esop_yield_reference (
    id              SERIAL PRIMARY KEY,
    ship_class      VARCHAR(100) NOT NULL,
    faction         VARCHAR(100) DEFAULT 'generic',
    item_name       VARCHAR(300) NOT NULL,
    tier            VARCHAR(20) DEFAULT 't1',
    min_qty         INTEGER DEFAULT 0,
    max_qty         INTEGER DEFAULT 1,
    avg_qty         NUMERIC(8,2) DEFAULT 0.5,
    drop_prob       NUMERIC(5,4) DEFAULT 0.5,
    unit_value_isk  NUMERIC(20,2) DEFAULT 0,
    source          VARCHAR(100) DEFAULT 'manual',
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (ship_class, faction, item_name)
);

CREATE INDEX IF NOT EXISTS idx_esop_ref_class ON esop_yield_reference(ship_class);

-- ─── Seed: Common T1 salvage items by ship class ───────────────────────────────
INSERT INTO esop_yield_reference (ship_class, faction, item_name, tier, min_qty, max_qty, avg_qty, drop_prob, unit_value_isk)
VALUES
    ('frigate', 'generic', 'Metal Scraps',            't1', 1, 3, 1.5, 0.90, 80),
    ('frigate', 'generic', 'Armor Plates',             't1', 0, 2, 0.8, 0.60, 300),
    ('frigate', 'generic', 'Fried Interface Circuit',  't1', 0, 1, 0.3, 0.40, 1200),
    ('frigate', 'generic', 'Burned Logic Circuit',     't1', 0, 1, 0.3, 0.35, 700),
    ('frigate', 'generic', 'Tripped Power Circuit',    't1', 0, 1, 0.4, 0.50, 500),
    ('destroyer', 'generic', 'Metal Scraps',           't1', 2, 5, 3.0, 0.95, 80),
    ('destroyer', 'generic', 'Armor Plates',           't1', 1, 4, 2.0, 0.75, 300),
    ('destroyer', 'generic', 'Fried Interface Circuit','t1', 0, 2, 0.8, 0.55, 1200),
    ('destroyer', 'generic', 'Burned Logic Circuit',   't1', 0, 2, 0.7, 0.50, 700),
    ('destroyer', 'generic', 'Tripped Power Circuit',  't1', 1, 3, 1.5, 0.65, 500),
    ('cruiser', 'generic', 'Metal Scraps',             't1', 3, 8, 5.0, 0.95, 80),
    ('cruiser', 'generic', 'Armor Plates',             't1', 2, 6, 3.5, 0.85, 300),
    ('cruiser', 'generic', 'Contaminated Lorentz Fluid','t1', 0, 2, 0.9, 0.60, 2500),
    ('cruiser', 'generic', 'Charred Micro Circuit',    't1', 0, 2, 0.8, 0.55, 3000),
    ('cruiser', 'generic', 'Malfunctioning Hull Section','t1', 0, 1, 0.4, 0.45, 4500),
    ('cruiser', 'generic', 'Ward Console',             't1', 0, 1, 0.3, 0.40, 6000),
    ('battlecruiser', 'generic', 'Metal Scraps',        't1', 5, 15, 9.0, 0.95, 80),
    ('battlecruiser', 'generic', 'Armor Plates',        't1', 4, 10, 6.5, 0.90, 300),
    ('battlecruiser', 'generic', 'Contaminated Lorentz Fluid','t1', 1, 4, 2.2, 0.75, 2500),
    ('battlecruiser', 'generic', 'Charred Micro Circuit','t1', 1, 3, 1.8, 0.70, 3000),
    ('battlecruiser', 'generic', 'Malfunctioning Hull Section','t1', 0, 2, 0.9, 0.60, 4500),
    ('battlecruiser', 'generic', 'Smashed Trigger Unit', 't1', 0, 2, 0.8, 0.55, 8000),
    ('battlecruiser', 'generic', 'Ward Console',        't1', 0, 2, 0.7, 0.55, 6000),
    ('battleship', 'generic', 'Metal Scraps',           't1', 8, 25, 15.0, 0.95, 80),
    ('battleship', 'generic', 'Armor Plates',           't1', 6, 18, 11.0, 0.92, 300),
    ('battleship', 'generic', 'Contaminated Lorentz Fluid','t1', 2, 8, 4.5, 0.85, 2500),
    ('battleship', 'generic', 'Charred Micro Circuit',  't1', 2, 7, 4.0, 0.82, 3000),
    ('battleship', 'generic', 'Malfunctioning Hull Section','t1', 1, 4, 2.5, 0.75, 4500),
    ('battleship', 'generic', 'Smashed Trigger Unit',   't1', 1, 4, 2.2, 0.70, 8000),
    ('battleship', 'generic', 'Ward Console',           't1', 1, 3, 1.8, 0.68, 6000),
    ('battleship', 'generic', 'Alloyed Tritanium Bar',  't1', 0, 3, 1.2, 0.60, 12000),
    ('battleship', 'generic', 'Tripped Power Circuit',  't1', 2, 8, 4.5, 0.80, 500),
    ('battleship', 'generic', 'Burned Logic Circuit',   't1', 2, 7, 4.0, 0.78, 700)
ON CONFLICT (ship_class, faction, item_name) DO NOTHING;
