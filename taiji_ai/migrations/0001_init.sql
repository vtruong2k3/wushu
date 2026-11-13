-- 0001_init: core metadata tables (TECH_WORKFLOW_V1 §4.5).
-- Model outputs live in artifact directories; this DB holds identities, revisions and human decisions.

CREATE TABLE participant (
    participant_id   TEXT PRIMARY KEY,            -- pseudonym, e.g. P03
    level_self       TEXT,
    level_coach      TEXT,
    consent_ref      TEXT NOT NULL,
    consent_analysis INTEGER NOT NULL DEFAULT 1 CHECK (consent_analysis IN (0, 1)),
    consent_train    INTEGER NOT NULL DEFAULT 0 CHECK (consent_train IN (0, 1)),
    consent_share    INTEGER NOT NULL DEFAULT 0 CHECK (consent_share IN (0, 1)),
    retention_until  TEXT,
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE recording (
    recording_id   TEXT PRIMARY KEY,
    participant_id TEXT NOT NULL REFERENCES participant(participant_id),
    session_id     TEXT NOT NULL,
    take_id        TEXT NOT NULL,
    camera_id      TEXT NOT NULL,
    sha256         TEXT NOT NULL UNIQUE,
    source_path    TEXT NOT NULL,
    width          INTEGER NOT NULL,
    height         INTEGER NOT NULL,
    rotation       INTEGER NOT NULL DEFAULT 0,
    nominal_fps    REAL,
    vfr            INTEGER NOT NULL DEFAULT 0,
    duration_s     REAL,
    has_audio      INTEGER NOT NULL DEFAULT 0,
    ingested_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX idx_recording_take ON recording(take_id);

CREATE TABLE sync (
    take_id      TEXT NOT NULL,
    cam_a        TEXT NOT NULL,
    cam_b        TEXT NOT NULL,
    offset_s     REAL NOT NULL,
    drift        REAL NOT NULL DEFAULT 0,
    residual_ms  REAL,
    method       TEXT NOT NULL,
    validated_by TEXT,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (take_id, cam_a, cam_b)
);

CREATE TABLE segment (
    segment_id     TEXT NOT NULL,
    revision       INTEGER NOT NULL,
    recording_id   TEXT NOT NULL REFERENCES recording(recording_id),
    start_s        REAL NOT NULL,
    end_s          REAL NOT NULL CHECK (end_s > start_s),
    action         TEXT NOT NULL,
    side           TEXT,
    occurrence     INTEGER,
    view_category  TEXT NOT NULL CHECK (view_category IN ('front', 'side', 'oblique', 'back', 'unknown')),
    flags          TEXT NOT NULL DEFAULT '{}',   -- JSON: orientation_change, occlusion, perspective_shift
    reference_of   TEXT,                          -- set when this segment is a reference template
    created_by     TEXT NOT NULL,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (segment_id, revision)
);

CREATE TABLE run (
    run_id           TEXT PRIMARY KEY,
    segment_id       TEXT NOT NULL,
    segment_revision INTEGER NOT NULL,
    manifest_path    TEXT NOT NULL,
    status           TEXT NOT NULL CHECK (status IN ('queued', 'running', 'done', 'failed', 'partial', 'cancelled')),
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (segment_id, segment_revision) REFERENCES segment(segment_id, revision)
);

CREATE TABLE metric_record (
    metric_name            TEXT NOT NULL,
    version                TEXT NOT NULL,
    intended_use           TEXT NOT NULL,
    supported_views        TEXT NOT NULL,         -- JSON list
    human_variability      REAL,
    smallest_useful_change REAL,
    measurement_error      REAL,
    min_valid_duration_s   REAL,
    threshold              REAL,
    status                 TEXT NOT NULL DEFAULT 'experimental' CHECK (status IN ('experimental', 'enabled', 'retired')),
    signed_by              TEXT,
    signed_at              TEXT,
    PRIMARY KEY (metric_name, version)
);

CREATE TABLE finding (
    finding_id        TEXT NOT NULL,
    revision          INTEGER NOT NULL,
    run_id            TEXT NOT NULL REFERENCES run(run_id),
    criterion_version TEXT NOT NULL,
    t0                REAL NOT NULL,
    t1                REAL NOT NULL,
    metric_ids        TEXT NOT NULL,             -- JSON list
    status            TEXT NOT NULL CHECK (status IN ('ai_suggested', 'coach_confirmed', 'coach_rejected', 'insufficient_evidence')),
    coach_note        TEXT,
    decided_by        TEXT,
    created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (finding_id, revision)
);

CREATE TABLE report (
    report_id     TEXT PRIMARY KEY,
    run_ids       TEXT NOT NULL,                 -- JSON list
    finding_refs  TEXT NOT NULL,                 -- JSON list of [finding_id, revision]
    snapshot_path TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE audit_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    actor   TEXT NOT NULL,
    action  TEXT NOT NULL,
    entity  TEXT NOT NULL,
    before  TEXT,
    after   TEXT,
    at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
