#!/usr/bin/env python3
"""
Phase 17: real DXF structure extraction for AutoCAD Agent — never an
LLM's guess about what a drawing "probably" contains. Uses ezdxf (a
real, PyPI-installed DXF-parsing library) to open an actual DXF file
(an open, documented format) and extract layers, entity type counts,
the real drawing extents, and any TEXT/MTEXT/DIMENSION content.

Native .dwg is explicitly out of scope (Phase 17 doc, Section 4,
known_constraint) — no open-source parser exists and this is a Linux
environment with no Autodesk tooling; this script assumes a DWG->DXF
conversion already happened upstream.

Usage: dxf_parse.py <dxf_file_path>
Prints a structured JSON summary on success, {"error": "..."} with exit 1 on failure.
"""
import json
import sys

try:
    import ezdxf
    from ezdxf import bbox
except ImportError:
    print(json.dumps({"error": "ezdxf not installed — run: pip install ezdxf"}))
    sys.exit(1)


def parse(path: str) -> dict:
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()

    layers = sorted(layer.dxf.name for layer in doc.layers)

    entity_counts: dict[str, int] = {}
    text_content: list[str] = []
    dimensions: list[dict] = []

    for entity in msp:
        etype = entity.dxftype()
        entity_counts[etype] = entity_counts.get(etype, 0) + 1
        if etype in ("TEXT", "MTEXT"):
            text_content.append(entity.dxf.text if etype == "TEXT" else entity.text)
        elif etype == "DIMENSION":
            try:
                dimensions.append({"measurement": entity.get_measurement(), "text": entity.dxf.text or ""})
            except Exception:  # noqa: BLE001 — a malformed dimension entity shouldn't abort the whole parse
                pass

    # Real geometric bounding box computed from actual entities
    # (ezdxf.bbox), not the DXF header's $EXTMIN/$EXTMAX fields — those
    # are only as accurate as whatever authored the file last maintained
    # them, and are frequently stale/unset on programmatically-created
    # or edited files. Computing from real geometry is honestly correct
    # regardless of header state.
    box = bbox.extents(msp)
    extents = None
    if box.has_data:
        extents = {"min": [round(box.extmin.x, 6), round(box.extmin.y, 6)], "max": [round(box.extmax.x, 6), round(box.extmax.y, 6)]}

    return {
        "dxf_version": doc.dxfversion,
        "layers": layers,
        "entity_counts": entity_counts,
        "total_entities": sum(entity_counts.values()),
        "extents": extents,
        "text_content": text_content,
        "dimensions": dimensions,
    }


def main():
    if len(sys.argv) != 2:
        print(json.dumps({"error": "usage: dxf_parse.py <dxf_file_path>"}))
        sys.exit(1)
    path = sys.argv[1]
    try:
        result = parse(path)
    except IOError as e:
        print(json.dumps({"error": f"could not read file: {e}"}))
        sys.exit(1)
    except ezdxf.DXFError as e:
        print(json.dumps({"error": f"not a valid DXF file: {e}"}))
        sys.exit(1)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
