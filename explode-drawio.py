import enum
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ["DRAWIO_DISABLE_UPDATE"] = "true"


class Theme(enum.StrEnum):
    LIGHT = "light"
    DARK = "dark"


def get_page_names(drawio_fname: Path):
    ret = []
    with drawio_fname.open() as fd:
        root = ET.fromstring(fd.read())
    for diagram in root.findall(".//diagram"):
        ret.append(diagram.attrib["name"])
    return ret


def export_page(drawio_fname: Path, out_dir: Path, index: int, name: str, theme: Theme):
    cmd = [
        "drawio",
        "--export",
        "--output",
        out_dir / f"{name}-{theme}.svg",
        "--page-index",
        str(index),
        "--svg-theme",
        theme.value,
        "--format",
        "svg",
        drawio_fname,
    ]
    subprocess.run(cmd)


def export_pages(drawio_fname: Path, out_dir: Path):
    pages = get_page_names(drawio_fname)
    themes = [Theme.DARK, Theme.LIGHT]
    # FIXME
    themes = [Theme.LIGHT]
    with ThreadPoolExecutor(len(pages) * len(themes)) as tpe:
        for idx, page in enumerate(pages):
            for theme in themes:
                tpe.submit(export_page, drawio_fname, out_dir, idx, page.replace(' ', '-'), theme)


def main():
    diagram = Path(sys.argv[1])
    dest = Path(sys.argv[2])
    assert diagram.exists()
    assert dest.exists()
    assert dest.is_dir()
    assert diagram.is_file()
    export_pages(diagram,dest )
    pass

if __name__ == "__main__":
    main()
