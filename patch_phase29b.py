"""
GeoFlood AI - Phase 29b patch (frontend). Adds the 'date the satellite took the image' field to the Upload
page and the 'Change over time' panel to the Event page. Run once from the project root:

    python patch_phase29b.py

Each edit is checked against the exact text it expects. If a file does not look as expected, nothing in that
file is changed and you are told. Running it twice is safe.
"""
from pathlib import Path

UPLOAD_RULES_ADDITION = '''
// ---- Phase 29b: the date the satellite took the image (optional)
export const EARLIEST_DATE = "2000-01-01";

/** Today as YYYY-MM-DD in the browser's own time zone. */
export function todayString(now = new Date()) {
  const two = (n) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${two(now.getMonth() + 1)}-${two(now.getDate())}`;
}

/** "" when the value is fine (or empty), otherwise a message. */
export function checkAcquiredDate(value, now = new Date()) {
  if (!value) return "";
  const parsed = /^\\d{4}-\\d{2}-\\d{2}$/.test(value) ? new Date(`${value}T00:00:00Z`) : null;
  if (!parsed || Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== value) {
    return "The date the satellite took the image is not a real date.";
  }
  if (value < EARLIEST_DATE) return "The date the satellite took the image cannot be before the year 2000.";
  if (value > todayString(now)) return "The date the satellite took the image cannot be in the future.";
  return "";
}
'''

DATE_FIELD = '''          <div className="mb-3">
            <label htmlFor="acquired-at" className="form-label">
              Date the satellite took the image (optional)
            </label>
            <input
              id="acquired-at"
              type="date"
              className="form-control"
              min="2000-01-01"
              max={todayString()}
              value={acquiredAt}
              onChange={(e) => setAcquiredAt(e.target.value)}
            />
            <div className="form-text">
              Needed to compare images of the same area over time. This is the date of the satellite pass, not
              today&apos;s date. Without it the analysis works as before but is left out of the comparison.
            </div>
          </div>

'''

# file -> list of (old text, new text, marker that shows the edit is already there)
EDITS = {
    "frontend/src/api/client.js": [
        ("  createAnalysis: ({ file, baselineFile, eventId, sourceId }) => {",
         "  createAnalysis: ({ file, baselineFile, eventId, sourceId, acquiredAt }) => {",
         "eventId, sourceId, acquiredAt })"),
        ('    if (baselineFile) formData.append("baseline_file", baselineFile);\n',
         '    if (baselineFile) formData.append("baseline_file", baselineFile);\n'
         '    if (acquiredAt) formData.append("acquired_at", acquiredAt);\n',
         'formData.append("acquired_at"'),
        ("  severity: (id) => request(`/api/analyses/${encodeURIComponent(id)}/severity`),\n",
         "  progression: (eventId) => request(`/api/events/${encodeURIComponent(eventId)}/progression`),\n"
         "  severity: (id) => request(`/api/analyses/${encodeURIComponent(id)}/severity`),\n",
         "  progression: (eventId)"),
    ],
    "frontend/src/pages/UploadPage.jsx": [
        ('import { MAX_UPLOAD_MB, checkBaselineFile, checkImageFile, chipMismatch } from "../uploadRules.js";',
         'import {\n  MAX_UPLOAD_MB,\n  checkAcquiredDate,\n  checkBaselineFile,\n  checkImageFile,\n  chipMismatch,\n'
         '  todayString,\n} from "../uploadRules.js";',
         "checkAcquiredDate,\n"),
        ("  const [baseline, setBaseline] = useState(null);\n",
         "  const [baseline, setBaseline] = useState(null);\n  const [acquiredAt, setAcquiredAt] = useState(\"\");\n",
         "const [acquiredAt, setAcquiredAt]"),
        ("      checkBaselineFile(baseline) ||\n",
         "      checkBaselineFile(baseline) ||\n      checkAcquiredDate(acquiredAt) ||\n",
         "checkAcquiredDate(acquiredAt) ||"),
        ("{ file: image, baselineFile: baseline, eventId, sourceId }",
         "{ file: image, baselineFile: baseline, eventId, sourceId, acquiredAt }",
         "sourceId, acquiredAt }"),
        ("          {image && baseline && chipMismatch(", DATE_FIELD + "          {image && baseline && chipMismatch(",
         'htmlFor="acquired-at"'),
    ],
    "frontend/src/pages/EventPage.jsx": [
        ('import ActionsPanel from "../components/ActionsPanel.jsx";\n',
         'import ActionsPanel from "../components/ActionsPanel.jsx";\n'
         'import ProgressionPanel from "../components/ProgressionPanel.jsx";\n',
         "import ProgressionPanel"),
        ('          </div>\n        </div>\n\n        <div className="col-lg-5">',
         '          </div>\n\n          <ProgressionPanel eventId={eventId} />\n        </div>\n\n'
         '        <div className="col-lg-5">',
         "<ProgressionPanel eventId"),
    ],
    "frontend/src/pages/EventPage.test.jsx": [
        ('  "GET /api/events/2/actions/geojson": [200, PINS],\n};',
         '  "GET /api/events/2/actions/geojson": [200, PINS],\n'
         '  "GET /api/events/2/progression": [200, { event_id: 2, series: [], unassigned: [], criteria: {}, note: "" }],\n};',
         '"GET /api/events/2/progression"'),
    ],
}

APPENDS = {"frontend/src/uploadRules.js": ("checkAcquiredDate", UPLOAD_RULES_ADDITION)}


def main():
    problems = 0
    for name, edits in EDITS.items():
        path = Path(name)
        if not path.exists():
            print(f"[MISSING] {name} - run this from the project root")
            problems += 1
            continue
        text = path.read_text(encoding="utf-8")
        todo = []
        failed = False
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
    for name, (marker, addition) in APPENDS.items():
        path = Path(name)
        if not path.exists():
            print(f"[MISSING] {name} - run this from the project root")
            problems += 1
            continue
        text = path.read_text(encoding="utf-8")
        if marker in text:
            print(f"[SKIP] {name}: already patched")
            continue
        path.write_text(text.rstrip("\n") + "\n" + addition, encoding="utf-8")
        print(f"[DONE] {name}: functions added at the end")
    print("\nAll good." if not problems else f"\n{problems} problem(s) - send me the lines above.")


if __name__ == "__main__":
    main()
