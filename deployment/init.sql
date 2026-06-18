-- Audit trail hypertable (TimescaleDB)
-- 7-year retention per SEBI (5+ required)
CREATE TABLE IF NOT EXISTS audit_events (
    event_id UUID,
    timestamp TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}',
    checksum TEXT NOT NULL,
    ntp_offset_ms REAL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create hypertable (TimescaleDB requires timestamp in primary key)
SELECT create_hypertable('audit_events', 'timestamp', if_not_exists => TRUE);

-- Add primary key after hypertable creation (includes partitioning column)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'audit_events_pkey'
    ) THEN
        ALTER TABLE audit_events ADD PRIMARY KEY (event_id, timestamp);
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Primary key may already exist: %', SQLERRM;
END
$$;

-- Retention policy: 7 years (SEBI requires 5+)
SELECT add_retention_policy('audit_events', INTERVAL '7 years', if_not_exists => TRUE);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_events (event_type);
CREATE INDEX IF NOT EXISTS idx_audit_source ON audit_events (source);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events (timestamp DESC);

-- Prevent deletion (append-only)
CREATE OR REPLACE FUNCTION prevent_audit_deletion()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit events are append-only. Deletion not permitted.';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_prevent_audit_deletion
BEFORE DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION prevent_audit_deletion();

-- Prevent updates (append-only)
CREATE OR REPLACE FUNCTION prevent_audit_update()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit events are append-only. Updates not permitted.';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_prevent_audit_update
BEFORE UPDATE ON audit_events
FOR EACH ROW EXECUTE FUNCTION prevent_audit_update();
