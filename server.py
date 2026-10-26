"""Web UI + JSON API (stdlib http.server). Run: python server.py [port]"""
import threading, bisect, base64, hashlib, ipaddress, hmac, html, io, json, os, re, secrets, sqlite3, subprocess, sys, tempfile, time, zipfile
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
class _Res:
    def __init__(self, rows, rowcount, lastrowid):
        self.rows, self.rowcount, self.lastrowid = rows, rowcount, lastrowid

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows

    def __iter__(self):
        return iter(self.rows)


class _DB:
    """One sqlite connection shared by all request threads: every statement runs (and is fully fetched) under a lock."""

    def __init__(self, path):
        self.c, self.lock = sqlite3.connect(path, check_same_thread=False, isolation_level=None), threading.Lock()

    def execute(self, sql, args=()):
        with self.lock:
            cur = self.c.execute(sql, args)
            return _Res(cur.fetchall(), cur.rowcount, cur.lastrowid)

    def executescript(self, sql):
        with self.lock:
            self.c.executescript(sql)


db = _DB(os.path.join(DATA, "app.db"))
db.executescript("""CREATE TABLE IF NOT EXISTS users(name TEXT PRIMARY KEY, salt BLOB, hash BLOB);
CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY, user TEXT, title TEXT, data TEXT, updated REAL);
CREATE INDEX IF NOT EXISTS r_user ON reports(user, updated);
CREATE TABLE IF NOT EXISTS invites(code TEXT PRIMARY KEY, label TEXT, max_uses INTEGER, uses INTEGER DEFAULT 0, expires REAL, revoked INTEGER DEFAULT 0, created REAL);
CREATE TABLE IF NOT EXISTS usage(user TEXT, day TEXT, calls INTEGER, PRIMARY KEY(user, day))""")
for _c, _d in [("is_admin", "INTEGER DEFAULT 0"), ("disabled", "INTEGER DEFAULT 0"), ("created", "REAL"), ("last_seen", "REAL"), ("invite", "TEXT")]:
    if _c not in [r[1] for r in db.execute("PRAGMA table_info(users)")]:
        db.execute(f"ALTER TABLE users ADD COLUMN {_c} {_d}")


def _env(k):
    from llm import _env as e
    return e(k)


def load_geo():
    """China IP ranges from APNIC (data/cn_ranges.txt, made by `admin.py update-geo`); no file -> everyone counts as non-China."""
    v4, v6 = [], []
    try:
        for line in open(os.path.join(DATA, "cn_ranges.txt")):
            k, a, b = line.split()
            (v4.append((int(a), int(a) + int(b) - 1)) if k == "4" else v6.append(ipaddress.ip_network(f"{a}/{b}")))
    except OSError:
        pass
    return sorted(v4), v6


GEO = load_geo()


def is_cn(ip):
    try:
        a = ipaddress.ip_address(ip.split("%")[0])
        if a.version == 6 and a.ipv4_mapped:
            a = a.ipv4_mapped
        if a.version == 4:
            i = bisect.bisect_right(GEO[0], (int(a), 2 ** 33)) - 1
            return i >= 0 and GEO[0][i][0] <= int(a) <= GEO[0][i][1]
        return any(a in n for n in GEO[1])
    except ValueError:
        return False


def new_invite(label, max_uses=1, days=30):
    code = secrets.token_urlsafe(9)
    db.execute("INSERT INTO invites(code,label,max_uses,uses,expires,created) VALUES(?,?,?,0,?,?)",
               (code, label, int(max_uses), time.time() + days * 86400 if days else None, time.time()))
    return code


if not db.execute("SELECT 1 FROM invites").fetchone() and _env("INVITE_CODE"):   # one-time import of the old .env code
    db.execute("INSERT INTO invites(code,label,max_uses,uses,created) VALUES(?,?,0,0,?)", (_env("INVITE_CODE"), "owner (.env)", time.time()))


def _hash(pw, salt):
    return hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1)


def make_token(user, fp=""):
    body = base64.urlsafe_b64encode(f"{user}|{int(time.time()) + 30 * 86400}|{fp}".encode()).decode()
    return body + "." + hmac.new(SECRET, body.encode(), "sha256").hexdigest()


