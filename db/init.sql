CREATE TABLE IF NOT EXISTS requests (
    id UUID PRIMARY KEY,
    description TEXT NOT NULL CHECK (char_length(description) BETWEEN 10 AND 5000),
    vehicle VARCHAR(120) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS photos (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    content_type TEXT NOT NULL,
    data BYTEA NOT NULL,
    position SMALLINT NOT NULL
);
CREATE INDEX IF NOT EXISTS photos_request_id_idx ON photos(request_id);
CREATE INDEX IF NOT EXISTS requests_created_at_idx ON requests(created_at DESC);

CREATE TABLE IF NOT EXISTS ai_connections (
    provider TEXT PRIMARY KEY CHECK (provider IN ('codex', 'openwebui')),
    base_url TEXT NOT NULL DEFAULT '',
    api_key TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'untested',
    message TEXT NOT NULL DEFAULT '',
    checked_at TIMESTAMPTZ
);
INSERT INTO ai_connections (provider) VALUES ('codex'), ('openwebui') ON CONFLICT DO NOTHING;

ALTER TABLE ai_connections ADD COLUMN IF NOT EXISTS models JSONB NOT NULL DEFAULT '[]';

CREATE TABLE IF NOT EXISTS searches (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    provider TEXT NOT NULL CHECK (provider IN ('codex', 'openwebui')),
    model TEXT NOT NULL DEFAULT '',
    instructions TEXT NOT NULL DEFAULT '',
    vehicle TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    result TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    sources JSONB NOT NULL DEFAULT '[]',
    web_search_observed BOOLEAN NOT NULL DEFAULT FALSE,
    remote_url TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS searches_request_idx ON searches(request_id, created_at DESC);
ALTER TABLE searches ADD COLUMN IF NOT EXISTS preferred_price VARCHAR(80) NOT NULL DEFAULT '';
ALTER TABLE searches ADD COLUMN IF NOT EXISTS reasoning_effort VARCHAR(20) NOT NULL DEFAULT '';
ALTER TABLE searches ADD COLUMN IF NOT EXISTS listings JSONB NOT NULL DEFAULT '[]';
ALTER TABLE searches ADD COLUMN IF NOT EXISTS preferred_options INTEGER NOT NULL DEFAULT 6 CHECK (preferred_options BETWEEN 1 AND 20);
ALTER TABLE searches ADD COLUMN IF NOT EXISTS pickup_areas VARCHAR(500) NOT NULL DEFAULT '';
ALTER TABLE searches ADD COLUMN IF NOT EXISTS shipping_areas VARCHAR(500) NOT NULL DEFAULT '';
CREATE UNIQUE INDEX IF NOT EXISTS searches_one_active_idx ON searches(request_id)
    WHERE status IN ('queued', 'running');
CREATE TABLE IF NOT EXISTS search_photos (
    search_id UUID NOT NULL REFERENCES searches(id) ON DELETE CASCADE,
    position SMALLINT NOT NULL,
    data BYTEA NOT NULL,
    PRIMARY KEY (search_id, position)
);

CREATE TABLE IF NOT EXISTS website_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    urls JSONB NOT NULL DEFAULT '[]'
);
INSERT INTO website_settings (id) VALUES (1) ON CONFLICT DO NOTHING;
ALTER TABLE searches ADD COLUMN IF NOT EXISTS priority_websites JSONB NOT NULL DEFAULT '[]';

CREATE TABLE IF NOT EXISTS schedules (
    id UUID PRIMARY KEY,
    request_id UUID NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    weekday INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    local_time TIME NOT NULL,
    settings JSONB NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    next_run TIMESTAMPTZ NOT NULL,
    last_run TIMESTAMPTZ,
    last_message TEXT NOT NULL DEFAULT '',
    UNIQUE (request_id, weekday, local_time)
);
CREATE INDEX IF NOT EXISTS schedules_due_idx ON schedules(next_run) WHERE enabled;
ALTER TABLE searches ADD COLUMN IF NOT EXISTS schedule_id UUID;

CREATE TABLE IF NOT EXISTS cars (
    id UUID PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    specs JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE requests ADD COLUMN IF NOT EXISTS car_id UUID REFERENCES cars(id) ON DELETE RESTRICT;
CREATE INDEX IF NOT EXISTS requests_car_idx ON requests(car_id);
ALTER TABLE searches ADD COLUMN IF NOT EXISTS car_profile JSONB NOT NULL DEFAULT '{}';

CREATE TABLE IF NOT EXISTS car_photos (
    car_id UUID PRIMARY KEY REFERENCES cars(id) ON DELETE CASCADE,
    data BYTEA NOT NULL
);
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='car_photos' AND column_name='id') THEN
        ALTER TABLE car_photos ADD COLUMN id UUID NOT NULL DEFAULT gen_random_uuid();
        ALTER TABLE car_photos ADD COLUMN position SMALLINT NOT NULL DEFAULT 0;
        ALTER TABLE car_photos DROP CONSTRAINT car_photos_pkey;
        ALTER TABLE car_photos ADD PRIMARY KEY (id);
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS car_photos_car_idx ON car_photos(car_id, position);

CREATE TABLE IF NOT EXISTS listing_blacklist (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    url_key VARCHAR(64) NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    reason VARCHAR(500) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (request_id, url_key)
);
ALTER TABLE searches ADD COLUMN IF NOT EXISTS excluded_listings JSONB NOT NULL DEFAULT '[]';
