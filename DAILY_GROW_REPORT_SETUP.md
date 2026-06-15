# Daily Grow Report Setup Guide

## ✨ Overview

The RDWC system now sends you a **beautiful daily email report** with:
- 📷 **Current grow photo** (from timelapse camera)
- 📊 **Current system status** (pH, EC, temperature, all readings)
- 🎯 **Week's targets and forecasts** (where we're going)
- ⚡ **System alerts** (any issues detected)
- 💊 **Dosing history** (pH & EC doses in past 24h)
- ⚙️ **Hardware status** (pumps, lights, chiller, e-stop)

**Default Schedule:** Daily at **07:00 UTC** (configurable)

---

## 📋 Setup Required (5 minutes)

### Step 1: Configure GitHub Secrets

Go to your repository:  
**Settings** → **Secrets and variables** → **Actions**

Then create these 6 secrets:

#### **RDWC_HOST** ⭐ Required
- Your Raspberry Pi's IP address
- Example: `192.168.88.55`

#### **RDWC_PORT** ⭐ Required  
- Port where RDWC API runs (usually 8080)
- Example: `8080`

#### **EMAIL_SERVER** ⭐ Required
- SMTP server for your email provider
- **Gmail:** `smtp.gmail.com`
- **Outlook:** `smtp-mail.outlook.com`
- **Generic:** `mail.your-domain.com`

#### **EMAIL_PORT** ⭐ Required
- SMTP port (usually 587 for TLS or 465 for SSL)
- Example: `587`

#### **EMAIL_USER** ⭐ Required
- Your email address
- Example: `your-email@gmail.com`

