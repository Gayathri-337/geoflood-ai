"""
GeoFlood AI - Phase 31 patch: dashboard improvements (repeat count, severity overview, event links).
Run once from the project root:    python patch_phase31.py

Each edit is checked against the exact text it expects. If a file does not look as expected, nothing in that file
is changed and you are told. Running it twice is safe.
"""
from pathlib import Path

STATS_OLD = '''          FROM flood_analysis""")).mappings().one()
    out = dict(row)
'''
STATS_NEW = '''          FROM flood_analysis""")).mappings().one()
    out = dict(row)

    # analyses that repeat an image (same file) already analysed with the same baseline setting
    out["repeat_analyses"] = int(db.execute(text("""
        SELECT (SELECT count(*) FROM flood_analysis WHERE status = 'completed')
             - (SELECT count(*) FROM (
                    SELECT DISTINCT coalesce(i.file_sha256, 'image-' || i.image_id::text), a.baseline_method
                      FROM flood_analysis a JOIN satellite_images i ON i.image_id = a.image_id
                     WHERE a.status = 'completed') AS distinct_runs)""")).scalar_one())

    # saved severity levels of the completed analyses
    sev = db.execute(text("""
        SELECT count(*) FILTER (WHERE severity = 'low')      AS low,
               count(*) FILTER (WHERE severity = 'moderate') AS moderate,
               count(*) FILTER (WHERE severity = 'high')     AS high,
               count(*) FILTER (WHERE severity = 'severe')   AS severe,
               count(*) FILTER (WHERE severity IS NULL)      AS not_classified
          FROM flood_analysis WHERE status = 'completed'""")).mappings().one()
    out["severity_counts"] = {key: int(value) for key, value in sev.items()}
'''

SCHEMA_OLD = "    latest_analysis_at: Optional[datetime]\n    note: str"
SCHEMA_NEW = ("    latest_analysis_at: Optional[datetime]\n"
              "    repeat_analyses: int = 0                # completed analyses that repeat an image + baseline setting\n"
              "    severity_counts: dict[str, int] = {}    # saved levels; 'not_classified' = no level saved yet\n"
              "    note: str")

DASH_OLD_NOTE = '''        {stats.note} Latest analysis: {formatDate(stats.latest_analysis_at)}.
      </p>
'''
DASH_NEW_NOTE = '''        {stats.note} Latest analysis: {formatDate(stats.latest_analysis_at)}.
        {stats.repeat_analyses > 0 && (
          <>
            {" "}
            {stats.repeat_analyses} of the completed analyses{" "}
            {stats.repeat_analyses === 1 ? "repeats an image" : "repeat an image"} that was already analysed with the
            same baseline setting, so {stats.repeat_analyses === 1 ? "its" : "their"} areas are counted again in these
            totals.
          </>
        )}
      </p>

      <SeveritySummary counts={stats.severity_counts} />
'''

EDITS = {
    "backend/routers/stats.py": [(STATS_OLD, STATS_NEW, "repeat_analyses")],
    "backend/schemas/analysis.py": [(SCHEMA_OLD, SCHEMA_NEW, "repeat_analyses")],
    "frontend/src/pages/Dashboard.jsx": [
        ('import { LEVEL_BADGE, LEVEL_LABEL } from "../severity.js";\n',
         'import SeveritySummary from "../components/SeveritySummary.jsx";\n'
         'import { LEVEL_BADGE, LEVEL_LABEL } from "../severity.js";\n', "import SeveritySummary"),
        (DASH_OLD_NOTE, DASH_NEW_NOTE, "<SeveritySummary"),
        ("                  <td>{a.event_id}</td>\n",
         "                  <td>\n                    <Link to={`/events/${a.event_id}`}>{a.event_id}</Link>\n                  </td>\n",
         "/events/${a.event_id}"),
    ],
}


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
        if not todo:
            print(f"[SKIP] {name}: already patched")
            continue
        for old, new in todo:
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")
        print(f"[DONE] {name}: {len(todo)} edit(s)")
    print("\nAll good." if not problems else f"\n{problems} problem(s) - send me the lines above.")


if __name__ == "__main__":
    main()
