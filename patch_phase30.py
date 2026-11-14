"""
GeoFlood AI - Phase 30 patch. Adds the reference-data coverage check (backend and frontend).
Run once from the project root:    python patch_phase30.py

Each edit is checked against the exact text it expects. If a file does not look as expected, nothing in that file
is changed and you are told. Running it twice is safe.
"""
from pathlib import Path

SERVICE_ADDITION = '''

def reference_coverage(db: Session, analysis_id: int) -> dict:
    """How many reference features (per layer) lie inside the image of this analysis. Read-only."""
    row = db.execute(text("""
        SELECT count(*) FILTER (WHERE f.layer = 'village')        AS villages,
               count(*) FILTER (WHERE f.layer = 'road')           AS roads,
               count(*) FILTER (WHERE f.layer = 'farmland')       AS farmland,
               count(*) FILTER (WHERE f.layer = 'infrastructure') AS infrastructure
          FROM flood_analysis a
          JOIN satellite_images i ON i.image_id = a.image_id
          LEFT JOIN reference_features f ON ST_Intersects(f.geom, i.footprint)
         WHERE a.analysis_id = :aid"""), {"aid": analysis_id}).mappings().one()
    return describe_coverage(dict(row))
'''

ENDPOINT = '''@router.get("/{analysis_id}/reference-coverage")
def reference_coverage(analysis_id: int = PathParam(ge=1, le=MAX_BIGINT), db: Session = Depends(get_db)):
    """
    How much reference data (OpenStreetMap villages, roads, farmland, facilities) is stored inside this analysis's
    image. 'none' or 'partial' means that an impact of 0 may only mean there is no data. Nothing is changed.
    """
    _baseline_or_404(db, analysis_id)
    return {"analysis_id": analysis_id, **svc.reference_coverage(db, analysis_id)}


'''

NOTE = '''              <CoverageNote analysisId={analysisId} />

'''

COVERAGE_BLOCK_OLD = (
    '    out = [KeepTogether([heading, intro, Spacer(1, 4),\n'
    '                         _grid_table(["Layer", "Estimate"], rows, styles, [74 * mm, 100 * mm])])]')
COVERAGE_BLOCK_NEW = (
    '    coverage = data.get("coverage") or {}\n'
    '    if coverage.get("level") in ("none", "partial"):\n'
    '        coverage_block = [_notice(escape(str(coverage.get("message", ""))), styles), Spacer(1, 4)]\n'
    '    elif coverage.get("message"):\n'
    '        coverage_block = [Paragraph(escape(str(coverage["message"])), styles["small"]), Spacer(1, 4)]\n'
    '    else:\n'
    '        coverage_block = []\n'
    '    out = [KeepTogether([heading, intro, Spacer(1, 4), *coverage_block,\n'
    '                         _grid_table(["Layer", "Estimate"], rows, styles, [74 * mm, 100 * mm])])]')

# file -> list of (old text, new text, marker that shows the edit is already there)
EDITS = {
    "backend/services/impact_service.py": [
        ("from sqlalchemy.orm import Session\n",
         "from sqlalchemy.orm import Session\n\nfrom backend.services.coverage import describe_coverage\n",
         "import describe_coverage"),
    ],
    "backend/routers/impact.py": [
        ('@router.get("/{analysis_id}/impact/{layer}")', ENDPOINT + '@router.get("/{analysis_id}/impact/{layer}")',
         "/reference-coverage"),
    ],
    "backend/routers/report.py": [
        ('        "impact": {"summary": summary, "layers": layers},\n',
         '        "impact": {"summary": summary, "layers": layers},\n'
         '        "coverage": impact_service.reference_coverage(db, analysis_id),\n',
         "impact_service.reference_coverage"),
    ],
    "backend/services/report.py": [
        (COVERAGE_BLOCK_OLD, COVERAGE_BLOCK_NEW, "coverage_block"),
    ],
    "frontend/src/api/client.js": [
        ("  impactSummary: (id) => request(`/api/analyses/${encodeURIComponent(id)}/impact`),\n",
         "  impactSummary: (id) => request(`/api/analyses/${encodeURIComponent(id)}/impact`),\n"
         "  referenceCoverage: (id) => request(`/api/analyses/${encodeURIComponent(id)}/reference-coverage`),\n",
         "referenceCoverage:"),
    ],
    "frontend/src/pages/AnalysisPage.jsx": [
        ('import SeverityCard from "../components/SeverityCard.jsx";\n',
         'import CoverageNote from "../components/CoverageNote.jsx";\nimport SeverityCard from "../components/SeverityCard.jsx";\n',
         "import CoverageNote"),
        ('                  : "not computed yet"}\n              </p>\n',
         '                  : "not computed yet"}\n              </p>\n\n' + NOTE.rstrip("\n") + "\n",
         "<CoverageNote"),
    ],
}
APPENDS = {"backend/services/impact_service.py": ("def reference_coverage", SERVICE_ADDITION)}


def main():
    problems = 0
    for name, edits in EDITS.items():
        path = Path(name)
        if not path.exists():
            print(f"[MISSING] {name} - run this from the project root")
            problems += 1
            continue
        text = path.read_text(encoding="utf-8")
        todo, failed = [], False
        for old, new, marker in edits:
            if marker in text:
                continue
            if text.count(old) != 1:
                print(f"[STOP] {name}: the text to change was not found exactly once:\n    {old.strip().splitlines()[0]}")
                problems += 1
                failed = True
                break
            todo.append((old, new))
        if failed:
            continue
        for old, new in todo:
            text = text.replace(old, new)
        extra = APPENDS.get(name)
        appended = False
        if extra and extra[0] not in text:
            text = text.rstrip("\n") + "\n" + extra[1]
            appended = True
        if not todo and not appended:
            print(f"[SKIP] {name}: already patched")
            continue
        path.write_text(text, encoding="utf-8")
        print(f"[DONE] {name}: {len(todo) + int(appended)} edit(s)")
    print("\nAll good." if not problems else f"\n{problems} problem(s) - send me the lines above.")


if __name__ == "__main__":
    main()
