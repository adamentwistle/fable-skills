1. **Critical: `jobs/nightly_finance_export.py` is an unidentified reader.** It queries `o.status` directly in SQL; after migration 0143 drops the column, this job fails Friday 02:00 UTC. Update it to select `o.state` and map to the string enum name for the export.

2. **Incomplete backfill mapping.** Prod data includes 7,615 rows with unmapped status values (PAID uppercase: 5,210; canceled American spelling: 1,988; complete: 417). The CASE statement produces NULL for these; they remain state=NULL after backfill. Migration 0143's NOT NULL constraint will fail. Backfill must either map these values (ask whether 'complete'='shipped', 'canceled'='cancelled', 'PAID'='paid') or reject the migration until mapped.

3. **No dry-run on prod data.** Run the backfill script as dry-run against prod to verify the actual count of mapped vs. unmapped rows before the rollout window. The staging count (1,055,000/2,104,377) and the incomplete progress output shown suggest the author didn't verify reconciliation on the full prod dataset.

4. **Incomplete grep.** The author grepped only under `app/` and found three readers; the directive was to grep the whole codebase for the field name. Search for any other readers or writers in other service directories, reporting scripts, or webhooks before proceeding.

5. Before step 3 (backfill): require explicit data reconciliation — count unmapped rows, confirm mapping strategy, run dry-run on prod, document before-count and expected after-count.

**Cannot ship Thursday.** The unmapped data and missing reader will cause silent data loss (NULL state) and a job failure. Resolve the mapping and nightly export first; Thursday slot requires data verification before the backfill runs.