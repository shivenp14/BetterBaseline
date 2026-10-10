-- Backend-owned tables. Browser roles have no direct access until #18.
CREATE TABLE public.studies (
    id uuid PRIMARY KEY,
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.memberships (
    study_id uuid NOT NULL REFERENCES public.studies(id),
    user_id uuid NOT NULL,
    role text NOT NULL CHECK (role IN ('owner', 'member')),
    PRIMARY KEY (study_id, user_id)
);
CREATE INDEX memberships_user_idx ON public.memberships(user_id, study_id);

CREATE TABLE public.artifacts (
    id uuid PRIMARY KEY,
    study_id uuid NOT NULL REFERENCES public.studies(id),
    name text NOT NULL,
    kind text NOT NULL,
    approved_version_id uuid,
    UNIQUE (id, study_id)
);
CREATE INDEX artifacts_study_idx ON public.artifacts(study_id);
CREATE INDEX artifacts_approved_version_idx ON public.artifacts(approved_version_id);

CREATE TABLE public.artifact_versions (
    id uuid PRIMARY KEY,
    artifact_id uuid NOT NULL,
    study_id uuid NOT NULL,
    version_number integer NOT NULL CHECK (version_number > 0),
    previous_version_id uuid,
    filename text NOT NULL,
    status text NOT NULL CHECK (status IN ('uploaded', 'processing', 'ready', 'failed')),
    storage_path text UNIQUE,
    content_hash text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (artifact_id, version_number),
    UNIQUE (id, study_id),
    UNIQUE (id, artifact_id, study_id),
    FOREIGN KEY (artifact_id, study_id) REFERENCES public.artifacts(id, study_id),
    FOREIGN KEY (previous_version_id, artifact_id, study_id)
        REFERENCES public.artifact_versions(id, artifact_id, study_id),
    CHECK (previous_version_id IS NULL OR previous_version_id <> id)
);
CREATE INDEX versions_study_idx ON public.artifact_versions(study_id);
CREATE INDEX versions_previous_idx ON public.artifact_versions(previous_version_id);
ALTER TABLE public.artifacts ADD CONSTRAINT artifacts_approved_version_fk
    FOREIGN KEY (approved_version_id, id, study_id)
    REFERENCES public.artifact_versions(id, artifact_id, study_id);

CREATE TABLE public.source_fragments (
    id uuid PRIMARY KEY,
    study_id uuid NOT NULL,
    artifact_id uuid NOT NULL,
    version_id uuid NOT NULL,
    locator text NOT NULL,
    quote text NOT NULL,
    UNIQUE (id, version_id, artifact_id, study_id),
    FOREIGN KEY (version_id, artifact_id, study_id)
        REFERENCES public.artifact_versions(id, artifact_id, study_id)
);
CREATE INDEX fragments_version_idx ON public.source_fragments(version_id);
CREATE INDEX fragments_artifact_idx ON public.source_fragments(artifact_id);
CREATE INDEX fragments_study_idx ON public.source_fragments(study_id);

CREATE TABLE public.facts (
    id uuid PRIMARY KEY,
    study_id uuid NOT NULL,
    artifact_id uuid NOT NULL,
    version_id uuid NOT NULL,
    fragment_id uuid NOT NULL,
    logical_key text NOT NULL,
    label text NOT NULL,
    value jsonb NOT NULL CHECK (jsonb_typeof(value) IN ('string', 'number', 'boolean', 'null')),
    unit text,
    UNIQUE (version_id, logical_key),
    UNIQUE (id, study_id),
    UNIQUE (id, artifact_id, study_id),
    FOREIGN KEY (version_id, artifact_id, study_id)
        REFERENCES public.artifact_versions(id, artifact_id, study_id),
    FOREIGN KEY (fragment_id, version_id, artifact_id, study_id)
        REFERENCES public.source_fragments(id, version_id, artifact_id, study_id)
);
CREATE INDEX facts_study_idx ON public.facts(study_id);
CREATE INDEX facts_artifact_idx ON public.facts(artifact_id);
CREATE INDEX facts_fragment_idx ON public.facts(fragment_id);

CREATE TABLE public.dependencies (
    id uuid PRIMARY KEY,
    study_id uuid NOT NULL,
    from_fact_id uuid NOT NULL,
    to_fact_id uuid NOT NULL,
    relationship text NOT NULL CHECK (relationship IN ('defines', 'describes', 'calculated_from', 'requires', 'covered_by')),
    tracking text NOT NULL CHECK (tracking IN ('current', 'pinned')),
    status text NOT NULL CHECK (status IN ('proposed', 'confirmed')),
    evidence jsonb NOT NULL CHECK (jsonb_typeof(evidence) = 'array'),
    UNIQUE (id, study_id),
    FOREIGN KEY (from_fact_id, study_id) REFERENCES public.facts(id, study_id),
    FOREIGN KEY (to_fact_id, study_id) REFERENCES public.facts(id, study_id)
);
CREATE INDEX dependencies_study_idx ON public.dependencies(study_id);
CREATE INDEX dependencies_from_idx ON public.dependencies(from_fact_id);
CREATE INDEX dependencies_to_idx ON public.dependencies(to_fact_id);

CREATE TABLE public.changes (
    id uuid PRIMARY KEY,
    study_id uuid NOT NULL,
    artifact_id uuid NOT NULL,
    logical_key text NOT NULL,
    before_fact_id uuid,
    after_fact_id uuid,
    before_value jsonb NOT NULL CHECK (jsonb_typeof(before_value) IN ('string', 'number', 'boolean', 'null')),
    after_value jsonb NOT NULL CHECK (jsonb_typeof(after_value) IN ('string', 'number', 'boolean', 'null')),
    kind text NOT NULL CHECK (kind IN ('added', 'removed', 'modified')),
    UNIQUE (id, study_id),
    UNIQUE NULLS NOT DISTINCT (artifact_id, logical_key, before_fact_id, after_fact_id),
    FOREIGN KEY (artifact_id, study_id) REFERENCES public.artifacts(id, study_id),
    FOREIGN KEY (before_fact_id, artifact_id, study_id) REFERENCES public.facts(id, artifact_id, study_id),
    FOREIGN KEY (after_fact_id, artifact_id, study_id) REFERENCES public.facts(id, artifact_id, study_id),
    CHECK ((kind = 'added' AND before_fact_id IS NULL AND after_fact_id IS NOT NULL)
        OR (kind = 'removed' AND before_fact_id IS NOT NULL AND after_fact_id IS NULL)
        OR (kind = 'modified' AND before_fact_id IS NOT NULL AND after_fact_id IS NOT NULL))
);
CREATE INDEX changes_study_idx ON public.changes(study_id);
CREATE INDEX changes_before_idx ON public.changes(before_fact_id);
CREATE INDEX changes_after_idx ON public.changes(after_fact_id);

CREATE TABLE public.findings (
    id uuid PRIMARY KEY,
    study_id uuid NOT NULL,
    change_id uuid NOT NULL,
    affected_fact_id uuid NOT NULL,
    affected_artifact_id uuid NOT NULL,
    path_edge_ids uuid[] NOT NULL,
    action text NOT NULL CHECK (action IN ('review_document', 'rerun_analysis', 'review_support')),
    explanation text NOT NULL,
    sources jsonb NOT NULL CHECK (jsonb_typeof(sources) = 'array'),
    status text NOT NULL CHECK (status IN ('open', 'in_review', 'resolved', 'dismissed')),
    owner_id uuid,
    resolution jsonb CHECK (jsonb_typeof(resolution) = 'object'),
    UNIQUE (change_id, affected_fact_id),
    FOREIGN KEY (change_id, study_id) REFERENCES public.changes(id, study_id),
    FOREIGN KEY (affected_fact_id, affected_artifact_id, study_id)
        REFERENCES public.facts(id, artifact_id, study_id)
);
CREATE INDEX findings_study_idx ON public.findings(study_id);
CREATE INDEX findings_fact_idx ON public.findings(affected_fact_id);
CREATE INDEX findings_artifact_idx ON public.findings(affected_artifact_id);

CREATE TABLE public.audit_events (
    id uuid PRIMARY KEY,
    study_id uuid NOT NULL REFERENCES public.studies(id),
    actor_id uuid NOT NULL,
    action text NOT NULL,
    entity_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_study_time_idx ON public.audit_events(study_id, created_at, id);

CREATE TABLE public.jobs (
    id uuid PRIMARY KEY,
    study_id uuid NOT NULL,
    version_id uuid NOT NULL UNIQUE,
    status text NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    stage text NOT NULL DEFAULT 'queued',
    error text,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    lease_expires_at timestamptz,
    claimed_by text,
    next_retry_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (version_id, study_id) REFERENCES public.artifact_versions(id, study_id)
);
CREATE INDEX jobs_study_idx ON public.jobs(study_id);
CREATE INDEX jobs_claim_idx ON public.jobs(status, next_retry_at, created_at)
    WHERE status IN ('queued', 'running');

-- No browser policies in #14: unauthenticated API stays on localhost.
-- Backend connects as an owner/privileged database role. #18 supplies auth.
DO $$
DECLARE table_name text; role_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['studies', 'memberships', 'artifacts', 'artifact_versions',
        'source_fragments', 'facts', 'dependencies', 'changes', 'findings', 'audit_events', 'jobs']
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC', table_name);
        FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated'] LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
                EXECUTE format('REVOKE ALL ON TABLE public.%I FROM %I', table_name, role_name);
            END IF;
        END LOOP;
    END LOOP;
END $$;
