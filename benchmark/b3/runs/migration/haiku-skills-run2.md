1. **CRITICAL: backfill_order_state.py MAPPING incomplete** – prod has 'PAID' (5,210 rows), 'canceled' (1,988 rows), 'complete' (417 rows), plus 149 NULLs; none map, they stay NULL, migration 0143 NOT NULL constraint fails. The MAPPING covers only the five values from the expected set, but the author's own data shows outliers in prod. Fix: expand MAPPING to cover observed values or map them sensibly (e.g., 'PAID' → PAID, 'canceled' → CANCELLED, 'complete' → SHIPPED), then retest counts.

2. **CRITICAL: jobs/nightly_finance_export.py not updated** – still selects `o.status` after migration 0143 drops it; the export job will crash 02:00 UTC on the day after rollout. Fix: update to select `o.state` and map the IntEnum back to string, or hold this file's update for a later safe commit after verifying the export has migrated.

3. **CRITICAL: no pre-migration verification step** – before running the backfill script, add an explicit step: `SELECT status, count(*) FROM orders WHERE state IS NULL GROUP BY 1` and reconcile against MAPPING to confirm all values are covered. This is your gate before step 3.

4. **Backfill script lacks --dry-run** – script runs blind on prod with no preview. Add a mode (e.g. `--dry-run`) that runs the same UPDATE inside a savepoint, prints the count, and rolls back. Lets you verify counts before commit.

5. **After migration 0143 succeeds, add reconciliation check** – recount total rows before and after: unmigrated + migrated + errored + failed should equal initial total. The script prints only "done: X rows updated", not whether that equals the initial target.

**Cannot ship Thursday as written.** The backfill will leave 7,764+ rows with NULL state, blocking step 4. Fix the MAPPING first, verify pre-migration counts, then re-run backfill on staging with the complete set.