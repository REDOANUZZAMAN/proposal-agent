"""Admin CLI.  python3 admin.py update-geo   |   python3 admin.py make-admin <name> [password]   |   python3 admin.py invite <label> [max_uses=1] [days=30]"""
import secrets, sys, time

import server


def update_geo():
    import urllib.request
    rows = urllib.request.urlopen("https://ftp.apnic.net/stats/apnic/delegated-apnic-latest", timeout=120).read().decode().splitlines()
    out = []
    for r in rows:
        f = r.split("|")
        if len(f) > 6 and f[0] == "apnic" and f[1] == "CN":
            if f[2] == "ipv4":
                import ipaddress
                out.append(f"4 {int(ipaddress.ip_address(f[3]))} {f[4]}")
            elif f[2] == "ipv6":
                out.append(f"6 {f[3]} {f[4]}")
    open(server.os.path.join(server.DATA, "cn_ranges.txt"), "w").write("\n".join(out) + "\n")
    print(len(out), "China ranges written")


def main(a):
    if a[:1] == ["update-geo"]:
        return update_geo()
    if len(a) >= 2 and a[0] == "make-admin":
        name, pw = a[1].lower(), (a[2] if len(a) > 2 else None)
        row = server.db.execute("SELECT 1 FROM users WHERE name=?", (name,)).fetchone()
        gen = pw is None and not row
        pw = pw or secrets.token_urlsafe(12)
        if not row or len(a) > 2:
            salt = secrets.token_bytes(16)
            if row:
                server.db.execute("UPDATE users SET salt=?,hash=? WHERE name=?", (salt, server._hash(pw, salt), name))
            else:
                server.db.execute("INSERT INTO users(name,salt,hash,created) VALUES(?,?,?,?)", (name, salt, server._hash(pw, salt), time.time()))
        server.db.execute("UPDATE users SET is_admin=1, disabled=0 WHERE name=?", (name,))
        print("admin:", name, "| password:", pw if gen or len(a) > 2 else "(unchanged)")
    elif len(a) >= 2 and a[0] == "invite":
        print(server.new_invite(a[1], int(a[2]) if len(a) > 2 else 1, int(a[3]) if len(a) > 3 else 30))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
