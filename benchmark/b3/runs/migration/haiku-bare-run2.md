1. Backfill script incomplete — doesn't map 'PAID', 'canceled', 'complete' (7,615 prod rows shown in GROUP BY output); they'll stay NULL and block migration 0143's NOT NULL constraint. Extend MAPPING to handle all 8 distinct statuses or audit/clean the 3 unmapped ones before running backfill.

2. jobs/nightly_finance_export.py not updated — still references `orders.status`, which is dropped in migration 0143; the job will fail when run after Thursday's rollout. Update to use `state` instead, mapping OrderState back to status strings for the Finance export format.

3. Pre-rollout: test the updated backfill script on a copy of prod data to confirm no rows remain NULL before proceeding to migration 0143.

4. Pre-rollout: update and deploy the fixed nightly_finance_export.py; confirm it runs successfully before the rollout window.

**Cannot ship Thursday as planned.** The incomplete backfill mapping will leave ~7,615 rows with NULL state, blocking migration 0143's NOT NULL constraint. The unupdated nightly_finance_export.py will break the finance pipeline after status is dropped.