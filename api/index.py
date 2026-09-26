import os
import sys
import json
import asyncio
from http.server import BaseHTTPRequestHandler

# Add root directory to python path
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from telegram import Update
from bot import PlacementBot, create_application

bot_instance = PlacementBot()
ptb_app = create_application(bot_instance)

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        mode_str = "Google Sheets (Live)" if bot_instance.sheet_manager.use_google_sheets else "Local Excel"
        resp = {
            "status": "online",
            "service": "Placement Stats Telegram Bot Webhook",
            "platform": "Vercel Serverless",
            "sheet_mode": mode_str
        }
        self.wfile.write(json.dumps(resp).encode('utf-8'))

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)

        try:
            update_data = json.loads(post_data.decode('utf-8'))

            async def process_update():
                if not getattr(ptb_app, '_initialized', False):
                    await ptb_app.initialize()
                update = Update.de_json(update_data, ptb_app.bot)
                await ptb_app.process_update(update)

            asyncio.run(process_update())

            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"OK")
        except Exception as e:
            print("Error handling Telegram webhook update:", e)
            # Return HTTP 200 so Telegram does not repeatedly retry failed updates
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"OK")
