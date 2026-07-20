# Phase 20 — Backup Strategy · Disaster Recovery

---

## Prerequisites (read before implementation)

| Doc | Why |
|---|---|
| [`docs/README.md`](README.md) | Doc index and before-you-code checklist |
| [`phase-1-governance-layer.md`](phase-1-governance-layer.md) | `GET /audit/verify` — the exact check this phase's own restore drill runs, real since Phase 1 |
| [`phase-19-deployment-docker.md`](phase-19-deployment-docker.md) | The real Postgres topology (one instance, one logical database per service) this phase's backup/restore scripts operate on |

---

## 0. Priority Decision: Why This Phase Now

**Why it exists here:** every phase through 19 makes a real claim about data durability — the audit log's hash chain (Phase 1) is only tamper-evident if a restore genuinely preserves it intact, not just "most of the rows." This phase turns the master roadmap's own backup-priority table and restore-drill principle into two real, runnable scripts, and — unlike Phase 19's Docker artifacts — actually exercises them against this environment's real, live Postgres instance, since `pg_dump`/`psql` are real tools available here (no daemon-availability constraint the way Docker has one).

**What actually needs backing up, and at what priority** (the master roadmap's own table, carried forward unchanged — it's already correct):

| Data | Priority | Note |
|---|---|---|
| Audit log (Phase 1) | Highest | Hash-chained — a restore must verify the chain is intact, not just that rows exist. A backup that silently drops the tail defeats the tamper-evidence design entirely |
| Business memory, decision/architecture history (Phase 3) | High | Append-only, compliance-relevant |
| Task, subtask, config (Phases 2, 8) | Medium | Operational state, recoverable but disruptive to lose |
| Vector embeddings, ERP knowledge (Phases 3, 9) | Medium | Re-derivable by re-ingestion, but re-ingestion takes real time |
| Short-term / working memory (Phase 3) | None | Designed to be lossy already — not worth backing up |
| Secrets | Separate, stricter process | Backed up via the secrets backend's own mechanism, never lumped in with database backups |
| Ollama model weights | Low | Large but re-downloadable — explicitly not worth the same backup priority as anything above |

**Alternatives considered**
- *A generic `pg_dumpall` covering every logical database in one file, no tier distinction* — rejected as the sole mechanism. `backup.sh` (Section 1) does dump every logical database (simplest real operational default for a single Postgres instance), but the *restore drill itself* is scoped specifically to the audit log's hash chain — the one piece of data whose correctness is independently, structurally verifiable after a restore, not just "the row count looks right." The other tiers don't have an equivalent cheap, structural verification available, so the drill doesn't claim to check them.
- *Simulating a restore drill rather than running one* — rejected. This phase runs a REAL backup, a REAL drop-and-recreate of a disposable database, a REAL restore, and a REAL `GET /audit/verify` call against the restored data (Section 3) — not a description of what one would do.
- *Backing up secrets alongside the database dumps* — rejected, matching the master roadmap's own explicit separation. `DEMO_ERP_DATABASE_URL` and friends live in `.env`/a real secrets backend, never inside a Postgres dump.

**Trade-offs:** the real restore drill (Section 3) only exercises `governance`'s own database (the one service whose data has a structurally-verifiable post-restore check) — the other ten logical databases are backed up by the same script but not independently drill-tested this phase, since there's no equivalent cheap correctness check for them without re-running each service's own live test suite against the restored data (a real, larger undertaking than this phase's scope).

**Security implications:** `backup.sh` produces plain SQL dumps containing real (dev-environment) data — never encrypted or shipped anywhere by this phase's own scripts. A real deployment's backup destination (encrypted object storage, offsite replication) is an operational decision for whoever runs this, named as an explicit gap, not asserted as solved.

**Performance implications:** none evaluated at the scale this phase's own environment runs at.

**Future scalability:** the same restore-drill pattern (real backup → real restore → real structural check) generalizes to any future service that gains its own hash-chained or otherwise structurally-verifiable data.

**Estimated complexity:** Low. Two real, small shell scripts; the genuine work this phase does is actually running the drill once and reporting the real result, not writing more code.

---

## 1. `deploy/backup.sh`

Real `pg_dump` (custom format, `-Fc`, enabling `pg_restore`'s selective/parallel restore) of every logical database from Phase 19's own topology, into a timestamped directory. Takes `POSTGRES_HOST`/`POSTGRES_PORT`/`POSTGRES_USER`/`POSTGRES_PASSWORD` from the environment (matching `.env`'s own convention, Phase 19), defaults to `localhost:5432`/`postgres` for the local-dev path this phase's own drill (Section 3) actually exercises.

```bash
./deploy/backup.sh [output_dir]   # defaults to ./backups/<UTC timestamp>/
```

## 2. `deploy/restore.sh`

Real `pg_restore` (or `psql` for the fallback plain-SQL path) from a given backup directory into a named target database — never the source database implicitly, a real target name is always required, since silently restoring over a live database is exactly the kind of destructive default this project's own operating discipline refuses (`CLAUDE.md`'s own safety posture, carried through to tooling).

```bash
./deploy/restore.sh <backup_dir> <database_name> [target_db_name]
```

## 3. The real restore drill this phase actually ran

Not simulated — a real sequence, run once against this environment's own Postgres instance, using a disposable database (`governance_dr_drill`), never any database another phase's own tests or live services depend on:

1. Started a real governance instance pointed at a fresh `governance_dr_drill` database.
2. Generated real audit events through it (`POST /security/authorize` calls, the same real hash-chained path every other phase's own testing already exercises).
3. Confirmed `GET /audit/verify` returned `{"valid": true, "events_checked": N}` on the real, live chain — the baseline.
4. Ran `backup.sh` for real against that database.
5. Dropped `governance_dr_drill` entirely and recreated it empty — a real, deliberate destruction, not a described one.
6. Ran `restore.sh` for real against the empty database from the real backup file.
7. Restarted governance pointed at the restored database and called `GET /audit/verify` again.

**Real result, not asserted:** see the honesty note in `services/governance/README.md`'s own Phase 20 section for the exact `events_checked` count and `valid` result from this specific run — the actual output of step 7, not a prediction of what it should say.

---

## 4. Explicitly Out of Scope

RTO/RPO targets — a company policy decision, not asserted here as fact, per the master roadmap's own explicit framing. Encrypted or offsite backup storage — this phase's scripts produce local files only. Automated/scheduled backups (cron, systemd timers) — a real, separate operational concern for whoever deploys this. Restore-drilling the other ten logical databases — named honestly as not yet done (Section 0's trade-off), not silently assumed covered by the one drill this phase actually ran.

---

## Next

Phase 21: consolidated reference — pulling together the API surface index, database schema index, and component diagram already sketched in `phases-12-21-remaining-subsystems.md` into something that reflects the real, as-built system rather than the original speculative one.
