# Deployment Guide: MallPlus Logistics Dashboard

## Step 1: Push to GitHub

```bash
cd mallplus-logistics-dashboard

# Configure git (if not done)
git config --global user.email "ralph@fincom.asia"
git config --global user.name "Ralph Santos"

# Create GitHub repository
# Go to: https://github.com/new
# Create repo: mallplus-logistics-dashboard
# Copy HTTPS URL

# Add remote and push
git remote add origin <your-github-url>
git branch -M main
git push -u origin main
```

## Step 2: Set Up Streamlit Cloud

1. **Sign up for Streamlit Cloud**
   - Go to: https://streamlit.io/cloud
   - Click "Sign up"
   - Authenticate with GitHub

2. **Deploy App**
   - In Streamlit Cloud, click "New app"
   - Select repository: `yourusername/mallplus-logistics-dashboard`
   - Select branch: `main`
   - Select file: `app.py`
   - Click "Deploy"

3. **Add Google Credentials Secret**
   - In Streamlit Cloud app settings, go to "Secrets"
   - Create new secret: `google_credentials`
   - Paste content of `google-sa-key.json`
   - OR use Files: Upload the JSON file directly

## Step 3: Update App for Cloud Secrets

The app currently reads from local `~/.openclaw/workspace-logistics/secrets/google-sa-key.json`.

For Streamlit Cloud, update `app.py` line ~55:

**Before (Local):**
```python
creds_path = os.path.expanduser("~/.openclaw/workspace-logistics/secrets/google-sa-key.json")
creds = service_account.Credentials.from_service_account_file(
    creds_path,
    scopes=[...]
)
```

**After (Streamlit Cloud):**
```python
import streamlit as st
import json

# Read from Streamlit secrets
credentials_dict = st.secrets["google_credentials"]
creds = service_account.Credentials.from_service_account_info(
    credentials_dict,
    scopes=[...]
)
```

Then in `.streamlit/secrets.toml` (local, not committed):
```toml
[google_credentials]
type = "service_account"
project_id = "fincom-logistics"
private_key_id = "..."
# ... rest of JSON keys
```

## Step 4: Access Your Dashboard

Once deployed, your app will be live at:
```
https://<streamlit-username>-mallplus-logistics-dashboard-<random>.streamlit.app
```

Share this link with Ralph to access the live dashboard.

---

## Local Testing Before Deploy

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .streamlit/secrets.toml with your credentials
mkdir -p .streamlit
cat > .streamlit/secrets.toml << 'EOF'
[google_credentials]
type = "service_account"
project_id = "fincom-logistics"
# ... paste your google-sa-key.json content here
EOF

# Run locally
streamlit run app.py
```

Visit `http://localhost:8501` to test.

---

## Troubleshooting

**"Permission denied" reading Google Sheets:**
- Verify service account has access to the sheet
- Confirm sheet ID is correct: `1go2cqyqw5ACx-vki974lXV_10chTqTV67BB_rK1WN8c`
- Check secrets are properly configured in Streamlit Cloud

**Dashboard shows no data:**
- Check that mock data was loaded to "Data Simulation" sheet
- Verify Google Sheets API is enabled in project

**Slow performance:**
- Dashboard caches data every 5 minutes (`@st.cache_data(ttl=300)`)
- Reduce cache TTL to 60 seconds for live data: `ttl=60`

---

## Next Steps

1. Push code to GitHub
2. Deploy to Streamlit Cloud
3. Share dashboard link with Ralph
4. Iterate on design based on feedback
5. Add Sage anomaly detection logic (Phase 2)
