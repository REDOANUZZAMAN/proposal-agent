# proposal-agent · 项目申报书生成智能体

**Live demo (invite-only):** https://proposal.rmaikr.top/

Give it a funding guide (申报指南) and your project idea; it writes the proposal chapter by chapter.

0. **Log in** (accounts; register needs the `INVITE_CODE` from `.env`). Every report is saved to your account and can be reopened from **History**.
1. Paste or upload the guide (.txt/.md/.docx/.pdf; PDF needs `pdftotext`).
2. **Plan chapters**: the LLM reads the guide and proposes the chapter list. Each chapter has its own **editable prompt** and the guide rules it must meet.
3. **Generate** one chapter or all (each chapter sees the earlier ones, so the text stays consistent). Missing facts become `[待补充: …]` instead of invented numbers.
4. **Check**: every requirement in the guide is marked ok / partial / missing, with the place in the draft. The length is counted in code, not by the model.
5. **Export** to .docx or .pdf (the PDF is made from the same Word file with LibreOffice, so it needs `soffice` on the server).

**Rewrite a selection.** In *Write chapters → Text (edit directly)*, select some text: a small card asks what to change, and only that passage is rewritten (everything around it stays byte-for-byte the same; *Undo last change* restores it).

**Auto mode** (button on the Input tab) does steps 2-4 and the export page in one click: plan, write all chapters (each gets a length budget from the guide's word limit), check, then jump to *Preview & Export*. The UI has a built-in 中文 / EN switch.

Run (Python 3.10+, no pip packages):
```
cp .env.example .env   # fill LLM_BASE_URL, LLM_API_KEY, LLM_MODEL (any OpenAI-compatible API) and INVITE_CODE
python server.py 8100  # open http://localhost:8100
python -c "import sys;sys.path.insert(0,'tests');import test_basic as t;t.test_docx_roundtrip();t.test_txt_extract();t.test_token_roundtrip_and_tamper();t.test_password_hash_differs_by_salt()"
```
`examples/sample_guide.txt` is a made-up demo guide, not a real notice.
Limits: the model can still write weak or generic text, so a human must read and edit the draft; rate limits are retried 5 times.
Accounts and reports live in `data/` (SQLite, git-ignored). Run it behind an HTTPS reverse proxy in production (the live demo uses Traefik + Cloudflare). Behind a proxy the server reads the visitor's address from `CF-Connecting-IP` / `X-Forwarded-For` only when the connection comes from a private address, and marks the login cookie `Secure` when `X-Forwarded-Proto` is `https`.

**Admin.** `python3 admin.py make-admin <email> [password]` creates (or promotes) an admin; an admin sees an **Admin** tab with usage stats, user management (disable / enable / reset password / make admin / delete) and invite codes (create with a label, use limit and expiry; revoke). Admins see usage numbers only, never report contents. `python3 admin.py invite "<label>" [max_uses] [days]` makes an invite from the shell.
**Language.** The UI starts in Chinese for visitors from mainland-China IPs and English otherwise (ranges from APNIC, refreshed with `python3 admin.py update-geo`); a visitor's own 中文/EN choice always wins. Hong Kong, Macau and Taiwan count as non-China.
