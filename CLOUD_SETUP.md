# Run the weather graphics in the cloud (GitHub) — phone page + Google Drive

Once this is set up, GitHub runs the script on its own servers at **5 AM, 11 AM, 4 PM and 9 PM** (Eastern daylight
time; an hour earlier in winter). Your PC doesn't need to be on. Each run:

1. makes every graphic (same as `run_graphics.bat`),
2. updates a **phone-friendly web page** with all of them (tabs for Wide / Vertical / Post / Square, tap to view,
   **Share** straight to Facebook/Instagram, **Download**, caption with a Copy button),
3. copies them into a **Google Drive folder** ("Weather Graphics"), replacing the old ones.

To run it on demand from your phone: GitHub app → your repo → **Actions** → **Weather Graphics** → **Run workflow**.
(The web page also has a "Run now" link that goes there.)

---

## 1. Put the project on GitHub (one time, ~10 min)

1. Make a free account at github.com if you don't have one.
2. Click **+** → **New repository**. Name it `weather-graphics`. Choose **Public** (see note below). Create it.
3. On the new repo page click **uploading an existing file**, then drag in everything from
   `D:\Python Stuff\Python Codes\Weather Graphics Script` **except** the `output` and `cache` folders.
   Make sure the `.github` folder goes up too (it holds the schedule). Click **Commit changes**.
   - Tip: GitHub Desktop (desktop.github.com) makes later updates one click: it shows what changed and you hit
     *Commit* + *Push*. The included `.gitignore` already skips `output` and `cache`.

**Public vs private:** GitHub's free plan only publishes the web page from **public** repos (and gives public repos
unlimited run time). Public means anyone can see the code, `config.json` (including the contact email in
`user_agent`) and the graphics page. If you'd rather keep it private, GitHub Pro ($4/mo) allows a private repo with
the page; the free private plan includes about 2,000 run-minutes a month (a full run takes roughly 5–8 minutes).

## 2. Turn on the web page (one time, 1 min)

Repo → **Settings** → **Pages** → under *Build and deployment*, set **Source** to **GitHub Actions**.

Your page address will be `https://<your-github-name>.github.io/weather-graphics/`.
On your phone, open it and use **Share → Add to Home Screen** so it works like an app.

## 3. Connect Google Drive (one time, ~5 min, on your PC)

This uses **rclone**, a free, well-known tool, to sign in to your Google Drive once. GitHub then uses that saved sign-in.

1. Download rclone for Windows from **rclone.org/downloads**, unzip it (e.g. to `C:\rclone`).
2. Open a Command Prompt in that folder and run: `rclone config`
3. Answer:
   - `n` (new remote) → name: **gdrive**
   - Storage: type **drive** (Google Drive)
   - client_id / client_secret: just press **Enter** (blank)
   - scope: choose **drive.file** (rclone can only see files it creates — it can't touch the rest of your Drive)
   - service_account_file: **Enter** (blank)
   - Edit advanced config: **n**
   - Use web browser to automatically authenticate: **y** → a browser opens → sign in with your Google account → Allow
   - Configure as a Shared Drive: **n** → confirm **y** → **q** to quit
4. Run `rclone config file` to see where the config was saved, open that `rclone.conf` in Notepad, and copy
   **everything** in it.
5. GitHub repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
   - Name: `RCLONE_CONF`
   - Secret: paste the whole rclone.conf text → **Add secret**.
6. (Optional) to use a different Drive folder name: same page → **Variables** tab → New variable
   `DRIVE_FOLDER` = e.g. `Weather Graphics/Latest`.

The Drive folder is created on the first run. In the Drive app, star it or make it available offline for quick access.
Full runs mirror the folder (an expired alert map disappears, just like `output/latest`); one-graphic runs only add
or replace.

## 4. First run

Repo → **Actions** → (if asked, click *I understand… enable workflows*) → **Weather Graphics** → **Run workflow**.
- Tick **Test run with sample data** for a quick check, or leave it off for the real thing.
- *Only these graphics* lets you make just a few, e.g. `daily,7day,alert_maps` (the rest stay as they were).

Green check = done; the page and Drive update a minute later. A red ✗ means something failed — tap it to see the log
(the same messages you'd see in the command window).

---

### Good to know
- **Editing the forecast from your phone:** in the GitHub app open `overrides.json` → edit (pencil) → commit, then
  Run workflow. (The Weather Graphics Editor page still works on your PC; push the saved `overrides.json`/`config.json`
  with GitHub Desktop.)
- **Changing the schedule:** edit the `cron:` lines in `.github/workflows/weather-graphics.yml` (times are UTC).
  GitHub may start scheduled runs a few minutes late at busy times.
- **Keep it active:** GitHub pauses schedules on repos with no activity for 60 days; any commit (or a manual run in
  the Actions tab) keeps them going.
- **Your PC copy keeps working exactly as before** — the cloud is just another place it runs.
- The page and Drive always hold the latest graphics only (like `output/latest`).
