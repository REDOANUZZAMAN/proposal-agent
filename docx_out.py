"""Standard Chinese project-proposal .docx with the standard library only.

A4, margins 2.54/3.17 cm, 宋体 小四 (12 pt), 1.5 line spacing, 2-character first-line indent, cover page,
contents page, numbered Heading 1/2 styles, centred page numbers (not on the cover), blank signature page.
The browser preview renders the very same `model`, so preview and file cannot drift apart.

model = {lang: "zh"|"en", label, title, cover: [[label, value]], contents: str,
         chapters: [{title, blocks: [{k: "h2"|"p", t}]}], sign_title: str, sign: [str with {u} = blank to fill in]}
"""
import io
import re
import zipfile
from xml.sax.saxutils import escape

NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
_BAD = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")     # characters XML cannot hold
BREAK = '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'
HEI = '<w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:eastAsia="黑体" w:cs="Arial"/>'


def _t(s):
    return escape(_BAD.sub("", str(s)))


def _run(text, rpr=""):
    return f'<w:r>{"<w:rPr>" + rpr + "</w:rPr>" if rpr else ""}<w:t xml:space="preserve">{_t(text)}</w:t></w:r>'


def _p(content, style=None, ppr=""):
    st = f'<w:pStyle w:val="{style}"/>' if style else ""
    return f"<w:p><w:pPr>{st}{ppr}</w:pPr>{content}</w:p>"


def _blank_runs(text):
    """'签字：{u}' -> text runs with an underlined blank where {u} is."""
    out = []
    for i, part in enumerate(text.split("{u}")):
        if i:
            out.append(_run(" " * 22, "<w:u w:val=\"single\"/>"))
        if part:
            out.append(_run(part))
    return "".join(out)


