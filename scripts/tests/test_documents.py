from document_downloader.bdu_handler import rewrite_bdu_url
from document_downloader.config import SOURCES
from document_downloader.html_discovery import _is_supported_document_url
from document_downloader.utils import detect_document_extension


def test_bdu_handle_is_rewritten():
    source = SOURCES["bdu"]
    assert rewrite_bdu_url(source, "http://hdl.handle.net/123456789/4991") == (
        "http://ir.bdu.edu.et/handle/123456789/4991"
    )


def test_supported_document_urls():
    assert _is_supported_document_url("http://example.org/file.pdf?x=1")
    assert _is_supported_document_url("http://example.org/file.doc")
    assert _is_supported_document_url("http://example.org/file.docx?sequence=1")


def test_document_signatures():
    assert detect_document_extension(url="x", content_type=None, first_bytes=b"%PDF-1.7") == ".pdf"
    assert (
        detect_document_extension(url="x", content_type=None, first_bytes=b"PK\x03\x04") == ".docx"
    )
    assert (
        detect_document_extension(
            url="x", content_type=None, first_bytes=bytes.fromhex("D0CF11E0A1B11AE1")
        )
        == ".doc"
    )
