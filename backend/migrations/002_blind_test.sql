CREATE TABLE IF NOT EXISTS climate_blind_test (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    train_run_id integer NOT NULL REFERENCES climate_run(id),
    test_run_id integer NOT NULL REFERENCES climate_run(id),
    status text NOT NULL CHECK (status IN ('queued', 'completed', 'failed')),
    train_snapshot jsonb NOT NULL,
    test_snapshot jsonb NOT NULL,
    coverage jsonb NOT NULL,
    published jsonb NOT NULL,
    provenance jsonb NOT NULL,
    digests jsonb NOT NULL,
    result jsonb,
    error text,
    attempts integer NOT NULL DEFAULT 0,
    actor text NOT NULL REFERENCES account(username),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (train_run_id <> test_run_id),
    UNIQUE (train_run_id, test_run_id)
);
