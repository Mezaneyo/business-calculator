import html
import traceback

try:
    from app import app
except Exception:
    err = html.escape(traceback.format_exc())
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Show(BaseHTTPRequestHandler):
        def do_GET(self):
            body = ("<h3>Startup error</h3><pre style='white-space:pre-wrap'>" + err + "</pre>").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

    HTTPServer(("127.0.0.1", 5000), Show).serve_forever()
else:
    app.run(host="127.0.0.1", port=5000, debug=False)
