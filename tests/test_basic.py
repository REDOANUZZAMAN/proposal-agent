import os, sys, zipfile, io
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import docx_out
from server import extract_text


def _model():
    return {"lang": "zh", "label": "项目申报书", "title": "T <&>", "contents": "目　录", "sign_title": "签字盖章页",
            "sign": ["项目负责人（签字）：{u}　日期：{u}"], "cover": [["项目名称", "T <&>"], ["申报单位", "某大学"]],
            "chapters": [{"title": "一、背景", "blocks": [{"k": "p", "t": "第一段"}, {"k": "h2", "t": "小节"}, {"k": "p", "t": "第二段 <&>\x0b"}]}]}


def test_docx_standard_layout():
    z = zipfile.ZipFile(io.BytesIO(docx_out.build(_model())))
    assert z.testzip() is None
    doc, sty = z.read("word/document.xml").decode(), z.read("word/styles.xml").decode()
    assert 'w:w="11906" w:h="16838"' in doc and "<w:titlePg/>" in doc            # A4, no number on the cover
    assert "宋体" in sty and 'w:line="360"' in sty and 'w:firstLineChars="200"' in sty    # 小四 body, 1.5 spacing, 2-char indent
    assert doc.count('w:val="Heading1"') == 1 and doc.count('w:val="Heading2"') == 1
    assert " PAGE " in z.read("word/footer1.xml").decode()
    assert "\x0b" not in doc and "T &lt;&amp;&gt;" in doc                          # XML-safe
    assert extract_text("x.docx", docx_out.build(_model())).split("\n")[:4] == ["", "项目申报书", "项目名称", "T <&>"]


def test_txt_extract():
    assert extract_text("a.txt", "你好".encode()) == "你好"


def test_token_roundtrip_and_tamper():
    import server
    tok = server.make_token("alice", "abc123")
    assert server.read_token(tok) == ("alice", "abc123")
    assert server.read_token(tok[:-1] + ("0" if tok[-1] != "0" else "1")) is None   # bad signature
    assert server.read_token("junk") is None


def test_password_hash_differs_by_salt():
    import server
    assert server._hash("pw-12345", b"a" * 16) != server._hash("pw-12345", b"b" * 16)


def test_is_cn():
    import server
    assert server.is_cn("114.114.114.114") and server.is_cn("::ffff:114.114.114.114")
    assert not server.is_cn("8.8.8.8") and not server.is_cn("127.0.0.1") and not server.is_cn("garbage")
