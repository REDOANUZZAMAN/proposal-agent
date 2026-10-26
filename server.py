"""Web UI + JSON API (stdlib http.server). Run: python server.py [port]"""
import html, io, json, os, re, subprocess, sys, tempfile, zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import agent, docx_out

STATIC = os.path.join(os.path.dirname(__file__), "static")


def extract_text(name, data):
    name = name.lower()
    if name.endswith(".docx"):
        xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")
        paras = re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S)
        return "\n".join(html.unescape("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p))) for p in paras)
    if name.endswith(".pdf"):
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(data); f.flush()
            return subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True, check=True).stdout
    return data.decode("utf-8", "replace")        # shortcut: .txt/.md only otherwise


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json", extra=None):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text") or ctype == "application/json" else ""))
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._send(200, open(os.path.join(STATIC, "index.html"), "rb").read(), "text/html")
        self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            if u.path == "/api/extract":
                return self._send(200, {"text": extract_text(parse_qs(u.query).get("name", [""])[0], raw)})
            j = json.loads(raw or b"{}")
            if u.path == "/api/outline":
                return self._send(200, agent.outline(j["guide"], j.get("idea", "")))
            if u.path == "/api/chapter":
                return self._send(200, {"text": agent.chapter(j["guide"], j.get("idea", ""), j["chapter"], j.get("previous", []))})
            if u.path == "/api/check":
                return self._send(200, agent.check(j["guide"], j["chapters"]))
            if u.path == "/api/export":
                return self._send(200, docx_out.build(j.get("title") or "项目申报书", j["chapters"]),
                                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                  {"Content-Disposition": "attachment; filename=proposal.docx"})
            self._send(404, {"error": "not found"})
        except Exception as e:                       # surface the reason to the UI instead of a blank 500
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8100
    print(f"http://localhost:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
