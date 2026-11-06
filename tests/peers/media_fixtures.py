"""Create synthetic documents using the independently installed, pinned parser package."""

from pathlib import Path
import sys
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

root = Path(sys.argv[1])


def document(name, labels, encrypted=False):
    writer = PdfWriter()
    for label in labels:
        page = writer.add_blank_page(width=300, height=200)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): writer._add_object(font)}
                )
            }
        )
        stream = DecodedStreamObject()
        stream.set_data(
            ("BT /F1 12 Tf 20 100 Td (" + label + ") Tj ET\n" + " " * 20000).encode()
        )
        page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("secret-fixture-only")
    with (root / name).open("wb") as f:
        writer.write(f)


document("good.pdf", ["Selected page one", "Selected page two"])
document("unselected.pdf", ["UNSELECTED"])
document("empty.pdf", [""])
document("encrypted.pdf", ["Private"], True)
(root / "corrupt.pdf").write_bytes(b"%PDF-1.7\nnot a valid file")
