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
ALTER TABLE searches ADD COLUMN IF NOT EXISTS research_meta JSONB NOT NULL DEFAULT '{}';

ALTER TABLE schedules ADD COLUMN IF NOT EXISTS discord_notify BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE searches ADD COLUMN IF NOT EXISTS discord_notify BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS discord_notifications (
    search_id UUID PRIMARY KEY REFERENCES searches(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sending', 'sent', 'failed', 'skipped')),
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_error TEXT NOT NULL DEFAULT '',
    message_id TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS discord_notifications_due_idx ON discord_notifications(next_attempt)
    WHERE status = 'pending';
ALTER TABLE discord_notifications ADD COLUMN IF NOT EXISTS messages JSONB NOT NULL DEFAULT '{}';

CREATE TABLE IF NOT EXISTS discord_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    bot_token TEXT NOT NULL DEFAULT '',
    channel_id VARCHAR(20) NOT NULL DEFAULT '',
    owner_id VARCHAR(20) NOT NULL DEFAULT '',
    app_url TEXT NOT NULL DEFAULT '',
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    version INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'unconfigured',
    message TEXT NOT NULL DEFAULT '',
    checked_at TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ
);
INSERT INTO discord_settings (id) VALUES (1) ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS discord_confirmations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    search_id UUID NOT NULL REFERENCES searches(id) ON DELETE CASCADE,
    listing_index INTEGER NOT NULL,
    user_id VARCHAR(20) NOT NULL,
    channel_id VARCHAR(20) NOT NULL,
    message_id VARCHAR(20) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT now() + interval '5 minutes',
    used_at TIMESTAMPTZ
);

-- Optional technical facts; old requests retain an empty profile.
ALTER TABLE requests ADD COLUMN IF NOT EXISTS part_profile JSONB NOT NULL DEFAULT '{}';
ALTER TABLE requests ADD COLUMN IF NOT EXISTS profile_revision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE searches ADD COLUMN IF NOT EXISTS part_profile JSONB NOT NULL DEFAULT '{}';
CREATE TABLE IF NOT EXISTS part_drafts (
    id UUID PRIMARY KEY, owner TEXT NOT NULL, request_id UUID REFERENCES requests(id) ON DELETE CASCADE,
    revision INTEGER NOT NULL DEFAULT 0, content JSONB NOT NULL DEFAULT '{}',
    created_request_id UUID REFERENCES requests(id) ON DELETE CASCADE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS part_draft_photos (
    id UUID PRIMARY KEY, draft_id UUID NOT NULL REFERENCES part_drafts(id) ON DELETE CASCADE,
    position SMALLINT NOT NULL, data BYTEA NOT NULL
);
CREATE TABLE IF NOT EXISTS part_enrichments (
    id UUID PRIMARY KEY, draft_id UUID NOT NULL REFERENCES part_drafts(id) ON DELETE CASCADE,
    draft_revision INTEGER NOT NULL, idempotency_key UUID NOT NULL,
    provider TEXT NOT NULL CHECK (provider IN ('codex','openwebui')), model TEXT NOT NULL,
    reasoning_effort TEXT NOT NULL DEFAULT '', input JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','completed','failed','cancelled')),
    output JSONB NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '', remote_url TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ,
    UNIQUE (draft_id, idempotency_key)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_part_enrichment_active ON part_enrichments(draft_id) WHERE status IN ('queued','running');
CREATE TABLE IF NOT EXISTS part_enrichment_photos (
    run_id UUID NOT NULL REFERENCES part_enrichments(id) ON DELETE CASCADE,
    position SMALLINT NOT NULL, data BYTEA NOT NULL, PRIMARY KEY(run_id, position)
);

ALTER TABLE part_enrichments ADD COLUMN IF NOT EXISTS stage TEXT NOT NULL DEFAULT 'queued';
ALTER TABLE part_enrichments ADD COLUMN IF NOT EXISTS progress_at TIMESTAMPTZ;
CREATE TABLE IF NOT EXISTS worker_heartbeats (
    name TEXT PRIMARY KEY,
    seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS language_preferences (
    id SMALLINT PRIMARY KEY CHECK (id=1),
    response_language TEXT NOT NULL DEFAULT 'en' CHECK (response_language IN ('en','pt','fr','de','es')),
    search_languages JSONB NOT NULL DEFAULT '["en","pt","fr","de","es"]'
);
INSERT INTO language_preferences(id) VALUES(1) ON CONFLICT DO NOTHING;
ALTER TABLE searches ADD COLUMN IF NOT EXISTS language_preferences JSONB NOT NULL DEFAULT '{}';
ALTER TABLE part_enrichments ADD COLUMN IF NOT EXISTS purpose TEXT NOT NULL DEFAULT 'profile';
