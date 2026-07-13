import http.server
import json
import os
import sys
import re
import subprocess
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

# Ensure imports resolve correctly from the project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.orchestrator_agent import get_agent
from tools.db import TABLE_BOOKS, TABLE_MEMBERS, TABLE_RESERVATIONS, TABLE_HISTORY

PORT = 8000
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

# Thinking tags regex to clean Bedrock reasoning outputs
_THINKING_TAG_RE = re.compile(r"<thinking>.*?</thinking>\s*", re.DOTALL | re.IGNORECASE)

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            if obj % 1 == 0:
                return int(obj)
            return float(obj)
        return super().default(obj)

def clean_response(text: str) -> str:
    return _THINKING_TAG_RE.sub("", str(text)).strip()

def scan_table_safe(table):
    try:
        response = table.scan()
        return response.get("Items", [])
    except Exception as e:
        print(f"[ERROR] Scanning table {table.name}: {e}")
        return []

class LibraryAgentAPIHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Override to suppress standard HTTP logging to keep console clean
        pass

    def send_json_response(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data, cls=DecimalEncoder).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        # REST API Routes
        if path == "/api/books":
            books = scan_table_safe(TABLE_BOOKS)
            # Sort books by book_id
            books = sorted(books, key=lambda x: x.get("book_id", ""))
            self.send_json_response(books)
            return
        elif path == "/api/members":
            members = scan_table_safe(TABLE_MEMBERS)
            members = sorted(members, key=lambda x: x.get("member_id", ""))
            self.send_json_response(members)
            return
        elif path == "/api/reservations":
            reservations = scan_table_safe(TABLE_RESERVATIONS)
            reservations = sorted(reservations, key=lambda x: x.get("reservation_id", ""))
            self.send_json_response(reservations)
            return
        elif path == "/api/history":
            history = scan_table_safe(TABLE_HISTORY)
            self.send_json_response(history)
            return

        # Static File Server
        if path == "/":
            path = "/index.html"
        
        # Sanitize path to prevent directory traversal
        filename = os.path.basename(path)
        file_path = os.path.join(WEB_DIR, filename)

        if os.path.exists(file_path) and os.path.isfile(file_path):
            content_type = "text/plain"
            if file_path.endswith(".html"):
                content_type = "text/html"
            elif file_path.endswith(".css"):
                content_type = "text/css"
            elif file_path.endswith(".js"):
                content_type = "application/javascript"
            elif file_path.endswith(".png"):
                content_type = "image/png"
            elif file_path.endswith(".ico"):
                content_type = "image/x-icon"

            try:
                with open(file_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-type", content_type)
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Internal server error: {e}".encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def do_POST(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        # Read JSON body
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)
        try:
            body = json.loads(post_data.decode("utf-8")) if post_data else {}
        except Exception as e:
            self.send_json_response({"error": f"Invalid JSON body: {e}"}, 400)
            return

        if path == "/api/chat":
            prompt = body.get("prompt", "").strip()
            mode = body.get("mode", "sequential").strip()
            reset = body.get("reset", False)

            if not prompt and not reset:
                self.send_json_response({"error": "Prompt cannot be empty"}, 400)
                return

            try:
                # Handle reset chat session request
                if reset:
                    import agents.sequential_agent as sa
                    import agents.parallel_agent as pa
                    sa._sequential_agent_instance = None
                    pa._parallel_agent_instance = None
                    print("[INFO] Recreated agent instances (session reset)")
                    self.send_json_response({"message": "Session reset successful"})
                    return

                # Get Orchestrator agent
                agent = get_agent(mode)
                response = agent(prompt)
                clean_res = clean_response(response)

                self.send_json_response({
                    "response": clean_res,
                    "mode": mode
                })
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.send_json_response({"error": str(e)}, 500)

        elif path == "/api/seed":
            try:
                print("[INFO] Running DynamoDB table initialization...")
                # Run the seeding script as a subprocess
                result = subprocess.run(
                    [sys.executable, os.path.join("deployment", "init_dynamodb.py")],
                    capture_output=True,
                    text=True,
                    check=True
                )
                print("[INFO] Seeding output:", result.stdout)
                self.send_json_response({
                    "success": True,
                    "output": result.stdout
                })
            except Exception as e:
                self.send_json_response({
                    "success": False,
                    "error": str(e)
                }, 500)
        else:
            self.send_json_response({"error": "Endpoint not found"}, 404)

def run_server():
    # Make sure static directory exists
    if not os.path.exists(WEB_DIR):
        os.makedirs(WEB_DIR)

    server_address = ("", PORT)
    httpd = http.server.HTTPServer(server_address, LibraryAgentAPIHandler)
    print("=" * 60)
    print(f"  Library Reservation System - Web Server")
    print(f"  Running locally at: http://localhost:{PORT}")
    print(f"  Serving static files from: {WEB_DIR}")
    print("=" * 60)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping web server...")
        httpd.server_close()

if __name__ == "__main__":
    run_server()
