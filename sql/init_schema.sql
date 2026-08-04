-- Reference snapshot only; application schema changes are managed by Alembic migrations.
-- This file is not read by runtime code and must not be used to upgrade a database.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE company (
    company_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_name TEXT NOT NULL UNIQUE
);

CREATE TABLE position (
    position_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    position_name TEXT NOT NULL UNIQUE
);

CREATE TABLE company_alias (
    company_alias_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    raw_name TEXT NOT NULL UNIQUE,
    company_id INTEGER NOT NULL REFERENCES company(company_id)
);

CREATE TABLE position_alias (
    position_alias_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    raw_name TEXT NOT NULL UNIQUE,
    position_id INTEGER NOT NULL REFERENCES position(position_id)
);

CREATE TABLE application (
    application_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    latest_status TEXT,
    latest_status_received_at TIMESTAMPTZ,
    latest_status_email_id INTEGER,
    latest_jd_id INTEGER,
    CHECK (
        latest_status IS NULL OR latest_status IN (
            'applied',
            'assessment',
            'interview',
            'offer',
            'rejection'
        )
    ),
    company_id INTEGER NOT NULL REFERENCES company(company_id),
    position_id INTEGER NOT NULL REFERENCES position(position_id),
    UNIQUE (company_id, position_id)
);

CREATE TABLE email (
    email_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    message_id TEXT NOT NULL UNIQUE,
    received_at TIMESTAMPTZ NOT NULL,
    recipient TEXT NOT NULL,
    sender TEXT NOT NULL,
    subject TEXT,
    body_text TEXT,
    source_path TEXT,
    email_type TEXT,
    CHECK (
        email_type IS NULL OR email_type IN (
            'auth',
            'delivery-failure',
            'logistics',
            'unrelated',
            'unknown',
            'applied',
            'profile-update',
            'assessment',
            'interview',
            'offer',
            'rejection'
        )
    ),
    company_raw TEXT,
    position_raw TEXT,
    application_link_method TEXT,
    CHECK (
        application_link_method IS NULL OR application_link_method IN (
            'exact',
            'company_singleton',
            'manual'
        )
    ),
    application_id INTEGER REFERENCES application(application_id)
);

CREATE TABLE job_description (
    jd_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    captured_at DATE,
    company_raw TEXT,
    position_raw TEXT,
    location_raw TEXT,
    salary_raw TEXT,
    responsibilities TEXT,
    qualifications TEXT,
    nice_to_have TEXT,
    source_url TEXT,
    source_path TEXT,
    application_id INTEGER REFERENCES application(application_id)
);

CREATE TABLE retrieval_chunk (
    chunk_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_type TEXT NOT NULL CHECK (
        source_type IN ('email', 'job_description')
    ),
    source_id INTEGER NOT NULL,
    application_id INTEGER REFERENCES application(application_id),
    company_id INTEGER REFERENCES company(company_id),
    position_id INTEGER REFERENCES position(position_id),
    email_type TEXT,
    CHECK (
        (
            source_type = 'email'
            AND email_type IN (
                'applied',
                'assessment',
                'interview',
                'offer',
                'rejection',
                'logistics',
                'profile-update'
            )
        ) OR (
            source_type = 'job_description'
            AND email_type IS NULL
        )
    ),
    semantic_fields TEXT[] NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(1024) NOT NULL,    -- Keep in sync with scripts.constants.EMBEDDING_DIMENSION.
    embedding_model TEXT NOT NULL,
    embedded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_type, source_id)
);
