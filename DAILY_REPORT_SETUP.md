# Daily Grow Report Email Setup

## Overview
The daily workflow has been replaced from "Slow Tests" (which was failing) to a **Daily Grow Progress Report** that sends you a beautiful HTML email every morning with:

✅ Current week, phase, and light cycle  
✅ Real-time sensor readings (pH, EC, temperature)  
✅ This week's nutrient targets  
✅ Last 24 hours of dosing activity  
✅ System hardware status  

## Setup Required

You need to configure 6 GitHub secrets to enable the email reports. The workflow will run daily at **07:00 UTC** (adjust the cron schedule in `.github/workflows/ci-slow.yml` if needed).

### Step 1: Configure GitHub Secrets

Go to your repository settings: **Settings** → **Secrets and variables** → **Actions**

Add these secrets:

#### 1. **RDWC_HOST** (required)
- **Value:** IP address of your Raspberry Pi  
- **Example:** `192.168.88.55`

#### 2. **RDWC_PORT** (required)
- **Value:** Port where RDWC API is running  
- **Example:** `8080`

#### 3. **EMAIL_SERVER** (required)
- **Value:** SMTP server address  
- **Examples:**
  - Gmail: `smtp.gmail.com`
  - Outlook: `smtp-mail.outlook.com`
  - Generic: `mail.your-domain.com`

#### 4. **EMAIL_PORT** (required)
- **Value:** SMTP port (usually 587 for TLS)  
- **Examples:** `587` or `465`

#### 5. **EMAIL_USER** (required)
- **Value:** Your email address (used for authentication)  
- **Example:** `your-email@gmail.com`

#### 6. **EMAIL_PASSWORD** (required)
- **Value:** Email password or app-specific password  
- **⚠️ Important:** 
  - For Gmail: Use an [App Password](https://support.google.com/accounts/answer/185833), not your regular password
  - For other providers: Check their documentation

#### 7. **EMAIL_FROM** (optional, defaults to EMAIL_USER)
- **Value:** Display name for "From" field  
- **Example:** `RDWC System <grow@example.com>`

#### 8. **EMAIL_TO** (required)
- **Value:** Recipient email address  
- **Example:** `yourname@gmail.com`

### Step 2: Adjust Schedule (Optional)

The report runs daily at **07:00 UTC**. To change:

Edit `.github/workflows/ci-slow.yml` line 8:

```yaml
on:
  schedule:
    - cron: '0 7 * * *'  # Change first number for minutes, second for hours (UTC)
```

**Examples:**
- `0 6 * * *` = 06:00 UTC (1 hour earlier)
- `30 7 * * *` = 07:30 UTC (30 mins later)
- `0 22 * * *` = 22:00 UTC (10 PM)

### Step 3: Test the Workflow

1. Go to your repository: **Actions** tab
2. Select **Daily Grow Report** workflow
3. Click **Run workflow** → **Run workflow** button
4. Wait ~30 seconds and check your email

You should receive a formatted HTML report like this:

```
📊 Current Phase: Flower
💡 Light Cycle: 12/12
🌡️ Water Temp: 21.3°C
🧪 pH: 5.62
📈 EC: 0.39 mS/cm
✅ Auto-Dosing: ON

📋 This Week's Targets
- pH: 6.0 - 6.0
- EC: 1.2 mS/cm
- Temp: 20°C
- Grow: 0/10L, Micro: 10/10L, Bloom: 20/10L

💊 Recent pH Doses (Last 24h)
[Dose history...]

🧪 Recent EC Doses (Last 24h)
[Dose history...]

⚙️ System Status
- Main Pump: ✅ ON
- Lights: ✅ ON
- Chiller: ❌ IDLE
```

## Troubleshooting

### Workflow runs but no email received:
1. Check GitHub Actions logs for errors
2. Verify email credentials are correct (especially for Gmail, use App Password)
3. Check your email spam folder
4. Verify RDWC_HOST and RDWC_PORT are correct

### "Connection refused" error:
- Ensure your Pi is on and RDWC service is running
- Test manually: `curl http://YOUR_PI_IP:8080/api/sensors`

### "Authentication failed" error:
- Verify EMAIL_USER and EMAIL_PASSWORD are correct
- For Gmail: Confirm you're using an [App Password](https://support.google.com/accounts/answer/185833)
- For other providers: Check SMTP credentials

### Want to disable reports?
Disable the workflow in GitHub Actions tab (or delete the schedule line from `.github/workflows/ci-slow.yml`)

## What's Reported

Each email includes:

1. **Current Status**
   - Growth phase, light cycle, week number, days elapsed

2. **Real-time Readings**
   - Water temperature, pH, EC (nutrients)

3. **This Week's Targets**
   - pH range, EC target, temperature target, nutrient mix ratios

4. **Dosing History**
   - Last 3 pH doses with timestamps, volumes, and effect
   - Last 3 EC doses with mix ratios and EC change

5. **System Health**
   - Main pump, lights, chiller status
   - Mode (auto/manual), E-STOP state

No more failed test notifications—only valuable grow insights! 🌱
