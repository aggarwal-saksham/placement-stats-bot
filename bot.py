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

# Start HTTP server in background thread only if deployed on Render
if os.getenv("RENDER"):
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
            
            # 1. Filter Companies: Only keep if (Company + Role) is NOT already present in Companies sheet
            filtered_companies = []
            if parsed_result.companies:
                for c in parsed_result.companies:
                    is_present = self.sheet_manager.company_matcher.is_company_role_present(c.Company, c.Role)
                    if not is_present:
                        # Normalize company name to exact sheet string if already known under another role
                        c.Company = self.sheet_manager.company_matcher.get_exact_company_name(c.Company)
                        filtered_companies.append(c)
                    else:
                        print(f"Company '{c.Company}' with role '{c.Role}' already exists in Companies sheet. Skipping re-addition.")

            parsed_result.companies = filtered_companies

            # 2. Filter Students: Ignore student roll numbers starting with 25/
            filtered_students = []
            if parsed_result.students:
                for s in parsed_result.students:
                    enriched = self.sheet_manager.student_lookup.enrich_student_data(s.Roll_No or '', s.Name or '')
                    roll = enriched.get('Roll No', '').strip().upper()
                    if roll.startswith("25/"):
                        print(f"Filtering out student {enriched.get('Name')} because roll starts with 25/")
                        continue
                    filtered_students.append(s)

            parsed_result.students = filtered_students

            # Adjust message type if companies filtered out
            if not parsed_result.companies and parsed_result.students:
                parsed_result.message_type = "STUDENT_PLACEMENT"
            elif parsed_result.companies and not parsed_result.students:
                parsed_result.message_type = "COMPANY_ANNOUNCEMENT"

            user_id = update.effective_user.id
            PENDING_PARSES[user_id] = parsed_result

            preview_text = f"📋 PLACEMENT DATA PARSED\nType: {parsed_result.message_type}\n\n"

            if parsed_result.companies:
                preview_text += "🏢 New Company Records to Add:\n"
                for c in parsed_result.companies:
                    preview_text += (
                        f"• Company: {c.Company}\n"
                        f"  Role: {c.Role or 'N/A'}\n"
                        f"  Offer Type: {c.Offer_Type}\n"
                        f"  CTC: {c.CTC_in_LPA or 'N/A'} LPA | Base: {c.Base_in_LPA or 'N/A'} LPA | Stipend: {c.Stipend_in_K or 'N/A'}K\n"
                        f"  CGPA Cutoff: {c.CGPA_criteria}\n"
                        f"  Category: {c.Category}\n"
                    )
                    if c.Comments:
                        preview_text += f"  Comments: {c.Comments}\n"
                    preview_text += "\n"

            if parsed_result.students:
                preview_text += "🎓 Student Records to Add:\n"
                for s in parsed_result.students:
                    exact_co = self.sheet_manager.company_matcher.get_exact_company_name(s.Company)
                    
                    # Role Fallback preview: Auto-fetch from live Companies sheet if omitted
                    role_preview = s.Role
                    if not role_preview or str(role_preview).lower() in ['none', 'null', 'nan', 'auto-fetch', '']:
                        roles = self.sheet_manager.company_matcher.find_roles_for_company(exact_co)
                        role_preview = roles[0] if roles else "Unstated"

                    enriched = self.sheet_manager.student_lookup.enrich_student_data(s.Roll_No or '', s.Name or '')
                    preview_text += f"• Roll: {enriched['Roll No']} | Name: {enriched['Name']}\n  Company: {exact_co} | Role: {role_preview} | Offer: {s.Offer_Type}\n\n"

            if not parsed_result.companies and not parsed_result.students:
                await status_msg.edit_text("ℹ️ No new records found or all records were already present / filtered out.")
                return

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
            # 1. Check /tmp persistence
            tmp_path = f"/tmp/pending_{user_id}.json"
            if os.path.exists(tmp_path):
                try:
                    with open(tmp_path, "r", encoding="utf-8") as f:
                        from ai_extractor import PlacementParseResult
                        PENDING_PARSES[user_id] = PlacementParseResult.model_validate_json(f.read())
                except Exception:
                    pass

        if user_id not in PENDING_PARSES:
            # 2. Re-parse from reply_to_message text if container restarted
            if query.message and query.message.reply_to_message and query.message.reply_to_message.text:
                orig_text = query.message.reply_to_message.text
                try:
                    self.sheet_manager.refresh_matchers()
                    reparsed = self.ai_extractor.parse_message(orig_text)
                    filtered_companies = []
                    if reparsed.companies:
                        for c in reparsed.companies:
                            if not self.sheet_manager.company_matcher.is_company_role_present(c.Company, c.Role):
                                c.Company = self.sheet_manager.company_matcher.get_exact_company_name(c.Company)
                                filtered_companies.append(c)
                    reparsed.companies = filtered_companies

                    filtered_students = []
                    if reparsed.students:
                        for s in reparsed.students:
                            enriched = self.sheet_manager.student_lookup.enrich_student_data(s.Roll_No or '', s.Name or '')
                            if not enriched.get('Roll No', '').strip().upper().startswith("25/"):
                                filtered_students.append(s)
                    reparsed.students = filtered_students
                    PENDING_PARSES[user_id] = reparsed
                except Exception as e:
                    print("Error re-parsing on button callback:", e)

        if user_id not in PENDING_PARSES:
            await query.edit_message_text("⚠️ No pending parse session found or session expired. Please resend the message.")
            return

        if query.data == "cancel_sync":
            PENDING_PARSES.pop(user_id, None)
            try:
                os.remove(f"/tmp/pending_{user_id}.json")
            except Exception:
                pass
            await query.edit_message_text("❌ Action cancelled. Sheet was not modified.")
            return

        if query.data == "confirm_sync":
            parsed_result = PENDING_PARSES[user_id]
            added_companies = []
            added_students = []

            # Only append to Companies sheet if company is NEW (batch operation)
            if parsed_result.companies:
                added_companies = self.sheet_manager.append_company_records(
                    [c.model_dump() for c in parsed_result.companies]
                )

            # Append to Students sheet if student records exist (batch operation)
            if parsed_result.students:
                added_students = self.sheet_manager.append_student_records(
                    [s.model_dump() for s in parsed_result.students]
                )

            PENDING_PARSES.pop(user_id, None)
            try:
                os.remove(f"/tmp/pending_{user_id}.json")
            except Exception:
                pass

            target_name = "Live Google Sheet" if self.sheet_manager.use_google_sheets else "Local Excel"
            success_text = f"🎉 SUCCESS! Synced to {target_name}!\n\n"
            if added_companies:
                success_text += f"• Added {len(added_companies)} Company record(s) to Companies sheet.\n"
            if added_students:
                success_text += f"• Added {len(added_students)} Student record(s) to Students sheet (ArrayFormulas auto-filled CGPA, CTC, Stipend, Branch!).\n"

            await query.edit_message_text(success_text)

def create_application(bot: PlacementBot = None):
    if bot is None:
        bot = PlacementBot()
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", bot.start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    app.add_handler(CallbackQueryHandler(bot.handle_button))
    return app

def main():
    if not TELEGRAM_BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN environment variable is not set!")
        return

    bot = PlacementBot()
    app = create_application(bot)

    mode = "Google Sheets (Live)" if bot.sheet_manager.use_google_sheets else "Local Excel"
    print(f"🤖 Telegram Placement Stats Bot running... [Mode: {mode}]")
    app.run_polling()

if __name__ == "__main__":
    main()
