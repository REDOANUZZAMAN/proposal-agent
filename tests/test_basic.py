import os, sys, zipfile, io
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import docx_out
from server import extract_text


def test_docx_roundtrip():
    data = docx_out.build("T", [{"title": "背景", "text": "第一段\n第二段 <&>"}])
    assert zipfile.ZipFile(io.BytesIO(data)).testzip() is None
    assert extract_text("x.docx", data).split("\n") == ["T", "背景", "第一段", "第二段 <&>"]


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