def read_token(tok):
    """-> (user, fingerprint) or None"""
    try:
        body, sig = tok.rsplit(".", 1)
        if not hmac.compare_digest(sig, hmac.new(SECRET, body.encode(), "sha256").hexdigest()):
            return None
        user, exp, fp = base64.urlsafe_b64decode(body).decode().rsplit("|", 2)
        return (user, fp) if int(exp) > time.time() else None
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
            t = read_token(v) if k == "pa" else None
            if t:
                r = db.execute("SELECT disabled,hash,last_seen FROM users WHERE name=?", (t[0],)).fetchone()
                if r and not r[0] and r[1].hex()[:12] == t[1]:
                    if time.time() - (r[2] or 0) > 60:
                        db.execute("UPDATE users SET last_seen=? WHERE name=?", (time.time(), t[0]))
                    return t[0]

    def is_admin(self):
        u = self.user()
        return bool(u and db.execute("SELECT is_admin FROM users WHERE name=?", (u,)).fetchone()[0])

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/me":
            return self._send(200, {"user": self.user(), "admin": self.is_admin(), "lang": "zh" if is_cn(self.client_address[0]) else "en"})
        if path.startswith("/api/") and path != "/api/sample" and not self.user():
            return self._send(401, {"error": "login required"})
        if path.startswith("/api/admin/"):
            return self._send(200, self.admin_get(path)) if self.is_admin() else self._send(403, {"error": "admin only"})
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
            if u.path.startswith("/api/admin/"):
                return self._send(200, self.admin_post(u.path, j)) if self.is_admin() else self._send(403, {"error": "admin only"})
            if u.path in ("/api/outline", "/api/chapter", "/api/revise", "/api/check"):
                db.execute("INSERT INTO usage VALUES(?,?,1) ON CONFLICT(user,day) DO UPDATE SET calls=calls+1", (self.user(), time.strftime("%Y-%m-%d")))
            if u.path == "/api/reports":
                return self.save_report(j)
            if u.path == "/api/reports/delete":
                db.execute("DELETE FROM reports WHERE id=? AND user=?", (int(j["id"]), self.user()))
                return self._send(200, {"ok": 1})
            if u.path == "/api/outline":
                return self._send(200, agent.outline(j["guide"], j.get("idea", "")))
            if u.path == "/api/chapter":
                return self._send(200, {"text": agent.chapter(j["guide"], j.get("idea", ""), j["chapter"], j.get("previous", []), j.get("budget"), j.get("unit", "chars"))})
            if u.path == "/api/revise":
                return self._send(200, {"text": agent.revise(j["guide"], j.get("idea", ""), j["chapter"], j["instruction"], j.get("budget"), j.get("unit", "chars"))})
            if u.path == "/api/check":
                return self._send(200, agent.check(j["guide"], j["chapters"], j.get("count"), j.get("unit", "chars")))
            if u.path == "/api/export":
                m = j["model"]
                if not isinstance(m, dict) or not isinstance(m.get("chapters"), list) or len(m["chapters"]) > 100:
                    raise ValueError("bad document model")
                return self._send(200, docx_out.build(m), "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                  {"Content-Disposition": "attachment; filename=proposal.docx"})
            self._send(404, {"error": "not found"})
        except Exception as e:                       # surface the reason to the UI instead of a blank 500
            self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def auth(self, kind, j):
        name, pw = str(j.get("user", "")).strip().lower(), str(j.get("password", ""))
        if not re.fullmatch(r"[\w.@-]{3,40}", name) or len(pw) < 8:
            return self._send(400, {"error": "Username: 3-40 letters/digits. Password: at least 8 characters."})
        row = db.execute("SELECT salt,hash,disabled,is_admin FROM users WHERE name=?", (name,)).fetchone()
        if kind == "register":
            code = str(j.get("invite", "")).strip()
            inv = db.execute("SELECT max_uses,uses,expires,revoked FROM invites WHERE code=?", (code,)).fetchone()
            if not inv or inv[3] or (inv[0] and inv[1] >= inv[0]) or (inv[2] and inv[2] < time.time()):
                return self._send(403, {"error": "Wrong or expired invite code."})
            if row:
                return self._send(409, {"error": "That username is taken."})
            salt = secrets.token_bytes(16)
            row = (salt, _hash(pw, salt), 0, 0)
            db.execute("INSERT INTO users(name,salt,hash,created,invite) VALUES(?,?,?,?,?)", (name, salt, row[1], time.time(), code))
            db.execute("UPDATE invites SET uses=uses+1 WHERE code=?", (code,))
        elif not row or not hmac.compare_digest(_hash(pw, row[0]), row[1]):
            time.sleep(0.6)                          # shortcut: slows guessing only; add real rate-limits if this goes public
            return self._send(401, {"error": "Wrong username or password."})
        elif row[2]:
            return self._send(403, {"error": "This account is disabled. Contact the administrator."})
        self._send(200, {"user": name, "admin": bool(row[3])}, extra={"Set-Cookie": f"pa={make_token(name, row[1].hex()[:12])}; Path=/; HttpOnly; SameSite=Lax; Max-Age={30 * 86400}"})

    def admin_get(self, path):
        day = lambda n: time.strftime("%Y-%m-%d", time.gmtime(time.time() - n * 86400))
        if path == "/api/admin/stats":
            q = lambda sql, *a: db.execute(sql, a).fetchone()[0] or 0
            return {"users": q("SELECT COUNT(*) FROM users"), "admins": q("SELECT COUNT(*) FROM users WHERE is_admin=1"),
                    "disabled": q("SELECT COUNT(*) FROM users WHERE disabled=1"), "reports": q("SELECT COUNT(*) FROM reports"),
                    "new7": q("SELECT COUNT(*) FROM users WHERE created>?", time.time() - 7 * 86400),
                    "calls_today": q("SELECT SUM(calls) FROM usage WHERE day=?", day(0)), "calls7": q("SELECT SUM(calls) FROM usage WHERE day>=?", day(6)),
                    "calls_total": q("SELECT SUM(calls) FROM usage"),
                    "daily": [{"day": day(i), "calls": q("SELECT SUM(calls) FROM usage WHERE day=?", day(i))} for i in range(6, -1, -1)]}
        if path == "/api/admin/users":
            rows = db.execute("""SELECT u.name,u.is_admin,u.disabled,u.created,u.last_seen,u.invite,
              (SELECT COUNT(*) FROM reports r WHERE r.user=u.name),
              (SELECT COALESCE(SUM(calls),0) FROM usage g WHERE g.user=u.name),
              (SELECT COALESCE(SUM(calls),0) FROM usage g WHERE g.user=u.name AND g.day>=?)
              FROM users u ORDER BY u.created DESC""", (day(6),)).fetchall()
            return {"users": [dict(zip(("name", "admin", "disabled", "created", "last_seen", "invite", "reports", "calls", "calls7"), r)) for r in rows]}
        if path == "/api/admin/invites":
            rows = db.execute("SELECT code,label,max_uses,uses,expires,revoked,created FROM invites ORDER BY created DESC").fetchall()
            return {"invites": [dict(zip(("code", "label", "max_uses", "uses", "expires", "revoked", "created"), r)) for r in rows]}
        return {"error": "not found"}

    def admin_post(self, path, j):
        me = self.user()
        if path == "/api/admin/invite":
            return {"code": new_invite(str(j.get("label", ""))[:60] or "invite", max(0, int(j.get("max_uses", 1))), max(0, int(j.get("days", 30))))}
        if path == "/api/admin/invite/revoke":
            db.execute("UPDATE invites SET revoked=1 WHERE code=?", (j["code"],))
            return {"ok": 1}
        if path == "/api/admin/user":
            name, act = str(j["name"]), j["action"]
            row = db.execute("SELECT is_admin FROM users WHERE name=?", (name,)).fetchone()
            if not row:
                return {"error": "no such user"}
            if name == me and act in ("disable", "delete", "remove_admin"):
                return {"error": "You cannot do that to your own account."}
            if act == "disable":
                db.execute("UPDATE users SET disabled=1 WHERE name=?", (name,))
            elif act == "enable":
                db.execute("UPDATE users SET disabled=0 WHERE name=?", (name,))
            elif act == "make_admin":
                db.execute("UPDATE users SET is_admin=1 WHERE name=?", (name,))
            elif act == "remove_admin":
                db.execute("UPDATE users SET is_admin=0 WHERE name=?", (name,))
            elif act == "delete":
                db.execute("DELETE FROM reports WHERE user=?", (name,)); db.execute("DELETE FROM usage WHERE user=?", (name,)); db.execute("DELETE FROM users WHERE name=?", (name,))
            elif act == "reset_password":
                pw, salt = secrets.token_urlsafe(9), secrets.token_bytes(16)
                db.execute("UPDATE users SET salt=?,hash=? WHERE name=?", (salt, _hash(pw, salt), name))   # new hash also logs the user out everywhere
                return {"password": pw}
            else:
                return {"error": "unknown action"}
            return {"ok": 1}
        return {"error": "not found"}

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
