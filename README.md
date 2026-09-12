# 🎓 Placement Stats Automation Telegram Bot & Local Engine

Automate your college placement stats collection with Google Gemini AI, CGPA Master Lookup, Company Fuzzy Matching, and Google Sheets / Excel Sync.

---

## ⚡ Quick Features

1. **AI Message Parser (Gemini 1.5/2.0 Flash)**:
   - Automatically parses raw job notifications and student selection lists.
   - Splits multi-role company announcements into separate rows automatically.

2. **Smart Student Auto-Lookup (`CGPA_Master`)**:
   - Auto-completes student **Roll No** if only Name is provided, or **Name** if only Roll No is provided, using 2,584 student records in `CGPA_Master`.

3. **Fuzzy Company & Role Normalization**:
   - Automatically normalizes company names (e.g. `Unify Apps` -> `UnifyApps`, `World wide Technology` -> `WWT`).
   - If role is omitted in student selection, auto-fetches the single registered role for that company from the `Companies` sheet!

4. **Preserves Google Sheets ArrayFormulas**:
   - Leaves `CGPA`, `Stipend`, `CTC`, `Base`, `Category`, `Branch`, and `Count` blank in `Students` sheet so Google Sheets `MAP` / `XLOOKUP` ArrayFormulas populate automatically without breaking.

---

## 🛠️ How to Run Locally (Instant Test)

You can run and test the engine directly from your command line right now without Telegram setup:

```bash
cd C:\Users\DELL\.gemini\antigravity-ide\scratch\placement-stats-bot
python test_cli.py
```

---

## 🤖 Setting Up the Telegram Bot

### Step 1: Get Telegram Bot Token (1 Minute)
1. Open Telegram and search for [@BotFather](https://t.me/BotFather).
2. Send `/newbot` and follow the instructions to choose a bot name and username (e.g., `MyPlacementStatsBot`).
3. Copy the HTTP API token provided by BotFather.

### Step 2: Get Gemini API Key
1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Click **Create API key** and copy your key.

### Step 3: Configure `.env`
Create a `.env` file inside `placement-stats-bot/` (or edit `.env.example`):
```env
TELEGRAM_BOT_TOKEN="your_bot_token_from_botfather"
GEMINI_API_KEY="your_gemini_api_key"
```

### Step 4: Run Telegram Bot
```bash
python bot.py
```
Now forward any company or student placement message to your Telegram bot!

---

## 📊 Live Google Sheets Sync Setup (Optional)

If you want to sync directly to live Google Sheets instead of local Excel:
1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Enable **Google Sheets API** and create a **Service Account**.
3. Download the service account JSON key file as `credentials.json` inside `placement-stats-bot/`.
4. Share your Google Sheet with the Service Account email (with **Editor** permission).
5. Set `GOOGLE_SHEET_ID_OR_URL` in `.env`.
