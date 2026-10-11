<!-- agent-workflow:begin -->
# Agent Operating Policy

For substantial software tasks, act as the coordinating agent.

Own:
- the user's objective and acceptance criteria;
- decomposition and dependency ordering;
- delegation and worker scope;
- integration decisions;
- review and final verification.

Do not accumulate broad repository exploration, long logs, or implementation
transcripts in the coordinating context when that work can be delegated to an
isolated subagent.

## Work Directly When Appropriate

Handle work directly when it is small, obvious, and unlikely to create
significant context.

Examples include:
- a targeted lookup;
- a simple grep or file read;
- a trivial one-file edit;
- a small correction to already-understood work.

Do not spawn a subagent merely to avoid a cheap operation.

## Orchestrate Substantial Work

For substantial implementation, broad repository exploration, noisy debugging,
multi-file changes, separable workstreams, or independent review, use the
`orchestrate` skill.

Implementation should normally be performed by implementation subagents when
the change is substantial enough to justify delegation.

The coordinating agent should manage the work rather than duplicate the
worker's implementation process.

Prefer:
- isolated subagents for context-heavy work;
- bounded ownership;
- concise result summaries;
- objective verification results;
- fresh-context review for important changes.

Parallelize only genuinely independent work.

Never assign overlapping write ownership to concurrent subagents.

## Worker Selection

Use the repository's worker role definitions according to their execution boundary:

- `explorer` for read-only repository investigation;
- `implementer` for bounded implementation, testing, and debugging;
- `reviewer` for independent read-only review.

Use the default subagent reasoning effort for normal delegated work.

Before dispatch, read the configured worker model and reasoning effort from
`.codex/config.toml` and the selected role definition. Explicitly select those
settings in the launch call; a role name or tool description is not evidence
that the runtime will apply them. Follow the `orchestrate` skill's worker
launch procedure. In T3 Code, all workers must be T3-owned children launched
through `delegate_task` with explicit provider, model, and reasoning settings,
including same-provider and nested delegation. Do not use native Codex spawn
or custom-role launch tools in T3. Outside T3, native Codex agents may be used
with explicit settings. Do not silently inherit the coordinator's settings.

Preserve the user's runtime and interaction modes during delegation. In T3,
pass `runtimeMode: "inherit"` and `interactionMode: "inherit"`, including for
reviewers and nested workers. A read-only assignment must not switch auto to
supervised (`approval-required`) or change the parent thread's mode. Native
read-only sandboxes and T3 approval modes are separate controls; follow the
orchestration skill's boundary and mode verification procedure.

Escalate a worker to the highest available reasoning effort only when the
orchestration or retry policy indicates that deeper reasoning is justified.

Do not create fictional specialist personas when a bounded task can be assigned
to one of these generic workers.

## Context Discipline

Retrieve detailed source context only when needed for coordination or
integration.

Do not copy large source files, logs, test output, diffs, or worker transcripts
into the coordinating context.

Workers should return only durable information needed for the next decision.

Prefer repository paths, symbols, task-state entries, and concise summaries
over copied implementation context.

For substantial multi-step tasks, use compact durable state according to the
orchestration skill rather than retaining execution history in conversation.

## Review and Verification

Do not mark substantial work complete solely because a subagent reports
success.

Use independent review when the orchestration policy calls for it.

Use evidence-based verification against the acceptance criteria before
completion.

A passing worker report is useful state, not proof by itself.

## Completion

Before completing substantial work, confirm:
- the acceptance criteria;
- relevant verification results;
- integration state;
- substantive review findings;
- genuine remaining risks or limitations.

Keep the final user-facing result concise and focused on outcomes.
<!-- agent-workflow:end -->

# Agent instructions

- Use Conventional Commits: `<type>(<optional scope>): <description>` (for example, `feat: add dependency tracking` or `docs: update README`).
- When you finish working on an issue, commit and push your changes, then open a pull request that links the issue and summarizes the changes and validation.
- Request a review from the collaborator paired with the pull request's GitHub author:
  - `dersual` → `roland-aranas`
  - `roland-aranas` → `dersual`
  - `shivenp14` → `PranavGoyal01`
  - `PranavGoyal01` → `shivenp14`
