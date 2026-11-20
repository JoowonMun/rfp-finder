import os
import zipfile
from pathlib import Path

from g2b_scout.convert import convert, pick_rfp
from g2b_scout.convert import pdf as pdf_mod

DOCS = Path(__file__).parent / "fixtures" / "docs"

FILLER = "과업 내용 및 요구사항을 상세히 기술한다. " * 20


def make_hwpx(path: Path, text: str) -> Path:
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
        'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
        f"<hp:p><hp:run><hp:t>{text}</hp:t></hp:run></hp:p>"
        f"<hp:p><hp:run><hp:t>{FILLER}</hp:t></hp:run></hp:p></hs:sec>"
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/hwp+zip")
        z.writestr("Contents/section0.xml", xml)
    return path


def make_text_pdf(path: Path, line: str) -> Path:
    """ASCII 텍스트 한 줄짜리 최소 PDF."""
    lines = [line] * 12
    content = "BT /F1 10 Tf 40 780 Td " + " ".join(f"({l}) Tj 0 -14 Td" for l in lines) + " ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{off:010d} 00000 n \n".encode() for off in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    path.write_bytes(out)
    return path


def test_hwpx_extract(tmp_path):
    r = convert(make_hwpx(tmp_path / "a.hwpx", "사업명: AI 전환 컨설팅"))
    assert r.ok, r.error
    assert "사업명: AI 전환 컨설팅" in r.text


def test_hwpx_real_fixture():
    r = convert(DOCS / "sample_rfp.hwpx")
    assert r.ok, r.error
    assert "정보화본부" in r.text


def test_hwp5_extract_fixture():
    r = convert(DOCS / "sample_notice.hwp")
    assert r.ok, r.error
    assert "청렴서약제" in r.text


def test_signature_beats_extension():
    # 이름은 .hwpx 이지만 실제로는 HWP5(OLE)
    r = convert(DOCS / "sample_ole_named_hwpx.hwpx")
    assert r.ok, r.error
    assert "판로플랫폼" in r.text


def test_pdf_extract(tmp_path):
    r = convert(make_text_pdf(tmp_path / "a.pdf", "Proposal request for AI transformation consulting"))
    assert r.ok, r.error
    assert "AI transformation consulting" in r.text


def test_scanned_pdf_is_failure():
    r = convert(DOCS / "sample_scanned.pdf")
    assert not r.ok and r.error == "no text"


def test_convert_failures_do_not_raise(tmp_path):
    bad_hwp = tmp_path / "bad.hwp"
    bad_hwp.write_bytes(os.urandom(2048))
    empty_pdf = tmp_path / "empty.pdf"
    empty_pdf.write_bytes(b"")
    docx = tmp_path / "x.docx"
    docx.write_bytes(b"not really")
    missing = tmp_path / "nope.hwp"
    for p in (bad_hwp, empty_pdf, docx, missing):
        r = convert(p)
        assert not r.ok and r.error, p


def test_zip_uses_pick_rfp_order(tmp_path):
    inner1 = make_hwpx(tmp_path / "붙임1_보안서약서.hwpx", "보안서약서 본문")
    inner2 = make_hwpx(tmp_path / "제안요청서_최종.hwpx", "제안요청서 본문")
    zpath = tmp_path / "attachments.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.write(inner1, inner1.name)
        z.write(inner2, inner2.name)
    r = convert(zpath)
    assert r.ok, r.error
    assert r.text.index("제안요청서 본문") < r.text.index("보안서약서 본문")
    assert r.source_name == "제안요청서_최종.hwpx"


def test_pick_rfp_order():
    names = ["붙임1_보안서약서.hwp", "제안요청서_최종.hwp", "과업지시서.pdf"]
    assert pick_rfp(names) == ["제안요청서_최종.hwp", "과업지시서.pdf", "붙임1_보안서약서.hwp"]
    assert pick_rfp(["규격서.hwp", "과업내용서.hwp", "기타.pdf"]) == ["과업내용서.hwp", "규격서.hwp", "기타.pdf"]
