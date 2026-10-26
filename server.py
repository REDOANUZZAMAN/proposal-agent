"""Web UI + JSON API (stdlib http.server). Run: python server.py [port]"""
import base64, hashlib, hmac, html, io, json, os, re, secrets, sqlite3, subprocess, sys, tempfile, time, zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import agent, docx_out

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(ROOT, "static")
DATA = os.path.join(ROOT, "data")
MAX_REPORT = 3_000_000            # bytes of JSON per saved report
os.makedirs(DATA, exist_ok=True)


def _secret():
    f = os.path.join(DATA, "secret")
    if not os.path.exists(f):
        with open(os.open(f, os.O_WRONLY | os.O_CREAT, 0o600), "wb") as o:
            o.write(secrets.token_bytes(32))
    return open(f, "rb").read()


SECRET = _secret()
db = sqlite3.connect(os.path.join(DATA, "app.db"), check_same_thread=False, isolation_level=None)
db.executescript("""CREATE TABLE IF NOT EXISTS users(name TEXT PRIMARY KEY, salt BLOB, hash BLOB);
CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY, user TEXT, title TEXT, data TEXT, updated REAL);
CREATE INDEX IF NOT EXISTS r_user ON reports(user, updated)""")


def _env(k):
    from llm import _env as e
    return e(k)


def _hash(pw, salt):
    return hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1)


def make_token(user):
    body = base64.urlsafe_b64encode(f"{user}|{int(time.time()) + 30 * 86400}".encode()).decode()
    return body + "." + hmac.new(SECRET, body.encode(), "sha256").hexdigest()


def read_token(tok):
    try:
        body, sig = tok.rsplit(".", 1)
        if not hmac.compare_digest(sig, hmac.new(SECRET, body.encode(), "sha256").hexdigest()):
            return None
        user, exp = base64.urlsafe_b64decode(body).decode().rsplit("|", 1)
        return user if int(exp) > time.time() else None
    except Exception:
        return None


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

    def user(self):
        for part in self.headers.get("Cookie", "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "pa":
                return read_token(v)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/me":
            return self._send(200, {"user": self.user()})
        if path.startswith("/api/") and path != "/api/sample" and not self.user():
            return self._send(401, {"error": "login required"})
        if path == "/api/reports":
            rows = db.execute("SELECT id,title,updated,data FROM reports WHERE user=? ORDER BY updated DESC", (self.user(),)).fetchall()
            out = []
            for i, t, u, d in rows:
                c = json.loads(d).get("chapters", [])
                out.append({"id": i, "title": t, "updated": u, "chapters": len(c), "written": sum(1 for x in c if x.get("text", "").strip()),
                            "chars": sum(len(x.get("text", "")) for x in c)})
            return self._send(200, {"reports": out})
        m = re.fullmatch(r"/api/reports/(\d+)", path)
        if m:
            r = db.execute("SELECT data FROM reports WHERE id=? AND user=?", (int(m[1]), self.user())).fetchone()
            return self._send(200, json.loads(r[0])) if r else self._send(404, {"error": "not found"})
        if path in ("/", "/index.html"):
            return self._send(200, open(os.path.join(STATIC, "index.html"), "rb").read(), "text/html")
        if path == "/api/sample":
            d = os.path.join(os.path.dirname(__file__), "examples")
            return self._send(200, {"guide": open(d + "/sample_guide.txt", encoding="utf-8").read(),
                                    "idea": open(d + "/sample_idea.txt", encoding="utf-8").read()})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            if u.path == "/api/extract":
                return self._send(200, {"text": extract_text(parse_qs(u.query).get("name", [""])[0], raw)})
            j = json.loads(raw or b"{}")
            if u.path in ("/api/register", "/api/login"):
                return self.auth(u.path[5:], j)
            if u.path == "/api/logout":
                return self._send(200, {"ok": 1}, extra={"Set-Cookie": "pa=; Path=/; Max-Age=0"})
            if not self.user():                      # every other endpoint spends LLM credit or reads private data
                return self._send(401, {"error": "login required"})
            if u.path == "/api/reports":
                return self.save_report(j)
            if u.path == "/api/reports/delete":
                db.execute("DELETE FROM reports WHERE id=? AND user=?", (int(j["id"]), self.user()))
                return self._send(200, {"ok": 1})
            if u.path == "/api/outline":
                return self._send(200, agent.outline(j["guide"], j.get("idea", "")))
            if u.path == "/api/chapter":
                return self._send(200, {"text": agent.chapter(j["guide"], j.get("idea", ""), j["chapter"], j.get("previous", []), j.get("budget"))})
            if u.path == "/api/revise":
                return self._send(200, {"text": agent.revise(j["guide"], j.get("idea", ""), j["chapter"], j["instruction"], j.get("budget"))})
            if u.path == "/api/check":
                return self._send(200, agent.check(j["guide"], j["chapters"]))
            if u.path == "/api/export":
                return self._send(200, docx_out.build(j.get("title") or "项目申报书", j["chapters"]),
                                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                  {"Content-Disposition": "attachment; filename=proposal.docx"})
            self._send(404, {"error": "not found"})
        except Exception as e:                       # surface the reason to the UI instead of a blank 500
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def auth(self, kind, j):
        name, pw = str(j.get("user", "")).strip(), str(j.get("password", ""))
        if not re.fullmatch(r"[\w.@-]{3,40}", name) or len(pw) < 8:
            return self._send(400, {"error": "Username: 3-40 letters/digits. Password: at least 8 characters."})
        row = db.execute("SELECT salt,hash FROM users WHERE name=?", (name,)).fetchone()
        if kind == "register":
            inv = _env("INVITE_CODE")
            if not inv or not hmac.compare_digest(str(j.get("invite", "")), inv):
                return self._send(403, {"error": "Wrong invite code."})
            if row:
                return self._send(409, {"error": "That username is taken."})
            salt = secrets.token_bytes(16)
            db.execute("INSERT INTO users VALUES(?,?,?)", (name, salt, _hash(pw, salt)))
        elif not row or not hmac.compare_digest(_hash(pw, row[0]), row[1]):
            time.sleep(0.6)                          # shortcut: slows guessing only; add real rate-limits if this goes public
            return self._send(401, {"error": "Wrong username or password."})
        self._send(200, {"user": name}, extra={"Set-Cookie": f"pa={make_token(name)}; Path=/; HttpOnly; SameSite=Lax; Max-Age={30 * 86400}"})

    def save_report(self, j):
        data = json.dumps(j["data"], ensure_ascii=False)
        if len(data) > MAX_REPORT:
            return self._send(413, {"error": "Report too large."})
        title = (j.get("title") or "").strip()[:120] or "未命名 / Untitled"
        rid = j.get("id")
        if rid and db.execute("UPDATE reports SET title=?,data=?,updated=? WHERE id=? AND user=?", (title, data, time.time(), int(rid), self.user())).rowcount:
            return self._send(200, {"id": int(rid)})
        rid = db.execute("INSERT INTO reports(user,title,data,updated) VALUES(?,?,?,?)", (self.user(), title, data, time.time())).lastrowid
        self._send(200, {"id": rid})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8100
    print(f"http://localhost:{port}")
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
