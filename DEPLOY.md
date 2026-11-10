# Deploy Shop Tracker for free (step by step)

Result: a public web address anyone can open, where a business owner picks their business type, uploads an
Excel/CSV sales file and gets charts, a forecast and extra views for their type of business. Cost: nothing.

You need three free things: a **GitHub account**, **Git** installed, and **Python 3.10 or newer** (only to test
before publishing). Hosting is **Streamlit Community Cloud**, which runs the app straight from your GitHub repo.

---

## Step 1. Test it on your computer first
In the unzipped `shop_tracker` folder (details in README.md):

    python -m venv .venv
    .venv\Scripts\activate            # Mac/Linux: source .venv/bin/activate
    pip install -r requirements.txt
    streamlit run app.py

Pick a business type, upload a sales file, check the tabs. Stop with Ctrl+C. If it does not work here it will not
work online.

## Step 2. Check what you are about to publish
The repository will be **public** (simplest, free). Make sure the folder contains no real business data:
- `.gitignore` already keeps `.xlsx`, `.xls`, `.csv`, `.env` and `secrets.toml` out of Git. Do not remove those lines.
- Do not put customer or sales files in the folder.
- The app needs no passwords or API keys, so there are no secrets to hide.

Your repository root must look like this (`app.py` and `requirements.txt` at the top, not inside another folder):

    app.py
    requirements.txt
    .streamlit/config.toml
    core/ ...

## Step 3. Create the GitHub repository
1. Sign in at github.com and click **New repository** (the + at the top right).
2. Name it, for example `shop-tracker`. Choose **Public**.
3. Leave "Add a README", ".gitignore" and "license" **unticked** (the folder already has them). Click **Create repository**.

## Step 4. Upload the code
**Option A, with Git (recommended).** In a terminal inside the `shop_tracker` folder:

    git init
    git add .
    git commit -m "Shop tracker"
    git branch -M main
    git remote add origin https://github.com/YOUR-USERNAME/shop-tracker.git
    git push -u origin main

First time using Git? Set your name once: `git config --global user.name "Your Name"` and
`git config --global user.email "you@example.com"`. When `git push` asks you to sign in, GitHub no longer accepts
your account password: use the browser sign-in window if it appears, or create a Personal Access Token
(GitHub > Settings > Developer settings > Personal access tokens) and paste it as the password.

**Option B, no Git.** On the new repository page click **uploading an existing file**, drag in the contents of the
folder, and commit. Hidden folders such as `.streamlit` are easy to miss on a Mac (Finder hides them: press
Cmd+Shift+. to show them). The app works without `.streamlit/config.toml`, but then the upload limit is the default
200 MB instead of 10 MB.

Refresh the repository page and confirm you see `app.py`, `requirements.txt`, `core/` and `.streamlit/`.

## Step 5. Deploy on Streamlit Community Cloud
1. Go to **share.streamlit.io** and sign in with GitHub. Allow it to access your repositories when asked.
2. In your workspace click **Create app** (upper right). If it asks "Do you already have an app?" choose
   **Yup, I have an app**.
3. Fill in: **Repository** `YOUR-USERNAME/shop-tracker`, **Branch** `main`, **Main file path** `app.py`.
4. Optional: choose your **App URL** (a name of your own on streamlit.app). It can be changed later in the app's settings.
5. Click **Advanced settings** and pick a **Python version**. This project was tested on 3.12. Leave Secrets empty.
   Click **Save**.
6. Click **Deploy**. The first build takes a few minutes while packages install. Watch the log on the right.

When it finishes you are on your live app. Copy the address from the browser.

## Step 6. Test the live app
- You are asked "What kind of business is this?" first. Choose one.
- Upload a real sales file, confirm the columns in Step 1 on the page, and open every tab.
- Open the address in a private/incognito window and on a phone to see what visitors see.
- Check that the local-path option does **not** appear in the sidebar (it must only exist on your own computer).

## Step 7. Share it
Send the address. Tell users: one row per sale or per day, a date column and a sales amount column, at least
4 weeks of daily data for a forecast. Say honestly that daily forecasts are rough guides (the app shows the typical
error on the page).

## Updating later
Edit the files, then:

    git add .
    git commit -m "What changed"
    git push

Streamlit Community Cloud redeploys automatically after a push.

---

## What the free plan means in practice
These come from Streamlit's documentation and may change, so check the current terms on their site.
- Apps that nobody visits for about 12 hours go to sleep; the next visitor clicks a button and waits a short while.
- Memory is limited (roughly 1 GB), shared by everyone using the app at that moment. Plenty for a shop's sales
  file; very large files (hundreds of thousands of rows) may be slow. The app refuses files over 500,000 rows.
- The app address is public. Anyone with it can use the app. They only see their own upload.
- Logs are visible only to people with write access to your repository.

## Privacy
The app code reads an uploaded file in memory to draw the charts and does not save it. Sales files can still be
sensitive: tell users not to upload personal customer data (names, phone numbers) that the analysis does not need.
Add your own contact or feedback link to the page if you want reports of problems.

## If something goes wrong
| Problem | What to do |
|---|---|
| Build fails with "No matching distribution" or a package error | Open **Manage app** > logs. Try another Python version in Advanced settings (reboot after changing). |
| `ModuleNotFoundError: No module named 'core'` | `app.py` and `core/` must be at the **top** of the repo, not inside a subfolder. Re-check Step 2 and 4. |
| "Oh no. Error running app" | Open **Manage app** > logs to see the real error. Note the logs only show for people with write access. |
| App says the file has no valid dates | Choose the right date column in Step 1; for dates like 03/04/2026 pick day-first or month-first. |
| Upload rejected | Over 10 MB (limit set in `.streamlit/config.toml`). Raise `maxUploadSize`, or split the file. |
| Changes do not appear after pushing | Confirm the push reached GitHub (refresh the repo page). In **Manage app** choose **Reboot**. |
| App is "sleeping" | Normal on the free plan. Click the wake-up button. |

## If Community Cloud does not suit you
Any host that can run `streamlit run app.py --server.port $PORT --server.address 0.0.0.0` can serve this app, for
example the free tier of Render (it also sleeps when idle). I have not tested other hosts. Vercel is not a good fit
for Streamlit itself.
