"""Build fresh, portable Word reports with only Python's standard library.

Each DOCX is a new OOXML ZIP package, never an update of a sample archive.
Word/PowerPoint automation and external Python packages are not required.
"""

from __future__ import annotations

import argparse
import json
import re
import struct
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "dc": "http://purl.org/dc/elements/1.1/",
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)

XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
REL_BASE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
CONTENT_BASE = "application/vnd.openxmlformats-officedocument.wordprocessingml."
REFERENCE_TITLES = (
    "csv—CSV file reading and writing",
    "Design and history FAQ",
    "typing—Support for type hints",
    "C++ core guidelines",
)


def element(parent: ET.Element, tag: str, **attributes: object) -> ET.Element:
    prefix, name = tag.split(":", 1)
    converted = {}
    for key, value in attributes.items():
        if ":" in key:
            attribute_prefix, attribute_name = key.split(":", 1)
            key = f"{{{NS[attribute_prefix]}}}{attribute_name}"
        converted[key] = str(value)
    return ET.SubElement(parent, f"{{{NS[prefix]}}}{name}", converted)


def xml_bytes(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def new_root(tag: str) -> ET.Element:
    prefix, name = tag.split(":", 1)
    return ET.Element(f"{{{NS[prefix]}}}{name}")


class Report:
    def __init__(self, specification: dict, repository_url: str):
        self.specification = specification
        self.repository_url = repository_url
        self.document = new_root("w:document")
        self.body = element(self.document, "w:body")
        self.relationships = new_root("pr:Relationships")
        self.media: dict[str, bytes] = {}
        self.image_count = 0
        self.add_relationship("rId1", "header", "header1.xml")
        self.add_relationship("rId2", "styles", "styles.xml")
        self.add_relationship("rId3", "settings", "settings.xml")

    def resolved(self, text: str) -> str:
        return str(text).replace("REPOSITORY_URL_PENDING", self.repository_url)

    def add_relationship(self, identifier: str, kind: str, target: str) -> None:
        element(self.relationships, "pr:Relationship", Id=identifier,
                Type=REL_BASE + kind, Target=target)

    def run(self, paragraph: ET.Element, text: str, *, bold=False,
            italic=False, code=False, size=24) -> ET.Element:
        run = element(paragraph, "w:r")
        properties = element(run, "w:rPr")
        font = "Consolas" if code else "Times New Roman"
        element(properties, "w:rFonts", **{
            "w:ascii": font, "w:hAnsi": font, "w:cs": font,
        })
        if bold:
            element(properties, "w:b")
        if italic:
            element(properties, "w:i")
        element(properties, "w:sz", **{"w:val": size})
        element(properties, "w:szCs", **{"w:val": size})
        for index, line in enumerate(self.resolved(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")):
            if index:
                element(run, "w:br")
            node = element(run, "w:t")
            node.set(XML_SPACE, "preserve")
            node.text = line
        return run

    def paragraph(self, text="", *, parent=None, bold=False, center=False,
                  page_break=False, indent=False, keep=False, code=False,
                  reference=False, size=24, single=False) -> ET.Element:
        paragraph = element(self.body if parent is None else parent, "w:p")
        properties = element(paragraph, "w:pPr")
        element(properties, "w:pStyle", **{"w:val": "Normal"})
        if keep:
            element(properties, "w:keepNext")
        if code:
            element(properties, "w:keepLines")
        if page_break:
            element(properties, "w:pageBreakBefore")
        element(properties, "w:widowControl")
        if code:
            element(properties, "w:shd", **{"w:val": "clear", "w:fill": "F0F0F0"})
        element(properties, "w:spacing", **{
            "w:before": 0, "w:after": 0,
            "w:line": 240 if code or single else 480, "w:lineRule": "auto",
        })
        if reference:
            element(properties, "w:ind", **{"w:left": 720, "w:hanging": 720})
        elif indent:
            element(properties, "w:ind", **{"w:firstLine": 720})
        element(properties, "w:jc", **{"w:val": "center" if center else "left"})
        if reference:
            matches = [title for title in REFERENCE_TITLES if title in text]
            if matches:
                title = matches[0]
                before, after = text.split(title, 1)
                self.run(paragraph, before)
                self.run(paragraph, title, italic=True)
                self.run(paragraph, after)
            else:
                self.run(paragraph, text)
        else:
            self.run(paragraph, text, bold=bold, code=code,
                     size=17 if code else size)
        return paragraph

    def table(self, specification: dict) -> None:
        headers = specification["headers"]
        rows = [headers] + specification["rows"]
        count = len(headers)
        table = element(self.body, "w:tbl")
        properties = element(table, "w:tblPr")
        element(properties, "w:tblW", **{"w:w": 9360, "w:type": "dxa"})
        borders = element(properties, "w:tblBorders")
        for edge in ("top", "bottom"):
            element(borders, f"w:{edge}", **{"w:val": "single", "w:sz": 4, "w:color": "A0A0A0"})
        element(properties, "w:tblLayout", **{"w:type": "fixed"})
        margins = element(properties, "w:tblCellMar")
        for edge in ("top", "left", "bottom", "right"):
            element(margins, f"w:{edge}", **{"w:w": 80, "w:type": "dxa"})
        widths = [9360 // count] * count
        widths[-1] += 9360 - sum(widths)
        grid = element(table, "w:tblGrid")
        for width in widths:
            element(grid, "w:gridCol", **{"w:w": width})
        for index, values in enumerate(rows):
            if len(values) != count:
                raise ValueError("A report table row does not match its header width.")
            row = element(table, "w:tr")
            row_properties = element(row, "w:trPr")
            element(row_properties, "w:cantSplit")
            if index == 0:
                element(row_properties, "w:tblHeader")
            for column, text in enumerate(values):
                cell = element(row, "w:tc")
                cell_properties = element(cell, "w:tcPr")
                element(cell_properties, "w:tcW", **{"w:w": widths[column], "w:type": "dxa"})
                if index == 0:
                    element(cell_properties, "w:shd", **{"w:val": "clear", "w:fill": "E7EDF3"})
                self.paragraph(str(text), parent=cell, bold=index == 0, size=20, single=True)
        self.paragraph()

    def image(self, specification: dict) -> None:
        path = (ROOT / specification["path"]).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError("Figure path must remain inside the project.")
        data = path.read_bytes()
        if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
            raise ValueError(f"Figure must be a PNG image: {path}")
        width, height = struct.unpack(">II", data[16:24])
        if not width or not height:
            raise ValueError(f"PNG has invalid dimensions: {path}")
        scale = min(468 / width, 510 / height)
        extent_x = round(width * scale * 12700)
        extent_y = round(height * scale * 12700)
        self.image_count += 1
        identifier = f"rId{self.image_count + 3}"
        name = f"image{self.image_count}.png"
        self.media[f"word/media/{name}"] = data
        self.add_relationship(identifier, "image", f"media/{name}")
        self.paragraph("Demonstration Evidence", bold=True, center=True, page_break=True, keep=True)
        caption = specification["caption"]
        match = re.fullmatch(r"(Figure \d+)\.\s*(.*)", caption)
        if match:
            self.paragraph(match.group(1), bold=True, keep=True)
            paragraph = self.paragraph(keep=True)
            self.run(paragraph, match.group(2), italic=True)
        else:
            self.paragraph(caption, keep=True)
        paragraph = self.paragraph(center=True, single=True)
        run = element(paragraph, "w:r")
        drawing = element(run, "w:drawing")
        inline = element(drawing, "wp:inline", distT=0, distB=0, distL=0, distR=0)
        element(inline, "wp:extent", cx=extent_x, cy=extent_y)
        element(inline, "wp:effectExtent", l=0, t=0, r=0, b=0)
        element(inline, "wp:docPr", id=self.image_count, name=name, descr=caption)
        frame = element(inline, "wp:cNvGraphicFramePr")
        element(frame, "a:graphicFrameLocks", noChangeAspect=1)
        graphic = element(inline, "a:graphic")
        graphic_data = element(graphic, "a:graphicData", uri=NS["pic"])
        picture = element(graphic_data, "pic:pic")
        nonvisual = element(picture, "pic:nvPicPr")
        element(nonvisual, "pic:cNvPr", id=0, name=name)
        picture_properties = element(nonvisual, "pic:cNvPicPr")
        element(picture_properties, "a:picLocks", noChangeAspect=1)
        fill = element(picture, "pic:blipFill")
        element(fill, "a:blip", **{"r:embed": identifier})
        stretch = element(fill, "a:stretch")
        element(stretch, "a:fillRect")
        shape = element(picture, "pic:spPr")
        transform = element(shape, "a:xfrm")
        element(transform, "a:off", x=0, y=0)
        element(transform, "a:ext", cx=extent_x, cy=extent_y)
        geometry = element(shape, "a:prstGeom", prst="rect")
        element(geometry, "a:avLst")
        note = self.paragraph()
        self.run(note, "Note. ", italic=True)
        self.run(note, "Screenshot of recorded output from actual command executions, rendered for readability. Full transcripts are included in docs/evidence.")

    def compose(self) -> None:
        specification = self.specification
        for _ in range(3):
            self.paragraph()
        self.paragraph(specification["title"], bold=True, center=True)
        for text in (" and ".join(specification["authors"]), specification["institution"],
                     specification["course"], specification["instructor"], specification["date"]):
            self.paragraph(text, center=True)
        self.paragraph(specification["title"], bold=True, center=True, page_break=True, keep=True)
        for section in specification["sections"]:
            self.paragraph(section["heading"], bold=True, center=True, keep=True,
                           page_break=bool(section.get("pageBreakBefore")))
            for text in section.get("paragraphs", []):
                self.paragraph(text, indent=True)
            for listing in section.get("codeBlocks", []):
                self.paragraph(listing["label"], keep=True)
                self.paragraph(listing["code"], code=True)
            if section.get("table"):
                self.table(section["table"])
            for image in section.get("images", []):
                self.image(image)
        if specification.get("references"):
            self.paragraph("References", bold=True, center=True, page_break=True, keep=True)
            for reference in specification["references"]:
                self.paragraph(reference, reference=True)
        section_properties = element(self.body, "w:sectPr")
        element(section_properties, "w:headerReference", **{"w:type": "default", "r:id": "rId1"})
        element(section_properties, "w:pgSz", **{"w:w": 12240, "w:h": 15840})
        element(section_properties, "w:pgMar", **{
            "w:top": 1440, "w:right": 1440, "w:bottom": 1440,
            "w:left": 1440, "w:header": 720, "w:footer": 720, "w:gutter": 0,
        })
        element(section_properties, "w:pgNumType", **{"w:start": 1})

    def styles(self) -> bytes:
        root = new_root("w:styles")
        defaults = element(root, "w:docDefaults")
        run_defaults = element(defaults, "w:rPrDefault")
        run_properties = element(run_defaults, "w:rPr")
        element(run_properties, "w:rFonts", **{"w:ascii": "Times New Roman", "w:hAnsi": "Times New Roman"})
        element(run_properties, "w:sz", **{"w:val": 24})
        paragraph_defaults = element(defaults, "w:pPrDefault")
        properties = element(paragraph_defaults, "w:pPr")
        element(properties, "w:spacing", **{"w:before": 0, "w:after": 0, "w:line": 480, "w:lineRule": "auto"})
        normal = element(root, "w:style", **{"w:type": "paragraph", "w:default": 1, "w:styleId": "Normal"})
        element(normal, "w:name", **{"w:val": "Normal"})
        element(normal, "w:qFormat")
        return xml_bytes(root)

    def header(self) -> bytes:
        root = new_root("w:hdr")
        paragraph = self.paragraph(parent=root, single=True)
        properties = paragraph.find(f"{{{NS['w']}}}pPr")
        alignment = properties.find(f"{{{NS['w']}}}jc")
        alignment.set(f"{{{NS['w']}}}val", "right")
        field = element(paragraph, "w:fldSimple", **{"w:instr": " PAGE "})
        self.run(field, "1")
        return xml_bytes(root)

    def content_types(self) -> bytes:
        root = new_root("ct:Types")
        element(root, "ct:Default", Extension="rels", ContentType="application/vnd.openxmlformats-package.relationships+xml")
        element(root, "ct:Default", Extension="xml", ContentType="application/xml")
        if self.media:
            element(root, "ct:Default", Extension="png", ContentType="image/png")
        for name, content_type in (
            ("/word/document.xml", CONTENT_BASE + "document.main+xml"),
            ("/word/styles.xml", CONTENT_BASE + "styles+xml"),
            ("/word/settings.xml", CONTENT_BASE + "settings+xml"),
            ("/word/header1.xml", CONTENT_BASE + "header+xml"),
            ("/docProps/core.xml", "application/vnd.openxmlformats-package.core-properties+xml"),
        ):
            element(root, "ct:Override", PartName=name, ContentType=content_type)
        return xml_bytes(root)

    def write(self, output_path: Path) -> None:
        self.compose()
        package_relationships = new_root("pr:Relationships")
        element(package_relationships, "pr:Relationship", Id="rId1", Type=REL_BASE + "officeDocument", Target="word/document.xml")
        element(package_relationships, "pr:Relationship", Id="rId2", Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties", Target="docProps/core.xml")
        core = new_root("cp:coreProperties")
        element(core, "dc:title").text = self.specification["title"]
        element(core, "dc:creator").text = "; ".join(self.specification["authors"])
        element(core, "cp:lastModifiedBy").text = "; ".join(self.specification["authors"])
        settings = new_root("w:settings")
        element(settings, "w:updateFields", **{"w:val": "true"})
        parts = {
            "[Content_Types].xml": self.content_types(),
            "_rels/.rels": xml_bytes(package_relationships),
            "docProps/core.xml": xml_bytes(core),
            "word/document.xml": xml_bytes(self.document),
            "word/styles.xml": self.styles(),
            "word/settings.xml": xml_bytes(settings),
            "word/header1.xml": self.header(),
            "word/_rels/document.xml.rels": xml_bytes(self.relationships),
            **self.media,
        }
        # Parsing every generated XML and writing each member once prevents
        # duplicate ZIP entries and invalid package structures from templates.
        for name, contents in parts.items():
            if name.endswith((".xml", ".rels")):
                ET.fromstring(contents)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as package:
            for name, contents in parts.items():
                package.writestr(name, contents)
        with ZipFile(output_path, "r") as package:
            if package.testzip() is not None:
                raise ValueError(f"DOCX CRC validation failed: {output_path}")
            if len(package.namelist()) != len(set(package.namelist())):
                raise ValueError(f"DOCX contains duplicate package members: {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-url", default="REPOSITORY_URL_PENDING")
    args = parser.parse_args()
    docs = ROOT / "docs"
    specifications = json.loads((docs / "report_content.json").read_text(encoding="utf-8-sig"))
    specifications.append(json.loads((docs / "comparison_content.json").read_text(encoding="utf-8-sig")))
    for specification in specifications:
        filename = specification["filename"]
        if Path(filename).name != filename or not filename.lower().endswith(".docx"):
            raise ValueError("Report filenames must be plain .docx names.")
        path = docs / filename
        Report(specification, args.repository_url).write(path)
        print(f"Built fresh DOCX package: {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
