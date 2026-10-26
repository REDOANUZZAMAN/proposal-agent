# proposal-agent · 项目申报书生成智能体

Give it a funding guide (申报指南) and your project idea; it writes the proposal chapter by chapter.

1. Paste or upload the guide (.txt/.md/.docx/.pdf; PDF needs `pdftotext`).
2. **Plan chapters**: the LLM reads the guide and proposes the chapter list. Each chapter has its own **editable prompt** and the guide rules it must meet.
3. **Generate** one chapter or all (each chapter sees the earlier ones, so the text stays consistent). Missing facts become `[待补充: …]` instead of invented numbers.
4. **Check**: every requirement in the guide is marked ok / partial / missing, with the place in the draft. The length is counted in code, not by the model.
5. **Export** to .docx.

Run (Python 3.10+, no pip packages):
```
cp .env.example .env   # fill LLM_BASE_URL, LLM_API_KEY, LLM_MODEL (any OpenAI-compatible API)
python server.py 8100  # open http://localhost:8100
python -c "import sys;sys.path.insert(0,'tests');import test_basic as t;t.test_docx_roundtrip();t.test_txt_extract()"
```
`examples/sample_guide.txt` is a made-up demo guide, not a real notice.
Limits: the model can still write weak or generic text, so a human must read and edit the draft; rate limits are retried 5 times.
