# MallPlus Logistics Dashboard

Real-time logistics KPI monitoring for J&T operations on the MallPlus platform.

## Features

- **Executive Dashboard**: KPIs, compliance heatmaps, critical alerts
- **Operations Dashboard**: Parcel status, exception queue, courier performance
- **Analytics Dashboard**: Anomaly detection, cost leakage, system integrity

## Data Source

- Google Sheets: `simulated data` workbook
- Auto-refreshes every 5 minutes
- 55 logistics fields tracked per parcel

## Setup

### Local Development

```bash
# Clone repo
git clone https://github.com/yourusername/mallplus-logistics-dashboard.git
cd mallplus-logistics-dashboard

# Install dependencies
pip install -r requirements.txt

# Create credentials directory
mkdir secrets
# Copy your google-sa-key.json to secrets/

# Run locally
streamlit run app.py
```

Visit `http://localhost:8501` to view the dashboard.

### Deploy to Streamlit Cloud

1. Push code to GitHub
2. Connect GitHub repo to Streamlit Cloud
3. Set environment variable for Google credentials (or use Secrets)
4. Deploy!

## Configuration

Edit `app.py` to customize:
- Colors and styling
- KPI thresholds
- Data refresh interval
- Charts and visualizations

## File Structure

```
mallplus-logistics-dashboard/
├── app.py                 # Main Streamlit app
├── requirements.txt       # Python dependencies
├── README.md             # This file
├── .gitignore            # Git ignore rules
└── secrets/              # (Not committed) Google credentials
```

## Support

For questions, contact the MallPlus Logistics team.
