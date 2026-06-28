# SSO Login Loop Runbook

Use this source when a user authenticates successfully but lands back on the sign-in page. Confirm the application reply URL, SAML audience, clock skew, and cookie domain. Ask IAM to clear stale sessions and verify the identity provider assignment group. Resolution normally requires correcting the redirect URI or re-adding the user to the application assignment.
