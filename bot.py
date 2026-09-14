import logging
import json
import os
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# Ensure UTF-8 stdout encoding on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from ai_extractor import AIExtractor
from sheet_manager import SheetManager
from config import TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, DEFAULT_LOCAL_EXCEL_PATH, GOOGLE_SHEETS_CREDENTIALS_PATH, GOOGLE_SHEET_ID_OR_URL

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

PENDING_PARSES = {}

# ----------------------------------------------------
# Lightweight Health Check Web Server for Render
# ----------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Placement Stats Bot is running 24/7!")

    def log_message(self, format, *args):
        return  # Silence routine HTTP access logs

def start_health_check_server():
    port = int(os.environ.get("PORT", 8080))
    server_address = ('', port)
    httpd = HTTPServer(server_address, HealthCheckHandler)
    print(f"🌐 Health check HTTP server listening on port {port} for Render...")
    httpd.serve_forever()

# Start HTTP server in background thread for Render health checks
threading.Thread(target=start_health_check_server, daemon=True).start()


# ----------------------------------------------------
# Telegram Bot Core
# ----------------------------------------------------
class PlacementBot:
    def __init__(self):
        self.ai_extractor = AIExtractor(GEMINI_API_KEY)
        self.sheet_manager = SheetManager(
            excel_path=DEFAULT_LOCAL_EXCEL_PATH,
            google_sheet_credentials=GOOGLE_SHEETS_CREDENTIALS_PATH,
            google_sheet_url=GOOGLE_SHEET_ID_OR_URL
        )

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        mode_str = "Google Sheets (Live)" if self.sheet_manager.use_google_sheets else "Local Excel"
        await update.message.reply_text(
            f"🎓 **Welcome to Placement Stats Automation Bot!**\nMode: `{mode_str}`\n\n"
            "Send or forward any company announcement or student placement message here.\n"
            "I will classify, extract, lookup student details, and sync directly to your sheet!",
            parse_mode='Markdown'
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        if not text:
            return

        status_msg = await update.message.reply_text("⚡ Processing announcement with Gemini AI...")

        try:
            parsed_result = self.ai_extractor.parse_message(text)
            
            user_id = update.effective_user.id
            PENDING_PARSES[user_id] = parsed_result

            preview_text = f"📋 PLACEMENT DATA PARSED\nType: {parsed_result.message_type}\n\n"

            if parsed_result.companies:
                preview_text += "🏢 Company Records to Add:\n"
                for c in parsed_result.companies:
                    exact_name = self.sheet_manager.company_matcher.get_exact_company_name(c.Company)
                    preview_text += f"• Company: {exact_name}\n  Role: {c.Role}\n  Offer Type: {c.Offer_Type}\n  CTC: {c.CTC_in_LPA or 'N/A'} LPA | Base: {c.Base_in_LPA or 'N/A'} LPA | Stipend: {c.Stipend_in_K or 'N/A'}K\n  CGPA Cutoff: {c.CGPA_criteria or 'None'} | Category: {c.Category}\n\n"

            if parsed_result.students:
                preview_text += "🎓 Student Records to Add:\n"
                for s in parsed_result.students:
                    exact_co = self.sheet_manager.company_matcher.get_exact_company_name(s.Company)
                    enriched = self.sheet_manager.student_lookup.enrich_student_data(s.Roll_No or '', s.Name or '')
                    preview_text += f"• Roll: {enriched['Roll No']} | Name: {enriched['Name']}\n  Company: {exact_co} | Role: {s.Role or 'Auto-fetch'} | Offer: {s.Offer_Type}\n\n"

            sync_target = "Live Google Sheet" if self.sheet_manager.use_google_sheets else "Local Excel"
            preview_text += f"Confirm to append rows to your {sync_target}:"

            keyboard = [
                [
                    InlineKeyboardButton("✅ Confirm & Sync to Sheet", callback_data="confirm_sync"),
                    InlineKeyboardButton("❌ Cancel", callback_data="cancel_sync")
                ]
            ]

            await status_msg.edit_text(preview_text, reply_markup=InlineKeyboardMarkup(keyboard))

        except Exception as e:
            await status_msg.edit_text(f"❌ Error processing message: {str(e)}")

    async def handle_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        if user_id not in PENDING_PARSES:
            await query.edit_message_text("⚠️ No pending parse session found or session expired.")
            return

        if query.data == "cancel_sync":
            del PENDING_PARSES[user_id]
            await query.edit_message_text("❌ Action cancelled. Sheet was not modified.")
            return

        if query.data == "confirm_sync":
            parsed_result = PENDING_PARSES[user_id]
            added_companies = []
            added_students = []

            for c in parsed_result.companies:
                res = self.sheet_manager.append_company_record(c.model_dump())
                added_companies.append(res)

            for s in parsed_result.students:
                res = self.sheet_manager.append_student_record(s.model_dump())
                added_students.append(res)

            del PENDING_PARSES[user_id]

            target_name = "Live Google Sheet" if self.sheet_manager.use_google_sheets else "Local Excel"
            success_text = f"🎉 SUCCESS! Synced to {target_name}!\n\n"
            if added_companies:
                success_text += f"• Added {len(added_companies)} Company record(s).\n"
            if added_students:
                success_text += f"• Added {len(added_students)} Student record(s) (ArrayFormulas auto-filled CGPA, CTC, Stipend, Branch!).\n"

            await query.edit_message_text(success_text)

def main():
    if not TELEGRAM_BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN environment variable is not set!")
        return

    bot = PlacementBot()
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", bot.start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    app.add_handler(CallbackQueryHandler(bot.handle_button))

    mode = "Google Sheets (Live)" if bot.sheet_manager.use_google_sheets else "Local Excel"
    print(f"🤖 Telegram Placement Stats Bot running... [Mode: {mode}]")
    app.run_polling()

if __name__ == "__main__":
    main()
