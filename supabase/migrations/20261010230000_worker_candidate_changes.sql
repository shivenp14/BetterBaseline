-- A removed fact has no after_fact_id, so candidate identity must be explicit.
-- NULL retains the uniqueness behavior of pre-worker seeded change records.
ALTER TABLE public.changes ADD COLUMN candidate_version_id uuid;
ALTER TABLE public.changes ADD CONSTRAINT changes_candidate_version_fk
    FOREIGN KEY (candidate_version_id, artifact_id, study_id)
    REFERENCES public.artifact_versions(id, artifact_id, study_id);

ALTER TABLE public.changes DROP CONSTRAINT changes_artifact_id_logical_key_before_fact_id_after_fact_i_key;
ALTER TABLE public.changes ADD CONSTRAINT changes_candidate_snapshot_key
    UNIQUE NULLS NOT DISTINCT
    (artifact_id, logical_key, before_fact_id, after_fact_id, candidate_version_id);
CREATE INDEX changes_candidate_version_idx ON public.changes(candidate_version_id);
