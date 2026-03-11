-- =============================================================================
-- iOS Carrier Bundle Database Schema
-- =============================================================================
-- All DDL uses IF NOT EXISTS / CREATE OR REPLACE — safe to run on existing DBs.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- iOS releases
-- Each row = one iOS build (e.g. 26.4 beta 4 / 23E5234a)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ios_releases (
    id                  SERIAL PRIMARY KEY,
    version             VARCHAR(20)  NOT NULL,           -- "26.4"
    build               VARCHAR(20)  NOT NULL UNIQUE,    -- "23E5234a"
    is_beta             BOOLEAN      NOT NULL DEFAULT FALSE,
    full_version_label  VARCHAR(60),                     -- "iOS 26.4 beta 4"
    os_type             VARCHAR(40),                     -- "Development", "Release", …
    release_date        DATE,
    ingested_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- iOS devices per build (from ipsw_metadata.json → devices[])
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ios_devices (
    id              SERIAL PRIMARY KEY,
    ios_build       VARCHAR(20) NOT NULL REFERENCES ios_releases(build) ON DELETE CASCADE,
    device_name     VARCHAR(100),                        -- "iPhone 17"
    product_id      VARCHAR(50),                        -- "iPhone18,3"
    board           VARCHAR(50),                        -- "V57AP"
    build_timestamp TIMESTAMPTZ,
    cpu_info        TEXT,                                -- "CPU: A19 Pro (ARMv9.2-A), ID: t8150"
    UNIQUE (ios_build, product_id)
);

-- ---------------------------------------------------------------------------
-- New plist keys detected per carrier bundle per iOS build
-- Source: cb-change-report.json → new_tags_by_bundle[]
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS carrier_bundle_key_changes (
    id          SERIAL PRIMARY KEY,
    ios_build   VARCHAR(20)  NOT NULL REFERENCES ios_releases(build) ON DELETE CASCADE,
    bundle_name VARCHAR(200) NOT NULL,
    key_path    TEXT         NOT NULL,
    UNIQUE (ios_build, bundle_name, key_path)
);

-- ---------------------------------------------------------------------------
-- Portugal / country bundle changes per iOS release
-- Source: portugal_changes.json → bundles_changed[]
-- Covers both the "Portugal" country bundle and all _pt carrier bundles.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pt_bundle_changes (
    id           SERIAL PRIMARY KEY,
    ios_build    VARCHAR(20)  NOT NULL REFERENCES ios_releases(build) ON DELETE CASCADE,
    ios_version  VARCHAR(20),
    ios_release  VARCHAR(60),                            -- "iOS 26.4 beta 2"
    release_date DATE,
    bundle_type  VARCHAR(20) CHECK (bundle_type IN ('country', 'carrier')),
    bundle_name  VARCHAR(100) NOT NULL,                  -- "Portugal", "Vodafone", …
    bundle_id    VARCHAR(200),                           -- "com.apple.Vodafone_pt"
    version_old  VARCHAR(50),
    version_new  VARCHAR(50),
    ingested_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (ios_build, bundle_id)
);

-- ---------------------------------------------------------------------------
-- Files modified inside each PT bundle change
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pt_bundle_file_changes (
    id              SERIAL PRIMARY KEY,
    pt_change_id    INTEGER NOT NULL REFERENCES pt_bundle_changes(id) ON DELETE CASCADE,
    file_path       TEXT    NOT NULL,
    UNIQUE (pt_change_id, file_path)
);

-- ---------------------------------------------------------------------------
-- Indexes for common query patterns
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_cb_key_bundle    ON carrier_bundle_key_changes(bundle_name);
CREATE INDEX IF NOT EXISTS idx_cb_key_build     ON carrier_bundle_key_changes(ios_build);
CREATE INDEX IF NOT EXISTS idx_pt_bundle_name   ON pt_bundle_changes(bundle_name);
CREATE INDEX IF NOT EXISTS idx_pt_bundle_build  ON pt_bundle_changes(ios_build);
CREATE INDEX IF NOT EXISTS idx_ios_release_date ON ios_releases(release_date DESC);

-- ---------------------------------------------------------------------------
-- View: full carrier bundle change history with iOS metadata
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_carrier_history AS
SELECT
    r.full_version_label  AS ios_version,
    r.build,
    r.release_date,
    r.is_beta,
    k.bundle_name,
    COUNT(k.id)           AS new_key_count
FROM carrier_bundle_key_changes k
JOIN ios_releases r ON r.build = k.ios_build
GROUP BY
    r.full_version_label, r.build, r.release_date, r.is_beta, k.bundle_name
ORDER BY r.release_date DESC NULLS LAST, k.bundle_name;

-- ---------------------------------------------------------------------------
-- View: Portugal / country bundle history with file change list
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_pt_bundle_history AS
SELECT
    r.full_version_label        AS ios_version,
    p.ios_build,
    p.ios_release,
    p.release_date,
    r.is_beta,
    p.bundle_type,
    p.bundle_name,
    p.bundle_id,
    p.version_old,
    p.version_new,
    ARRAY(
        SELECT f.file_path
        FROM   pt_bundle_file_changes f
        WHERE  f.pt_change_id = p.id
        ORDER  BY f.file_path
    ) AS files_modified
FROM pt_bundle_changes p
LEFT JOIN ios_releases r ON r.build = p.ios_build
ORDER BY p.release_date DESC NULLS LAST, p.bundle_type, p.bundle_name;

-- ---------------------------------------------------------------------------
-- View: iOS release summary with device and change counts
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_ios_releases AS
SELECT
    r.full_version_label,
    r.build,
    r.version,
    r.is_beta,
    r.os_type,
    r.release_date,
    r.ingested_at,
    COUNT(DISTINCT d.id) AS device_count,
    COUNT(DISTINCT k.id) AS total_new_keys
FROM ios_releases r
LEFT JOIN ios_devices                d ON d.ios_build = r.build
LEFT JOIN carrier_bundle_key_changes k ON k.ios_build = r.build
GROUP BY
    r.id, r.full_version_label, r.build, r.version, r.is_beta, r.os_type,
    r.release_date, r.ingested_at
ORDER BY r.release_date DESC NULLS LAST, r.ingested_at DESC;
