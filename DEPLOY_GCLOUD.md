# Deploying to Google Cloud (runs daily at 6 PM CT, no PC required)

This runs the scanner as a **Cloud Run Job** triggered by **Cloud Scheduler** at
18:00 America/Chicago. The container image is built **from source by Cloud Build**,
so you do **not** need Docker installed locally — only the `gcloud` CLI.

Estimated cost: effectively **$0** — one ~15-minute job run per day is well within
the Cloud Run / Cloud Build / Scheduler free tiers.

---

## One-time setup

### 1. Install the gcloud CLI
Download and run the installer:
https://cloud.google.com/sdk/docs/install
Then open a **new** Command Prompt window so `gcloud` is on your PATH.

### 2. Log in and pick a project
```cmd
gcloud auth login
gcloud projects create wyckoff-scanner-app --name="Wyckoff Scanner"   REM or reuse an existing project
gcloud config set project wyckoff-scanner-app
```
> If `projects create` fails, you likely need to pick a globally-unique ID,
> e.g. `wyckoff-scanner-<yourname>`. You must also have **billing enabled** on the
> project (free tier covers this usage): https://console.cloud.google.com/billing

### 3. Enable the required APIs
```cmd
gcloud services enable run.googleapis.com cloudbuild.googleapis.com cloudscheduler.googleapis.com secretmanager.googleapis.com
```

### 4. Store your Gmail App Password as a secret
Create a Gmail App Password first (Google Account -> Security -> 2-Step Verification
-> App passwords). Then:
```cmd
echo YOUR_16_CHAR_APP_PASSWORD| gcloud secrets create wyckoff-smtp-password --data-file=-
```
> Note: no space before the `|`, so the trailing newline isn't included.

Grant the runtime service account access to the secret (PROJECT_NUMBER is shown by
the command below):
```cmd
for /f %i in ('gcloud projects describe wyckoff-scanner-app --format="value(projectNumber)"') do set PNUM=%i
gcloud secrets add-iam-policy-binding wyckoff-smtp-password --member="serviceAccount:%PNUM%-compute@developer.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
```

### 5. Deploy the Cloud Run Job (builds image from source)
Replace the two email addresses with yours:
```cmd
gcloud run jobs deploy wyckoff-scanner ^
  --source . ^
  --region us-central1 ^
  --task-timeout 3600 ^
  --memory 2Gi ^
  --cpu 2 ^
  --max-retries 1 ^
  --set-env-vars WYCKOFF_SMTP_SENDER=you@gmail.com,WYCKOFF_SMTP_RECIPIENT=you@gmail.com,WYCKOFF_MIN_SCORE=80 ^
  --set-secrets WYCKOFF_SMTP_PASSWORD=wyckoff-smtp-password:latest
```

### 6. Test it immediately
```cmd
gcloud run jobs execute wyckoff-scanner --region us-central1
```
Watch logs in the console (link is printed), or:
```cmd
gcloud beta run jobs executions list --job wyckoff-scanner --region us-central1
```
You should receive the email within ~15 minutes.

### 7. Schedule it for 6 PM Central, daily
Cloud Scheduler calls the Cloud Run Admin API to start the job. First give the
default compute service account permission to run jobs:
```cmd
gcloud projects add-iam-policy-binding wyckoff-scanner-app --member="serviceAccount:%PNUM%-compute@developer.gserviceaccount.com" --role="roles/run.invoker"
```
Then create the schedule:
```cmd
gcloud scheduler jobs create http wyckoff-daily ^
  --location us-central1 ^
  --schedule "0 18 * * *" ^
  --time-zone "America/Chicago" ^
  --uri "https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/wyckoff-scanner-app/jobs/wyckoff-scanner:run" ^
  --http-method POST ^
  --oauth-service-account-email %PNUM%-compute@developer.gserviceaccount.com
```

Done. The scan now runs in Google Cloud every day at 6:00 PM Central and emails
setups scoring 80+, whether or not your computer is on.

---

## Updating the code later
After editing `scanner.py`, redeploy with the same command from step 5
(`gcloud run jobs deploy ... --source .`). Cloud Build rebuilds the image.

## Changing the schedule or threshold
- Time: `gcloud scheduler jobs update http wyckoff-daily --location us-central1 --schedule "0 18 * * *" --time-zone "America/Chicago"`
- Score threshold: redeploy step 5 with a different `WYCKOFF_MIN_SCORE`.

## Turning it off
```cmd
gcloud scheduler jobs pause wyckoff-daily --location us-central1     REM pause
gcloud scheduler jobs delete wyckoff-daily --location us-central1    REM remove schedule
gcloud run jobs delete wyckoff-scanner --region us-central1          REM remove job
```

## Remove the old local Windows task (now redundant)
Once the cloud job is confirmed working, delete the 6 PM task on this PC so you
don't get duplicate emails:
```cmd
schtasks /Delete /TN "WyckoffDailyAlerts" /F
```
