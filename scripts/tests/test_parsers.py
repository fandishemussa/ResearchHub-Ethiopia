from pathlib import Path
from unittest.mock import Mock

from document_downloader.config import SOURCES
from document_downloader.oai import iter_oai_publications
from document_downloader.utils import looks_like_pdf, safe_filename


class FakeClient:
    def __init__(self, content: bytes):
        self.content = content
        self.calls = 0

    def request(self, *args, **kwargs):
        self.calls += 1
        response = Mock()
        response.content = self.content
        response.close = Mock()
        return response


def test_safe_filename():
    assert safe_filename("A: bad/file?") == "A_ bad_file_"


def test_pdf_magic():
    assert looks_like_pdf(b"%PDF-1.7", None)


def test_oai_parse_first_record():
    content = Path("tests/fixtures/oai_page.xml").read_bytes()
    client = FakeClient(content)
    records = list(iter_oai_publications(client, SOURCES["bdu"], max_records=1))
    assert len(records) == 1
    assert records[0].title == "Example Thesis"
    assert records[0].landing_url.endswith("/123456789/4991")
