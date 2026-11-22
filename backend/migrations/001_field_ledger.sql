CREATE TABLE IF NOT EXISTS account (
    username text PRIMARY KEY,
    role text NOT NULL CHECK (role IN ('operator', 'supervisor', 'viewer')),
    password_hash text NOT NULL
);
CREATE TABLE IF NOT EXISTS vine_block (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text NOT NULL UNIQUE,
    name text NOT NULL,
    cultivar text NOT NULL,
    area_ha numeric(6,2) NOT NULL CHECK (area_ha > 0),
    sensor text NOT NULL UNIQUE,
    east_m integer NOT NULL CHECK (east_m BETWEEN 0 AND 1000),
    north_m integer NOT NULL CHECK (north_m BETWEEN 0 AND 1000),
    width_m integer NOT NULL CHECK (width_m BETWEEN 1 AND 500),
    height_m integer NOT NULL CHECK (height_m BETWEEN 1 AND 500),
    CHECK (east_m + width_m <= 1000 AND north_m + height_m <= 1000),
    UNIQUE (id, sensor)
);
CREATE TABLE IF NOT EXISTS microclimate_sample (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    block_id integer NOT NULL,
    sensor text NOT NULL,
    observed_day date NOT NULL,
    slot text NOT NULL CHECK (slot IN ('day', 'night')),
    temp_c double precision NOT NULL CHECK (temp_c BETWEEN -30 AND 60),
    rh_pct double precision NOT NULL CHECK (rh_pct BETWEEN 0 AND 100),
    source text NOT NULL,
    actor text NOT NULL REFERENCES account(username),
    UNIQUE (block_id, observed_day, slot),
    FOREIGN KEY (block_id, sensor) REFERENCES vine_block(id, sensor)
);
CREATE TABLE IF NOT EXISTS climate_run (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    window_end date NOT NULL,
    status text NOT NULL CHECK (status IN ('blocked', 'queued', 'effective', 'review', 'rejected', 'failed')),
    snapshot jsonb NOT NULL,
    digest text NOT NULL,
    coverage jsonb NOT NULL,
    result jsonb,
    error text,
    attempts integer NOT NULL DEFAULT 0,
    actor text NOT NULL REFERENCES account(username),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS single_open_climate_run ON climate_run ((1)) WHERE status IN ('queued', 'review');
CREATE TABLE IF NOT EXISTS climate_label (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    block_id integer NOT NULL REFERENCES vine_block(id),
    run_id integer NOT NULL REFERENCES climate_run(id),
    revision integer NOT NULL CHECK (revision > 0),
    profile text NOT NULL CHECK (profile IN ('cool', 'balanced', 'warm')),
    confidence double precision NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    state text NOT NULL CHECK (state IN ('proposed', 'active', 'superseded', 'rejected')),
    UNIQUE (block_id, revision),
    UNIQUE (block_id, run_id),
    UNIQUE (block_id, id)
);
CREATE UNIQUE INDEX IF NOT EXISTS active_climate_label ON climate_label (block_id) WHERE state = 'active';
CREATE TABLE IF NOT EXISTS irrigation_round (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text NOT NULL UNIQUE,
    block_id integer NOT NULL REFERENCES vine_block(id),
    original_label_id integer NOT NULL,
    label_id integer NOT NULL,
    starts_at timestamptz NOT NULL,
    minutes integer NOT NULL CHECK (minutes BETWEEN 1 AND 120),
    state text NOT NULL CHECK (state IN ('scheduled', 'needs_replan', 'completed', 'cancelled')),
    completed_at timestamptz,
    CHECK ((state = 'completed') = (completed_at IS NOT NULL)),
    FOREIGN KEY (block_id, label_id) REFERENCES climate_label(block_id, id),
    FOREIGN KEY (block_id, original_label_id) REFERENCES climate_label(block_id, id)
);
CREATE TABLE IF NOT EXISTS harvest_note (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    round_id integer NOT NULL UNIQUE REFERENCES irrigation_round(id),
    observed_at timestamptz NOT NULL,
    brix numeric(4,1) NOT NULL CHECK (brix BETWEEN 0 AND 45),
    berry_count integer NOT NULL CHECK (berry_count BETWEEN 20 AND 500),
    note text NOT NULL,
    actor text NOT NULL REFERENCES account(username)
);
CREATE TABLE IF NOT EXISTS field_event (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor text NOT NULL,
    event text NOT NULL,
    subject text NOT NULL,
    details jsonb NOT NULL,
    happened_at timestamptz NOT NULL DEFAULT now()
);