def _cover_table(rows):
    cell = lambda w, body, b="": (f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/>{b}<w:vAlign w:val="bottom"/></w:tcPr>{body}</w:tc>')
    line = '<w:tcBorders><w:bottom w:val="single" w:sz="6" w:space="0" w:color="000000"/></w:tcBorders>'
    trs = "".join(
        f'<w:tr><w:trPr><w:trHeight w:val="680"/></w:trPr>'
        + cell(2500, _p(_run(k, HEI + '<w:b/><w:sz w:val="28"/>'), "CoverCell", '<w:jc w:val="right"/>'))
        + cell(4700, _p(_run(v, '<w:sz w:val="28"/>'), "CoverCell", '<w:jc w:val="center"/>'), line) + "</w:tr>"
        for k, v in rows)
    return ('<w:tbl><w:tblPr><w:tblW w:w="7200" w:type="dxa"/><w:jc w:val="center"/><w:tblLayout w:type="fixed"/></w:tblPr>'
            f'<w:tblGrid><w:gridCol w:w="2500"/><w:gridCol w:w="4700"/></w:tblGrid>{trs}</w:tbl>')


def _table(rows):
    """Markdown-style grid -> bordered Word table, first row = bold shaded header repeated on every page."""
    n = max(len(r) for r in rows)
    width = lambda t: sum(2 if ord(ch) > 0x2E80 else 1 for ch in str(t))          # CJK characters are twice as wide
    weights = [min(36, max(4, max((width(r[j]) for r in rows if j < len(r)), default=4))) for j in range(n)]
    ws = [8306 * x // sum(weights) for x in weights]
    edge = lambda e: f'<w:{e} w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
    trs = ""
    for i, r in enumerate(rows):
        cells = "".join(
            f'<w:tc><w:tcPr><w:tcW w:w="{ws[j]}" w:type="dxa"/>{"<w:shd w:val=%sclear%s w:color=%sauto%s w:fill=%sE7E6E6%s/>" % ((chr(34),) * 6) if i == 0 else ""}</w:tcPr>'
            + _p(_run(c, "<w:b/>" if i == 0 else ""), "TableText", '<w:jc w:val="center"/>' if i == 0 else "") + "</w:tc>"
            for j, c in enumerate(list(r) + [""] * (n - len(r))))
        trs += f'<w:tr><w:trPr><w:cantSplit/>{"<w:tblHeader/>" if i == 0 else ""}</w:trPr>{cells}</w:tr>'
    return ('<w:tbl><w:tblPr><w:tblW w:w="8306" w:type="dxa"/><w:tblBorders>' + "".join(edge(e) for e in ("top", "left", "bottom", "right", "insideH", "insideV"))
            + '</w:tblBorders><w:tblLayout w:type="fixed"/></w:tblPr><w:tblGrid>' + "".join(f'<w:gridCol w:w="{x}"/>' for x in ws) + f"</w:tblGrid>{trs}</w:tbl>"
            '<w:p><w:pPr><w:spacing w:before="0" w:after="0" w:line="120" w:lineRule="exact"/></w:pPr></w:p>')


def _styles(zh):
    body_ind = '<w:ind w:firstLineChars="200" w:firstLine="480"/>' if zh else '<w:spacing w:after="120" w:line="360" w:lineRule="auto"/>'
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {NS}>'
            '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="宋体" w:cs="Times New Roman"/>'
            '<w:sz w:val="24"/><w:szCs w:val="24"/><w:lang w:val="en-US" w:eastAsia="zh-CN"/></w:rPr></w:rPrDefault>'
            '<w:pPrDefault><w:pPr><w:spacing w:after="0" w:line="360" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
            '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>'
            f'<w:style w:type="paragraph" w:styleId="BodyText"><w:name w:val="Body Text"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr>{body_ind}<w:jc w:val="both"/></w:pPr></w:style>'
            f'<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:before="0" w:after="240" w:line="240" w:lineRule="auto"/><w:jc w:val="center"/></w:pPr><w:rPr>{HEI}<w:b/><w:sz w:val="44"/><w:szCs w:val="44"/></w:rPr></w:style>'
            f'<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="BodyText"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="360" w:after="120" w:line="360" w:lineRule="auto"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr>{HEI}<w:b/><w:sz w:val="32"/><w:szCs w:val="32"/></w:rPr></w:style>'
            f'<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="BodyText"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="80" w:line="360" w:lineRule="auto"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr>{HEI}<w:b/><w:sz w:val="28"/><w:szCs w:val="28"/></w:rPr></w:style>'
            '<w:style w:type="paragraph" w:styleId="CoverCell"><w:name w:val="Cover Cell"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="40" w:after="40" w:line="240" w:lineRule="auto"/></w:pPr></w:style>'
            '<w:style w:type="paragraph" w:styleId="TableText"><w:name w:val="Table Text"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="40" w:after="40" w:line="300" w:lineRule="auto"/></w:pPr><w:rPr><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr></w:style>'
            '<w:style w:type="paragraph" w:styleId="ContentsEntry"><w:name w:val="Contents Entry"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="60" w:after="60"/><w:ind w:left="480"/></w:pPr></w:style>'
            '</w:styles>')


def build(model):
    zh = model.get("lang", "zh") == "zh"
    body = ""
    # cover
    body += _p("", None, '<w:spacing w:before="1800" w:after="0"/>')
    body += _p(_run(model.get("label", ""), "<w:sz w:val=\"52\"/><w:szCs w:val=\"52\"/>"), "Title", '<w:spacing w:before="0" w:after="1400" w:line="240" w:lineRule="auto"/>')
    body += _cover_table(model.get("cover", [])) + BREAK
    # contents (static list: page numbers cannot be known without Word's layout; headings are real Heading 1 so Word's own TOC works)
    body += _p(_run(model.get("contents", ""), "<w:sz w:val=\"32\"/><w:szCs w:val=\"32\"/>"), "Title", '<w:spacing w:before="0" w:after="360" w:line="240" w:lineRule="auto"/>')
    body += "".join(_p(_run(c["title"]), "ContentsEntry") for c in model.get("chapters", [])) + BREAK
    # chapters
    for c in model.get("chapters", []):
        body += _p(_run(c["title"]), "Heading1")
        for b in c.get("blocks", []):
            if b.get("k") == "table" and b.get("rows"):
                body += _table(b["rows"])
            else:
                body += _p(_run(b.get("t", "")), "Heading2" if b.get("k") == "h2" else "BodyText")
    # signature page
    body += BREAK + _p(_run(model.get("sign_title", ""), "<w:sz w:val=\"32\"/><w:szCs w:val=\"32\"/>"), "Title", '<w:spacing w:before="0" w:after="480" w:line="240" w:lineRule="auto"/>')
    for line in model.get("sign", []):
        body += _p(_blank_runs(line), None, '<w:spacing w:before="240" w:after="240" w:line="480" w:lineRule="auto"/>')
    sect = ('<w:sectPr><w:footerReference w:type="default" r:id="rId2"/><w:footerReference w:type="first" r:id="rId3"/>'
            '<w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1800" w:bottom="1440" w:left="1800" w:header="851" w:footer="992" w:gutter="0"/><w:titlePg/></w:sectPr>')
    doc = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {NS}><w:body>{body}{sect}</w:body></w:document>'
    footer = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr {NS}><w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
              '<w:fldSimple w:instr=" PAGE "><w:r><w:rPr><w:sz w:val="21"/></w:rPr><w:t>1</w:t></w:r></w:fldSimple></w:p></w:ftr>')
    footer_first = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr {NS}><w:p/></w:ftr>'
    ct = ('<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
          '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
          '<Override PartName="/word/footer2.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/></Types>')
    rel = lambda i, ty, tg: f'<Relationship Id="{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/{ty}" Target="{tg}"/>'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + rel("rId1", "officeDocument", "word/document.xml") + "</Relationships>")
        z.writestr("word/_rels/document.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + rel("rId1", "styles", "styles.xml") + rel("rId2", "footer", "footer1.xml") + rel("rId3", "footer", "footer2.xml") + "</Relationships>")
        z.writestr("word/document.xml", doc)
        z.writestr("word/styles.xml", _styles(zh))
        z.writestr("word/footer1.xml", footer)
        z.writestr("word/footer2.xml", footer_first)
    return buf.getvalue()
