# Precise 6 PM scheduling via cron-job.org (free)

GitHub Actions' built-in cron is unreliable on the free tier (it fired hours
late at random times). This sets up a **free external cron** that triggers the
scan at *exactly* 6:00 PM US Central every day.

How it works: **cron-job.org** sends an HTTPS request at 6 PM Central → GitHub's
`workflow_dispatch` API → the *Daily Wyckoff Scan* workflow runs → email + dashboard.

---

## Step 1 — Create a GitHub token (fine-grained, minimal scope)

1. Go to https://github.com/settings/personal-access-tokens/new
2. **Token name:** `cron-job wyckoff trigger`
3. **Expiration:** 1 year (or "No expiration")
4. **Resource owner:** swatz775
5. **Repository access:** *Only select repositories* → choose **wyckoff-scanner**
6. **Permissions:** expand *Repository permissions* → set **Actions** to **Read and write**
   (leave everything else "No access")
7. Click **Generate token** and **copy it** (starts with `github_pat_…`). You won't
   see it again.

This token can do nothing except trigger Actions on this one repo.

## Step 2 — Create a free cron-job.org account

1. Sign up at https://cron-job.org/en/signup/
2. Verify your email and log in.

## Step 3 — Create the cron job

Click **Create cronjob** and fill in:

**Common tab**
- **Title:** `Wyckoff 6PM Scan`
- **URL:**
  ```
  https://api.github.com/repos/swatz775/wyckoff-scanner/actions/workflows/daily-scan.yml/dispatches
  ```
- **Schedule:** Every day at **18:00** (6 PM). Set **minutes = 0**, **hours = 18**,
  every day/month/weekday.
- **Timezone:** select **America/Chicago** (this is the key setting — it handles
  daylight saving automatically, so it's always 6 PM Central).

**Advanced tab**
- **Request method:** `POST`
- **Request headers** — add these three (Key → Value):
  | Key | Value |
  |-----|-------|
  | `Authorization` | `Bearer github_pat_YOUR_TOKEN_HERE` |
  | `Accept` | `application/vnd.github+json` |
  | `X-GitHub-Api-Version` | `2022-11-28` |
- **Request body:**
  ```json
  {"ref":"main"}
  ```

Save. Optionally use **"Run now"** (or the test button) to fire it once — within
~2 minutes you should get the email and the dashboard at
https://swatz775.github.io/wyckoff-scanner/ should refresh.

> A successful trigger returns HTTP **204 No Content** — that's normal and means
> GitHub accepted the request.

---

## Notes
- You can still trigger manually anytime: Actions → Daily Wyckoff Scan → Run workflow.
- To change the time, edit the cron-job.org schedule (no code change needed).
- If the token ever expires, regenerate it (Step 1) and update the `Authorization`
  header value in the cron job.
