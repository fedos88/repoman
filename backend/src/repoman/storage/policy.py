"""Storage policy constants (design §7.5).

They become configurable once system settings are stored in the database.
"""

from datetime import timedelta

DEFAULT_STORE_NAME = "default"

# Deleted blobs are physically removed after this delay (safe backups, design §7.7).
GC_GRACE_PERIOD = timedelta(hours=24)
# Objects without a database row, and abandoned temporary files, are removed after this age.
ORPHAN_MIN_AGE = timedelta(hours=24)

# Below max(ratio * total, min bytes) of free space no new blobs are written.
LOW_SPACE_RATIO = 0.05
LOW_SPACE_MIN_BYTES = 10 * 1024**3

BLOB_GC_JOB = "blob_gc"
BLOB_GC_INTERVAL_SECONDS = 3600
STORE_CLEANUP_JOB = "blob_store_cleanup"
STORE_CLEANUP_INTERVAL_SECONDS = 86400
