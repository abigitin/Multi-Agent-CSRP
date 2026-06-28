# Billing Archive Permission Fix

Use this source when billing export jobs fail with permission denied on an archive share. Confirm the service account, share ACL, folder inheritance, job runner identity, and recent permission changes. Restore least-privilege write access for the export service account and rerun the failed batch after verifying ownership.