#### **EMAIL_PASSWORD** ⭐ Required
- **⚠️ IMPORTANT:**
  - **Gmail Users:** Use an [App Password](https://support.google.com/accounts/answer/185833), NOT your regular password
  - **Outlook/Other:** Check your email provider's documentation for app-specific passwords
- Example: `abcd efgh ijkl mnop` (Gmail app password format)

#### **EMAIL_TO** ⭐ Required
- Where to send the report (can be different from EMAIL_USER)
- Example: `your-personal-email@gmail.com`

#### **EMAIL_FROM** (Optional)
- Display name for "From" field
- Defaults to EMAIL_USER if not set
- Example: `RDWC System <noreply@example.com>`

---

### Step 2: Test the Workflow

1. Go to your repository on GitHub
2. Click **Actions** tab
3. Select **Daily Grow Report** from the workflow list
4. Click **Run workflow** → **Run workflow** button
5. Wait 30-60 seconds and check your email

**Expected result:** You should receive a formatted HTML email with:
- Latest camera snapshot of your grow
- Current readings (pH, EC, temperature)
- This week's nutrient schedule
- System alerts (if any)

---

### Step 3: Adjust Schedule (Optional)

The report runs daily at **07:00 UTC**. To change:

Edit `.github/workflows/daily-report.yml` line 8:

```yaml
on:
  schedule:
    - cron: '0 7 * * *'  # Change: MM HH * * * (UTC)
```

**Cron Examples:**
- `0 6 * * *` = 06:00 UTC (1 hour earlier)
- `30 7 * * *` = 07:30 UTC (30 mins later)  
- `0 22 * * *` = 22:00 UTC (10 PM)
- `0 14 * * *` = 14:00 UTC (2 PM)

Then commit and push to `main`:
```bash
git add .github/workflows/daily-report.yml
git commit -m "Change daily report schedule to $(time)"
git push origin main
```

---

## 🔧 Gmail Setup (Step-by-Step)

### 1. Enable 2-Factor Authentication
- Go to [Google Account](https://myaccount.google.com/)
- Click **Security** on the left
- Scroll to **2-Step Verification**
- Complete the setup

### 2. Create App Password
- Return to **Security** in Google Account
- Scroll to **App passwords**
- Select **Mail** and **Windows Computer** (or your device)
- Google generates a 16-character password
- Copy it (ignore spaces)

### 3. Add GitHub Secrets
In your repository:
- `EMAIL_SERVER` = `smtp.gmail.com`
- `EMAIL_PORT` = `587`
- `EMAIL_USER` = `your-gmail@gmail.com`
- `EMAIL_PASSWORD` = (the 16-char app password from step 2)
- `EMAIL_TO` = `your-personal-email@gmail.com` (can be the same)

---

## 📧 Outlook Setup (Step-by-Step)

### 1. Create App Password
- Go to [Microsoft Account](https://account.microsoft.com/)
- Click **Security** on the left  
- Select **App passwords**
- Generate a new password for "Mail" and "Windows"
- Copy the password

### 2. Add GitHub Secrets
In your repository:
- `EMAIL_SERVER` = `smtp-mail.outlook.com`
- `EMAIL_PORT` = `587`
- `EMAIL_USER` = `your-outlook@outlook.com`
- `EMAIL_PASSWORD` = (the password from step 1)
- `EMAIL_TO` = `your-personal-email@outlook.com`

---

## ✅ Verification

### Run a Manual Test
1. Go to **Actions** tab in GitHub
2. Click **Daily Grow Report**
3. Click **Run workflow** (top right)
4. Select branch: `main`
5. Click **Run workflow**

### Check the Results
- **In GitHub:** The workflow run should complete in ~30 seconds
  - Click the run to see logs
  - Look for: `✅ Report generated successfully` and `Report OK: Week X`

- **In Your Email:**
  - Check inbox and spam folder
  - Should arrive within 2 minutes
  - Contains full HTML report with grow photo

### Troubleshooting

**No email received after test?**
- Check GitHub Actions logs for errors
- Verify all 6 secrets are set (don't leave any blank)
- Confirm RDWC_HOST and RDWC_PORT are correct
- Ensure your email provider allows SMTP access
- For Gmail: Confirm you used an App Password (not regular password)

**Report says "No camera available"?**
- That's OK! It still generates the text report
- Camera is optional; ensures report still works if camera fails

**"Sensors offline" in report?**
- Pi might not be reachable from GitHub Actions
- Ensure Pi is on and running rdwc.service
- Check that RDWC_HOST (Pi IP) is correct and accessible from internet

---

## 🚀 What You'll See

### Email Example

```
📊 RDWC Daily Report - RDWC-v4
Week 3 • Day 18 • 2026-06-15 07:00 UTC

🎥 Current Grow State
[Full color photo of your grow setup]

⚡ System Alerts
✅ All systems normal

📍 Current Status - Where We Are
pH:        6.23 (OK)
           Target: 6.0-6.8
           24h trend: ↗ Rising slowly

EC:        1.34 mS/cm (OK)
           Target: 1.2-1.6
           
Water Temp: 21.5°C (OK)
           Target: 16-24°C

🎯 Week 3 Plan - Where We're Going
Nutrient Targets        Per 10L Nutrients
pH: 6.0 - 6.8           Grow: 15ml
EC: 1.2 mS/cm           Micro: 10ml  
Temp: 20°C              Bloom: 25ml
Phase: Flower
Lights: 12/12

💊 Recent pH Doses (Last 24h)
[Table of doses with timestamps]

⚙️ Hardware Status
Main Pump: Running | Lights: On
Chiller: Idle | E-Stop: Clear
Mode: AUTO | Global Auto: Enabled
Sensors: Online (age: 15s)
```

---

## 📞 Support

**Workflow not running?**
- Check GitHub Actions tab → Workflows
- Look for any error badges
- Click the failed run to see logs

**Questions about schedule?**
- See the cron examples above
- Visit [crontab.guru](https://crontab.guru) to test cron expressions

**Report looks wrong?**
- Manual test: Run workflow manually from GitHub
- Check RDWC API is responding: `http://YOUR-PI-IP:8080/api/settings`
- Verify sensors are online: `http://YOUR-PI-IP:8080/api/sensors`

---

## 🔄 Monitoring

After setup, your reports will arrive daily at your configured time. You can:

- **View past reports** in your email (check archive/all-mail)
- **Change schedule** anytime by editing `.github/workflows/daily-report.yml`
- **Disable reports** by deleting the secret `EMAIL_SERVER` (workflow will skip email step)
- **Re-enable manually** by clicking "Run workflow" in GitHub Actions anytime

---

**That's it! You should start receiving daily reports automatically. 🎉**
