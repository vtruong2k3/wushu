-- 0002_metric_record: the table of signed metric records (P5.09, DEC-0063).
--
-- Migration 0001 had one `threshold` column, no metric version, no units, and no place for the values a record binds
-- (the thresholds `pause_tau` and `pause_min_s` of the speed metrics and the Butterworth cut-off: DEC-0061 says they
-- are one triple). Nothing ever wrote the table, so it is rebuilt here; if a row exists the migration stops and nothing
-- changes (the failed constraint below rolls the whole transaction back).
--
-- Key: (metric_name, version) where `version` is the record's own version and `metric_version` is the version of the
-- metric code it applies to. A record is `enabled` only with a signature and every number of v3 section 8.2, and its
-- measurement error must be below the smallest useful change (gate G03). An enabled or retired record never changes
-- again, except that an enabled record can be retired (status and signature only). The store (store/metric_records.py)
-- checks the same rules with messages that say why; the checks here are what a direct SQL write cannot get around.

CREATE TEMP TABLE metric_record_guard (
    empty INTEGER NOT NULL,
    CONSTRAINT metric_record_0002_needs_an_empty_table CHECK (empty = 1)
);
INSERT INTO metric_record_guard (empty) SELECT CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END FROM metric_record;
DROP TABLE metric_record_guard;

DROP TABLE metric_record;

CREATE TABLE metric_record (
    metric_name            TEXT NOT NULL,
    version                TEXT NOT NULL,                       -- the record's own version
    metric_version         TEXT NOT NULL,                       -- the version of the metric code it applies to
    units                  TEXT NOT NULL,                       -- of the numbers below; the metric's units
    status                 TEXT NOT NULL DEFAULT 'experimental',
    intended_use           TEXT NOT NULL,                       -- the coach's sentence; never logged
    supported_views        TEXT NOT NULL,                       -- JSON list
    gold_reference         TEXT,                                -- short code of the gold annotations (a report or task ID)
    human_variability      REAL,                                -- in `units`
    smallest_useful_change REAL,                                -- in `units`
    measurement_error      REAL,                                -- in `units`
    min_valid_duration_s   REAL,                                -- seconds
    parameters             TEXT NOT NULL DEFAULT '{}',          -- JSON object: the values the metric must be computed with
    data_sources           TEXT NOT NULL DEFAULT '[]',          -- JSON list: provenance (AGENTS.md 9.4.6)
    signed_by              TEXT,                                -- role code of the coach; for a retired record, who retired it
    signed_at              TEXT,                                -- ISO date
    PRIMARY KEY (metric_name, version),
    CONSTRAINT metric_record_status_is_known CHECK (status IN ('experimental', 'enabled', 'retired')),
    CONSTRAINT metric_record_supported_views_is_list
        CHECK (CASE WHEN json_valid(supported_views) THEN json_type(supported_views) = 'array' ELSE 0 END),
    CONSTRAINT metric_record_parameters_is_object
        CHECK (CASE WHEN json_valid(parameters) THEN json_type(parameters) = 'object' ELSE 0 END),
    CONSTRAINT metric_record_data_sources_is_list
        CHECK (CASE WHEN json_valid(data_sources) THEN json_type(data_sources) = 'array' ELSE 0 END),
    CONSTRAINT metric_record_enabled_is_complete CHECK (
        status <> 'enabled' OR (
            signed_by IS NOT NULL AND signed_at IS NOT NULL AND gold_reference IS NOT NULL
            AND human_variability IS NOT NULL AND smallest_useful_change IS NOT NULL
            AND measurement_error IS NOT NULL AND min_valid_duration_s IS NOT NULL
            AND measurement_error < smallest_useful_change
        )
    ),
    CONSTRAINT metric_record_retired_is_signed CHECK (
        status <> 'retired' OR (signed_by IS NOT NULL AND signed_at IS NOT NULL)
    )
);

-- At most one enabled record for a metric version; drafts and retired records may be many.
CREATE UNIQUE INDEX idx_metric_record_enabled ON metric_record (metric_name, metric_version) WHERE status = 'enabled';

CREATE TRIGGER metric_record_is_immutable_update
BEFORE UPDATE ON metric_record
WHEN OLD.status IN ('enabled', 'retired')
    AND NOT (
        OLD.status = 'enabled' AND NEW.status = 'retired'
        AND NEW.metric_name IS OLD.metric_name AND NEW.version IS OLD.version
        AND NEW.metric_version IS OLD.metric_version AND NEW.units IS OLD.units
        AND NEW.intended_use IS OLD.intended_use AND NEW.supported_views IS OLD.supported_views
        AND NEW.gold_reference IS OLD.gold_reference AND NEW.human_variability IS OLD.human_variability
        AND NEW.smallest_useful_change IS OLD.smallest_useful_change AND NEW.measurement_error IS OLD.measurement_error
        AND NEW.min_valid_duration_s IS OLD.min_valid_duration_s AND NEW.parameters IS OLD.parameters
        AND NEW.data_sources IS OLD.data_sources
    )
BEGIN
    SELECT RAISE(ABORT, 'metric_record_is_immutable: an enabled or retired record cannot be changed (an enabled one can only be retired)');
END;

CREATE TRIGGER metric_record_is_immutable_delete
BEFORE DELETE ON metric_record
WHEN OLD.status IN ('enabled', 'retired')
BEGIN
    SELECT RAISE(ABORT, 'metric_record_is_immutable: an enabled or retired record cannot be deleted');
END;
