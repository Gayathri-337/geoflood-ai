"""
GeoFlood AI - Phase 28 test: the PDF report builder, on SYNTHETIC data (no database, no server needed).

Usage (project root):  python -m backend.test_report
"""

import copy

from backend.report_fixtures import ANALYSIS, ZONES, collection, sample_data
from backend.services.report import build_report, safe

SEP = "=" * 70


def ok(message):
    print(f"  [OK] {message}")


def pdf_of(**kwargs):
    """The report with readable (uncompressed) text, so that the tests can look for words in it."""
    return build_report(sample_data(**kwargs), compress=False)


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 28 PDF Report Builder Test (synthetic data)")
    print(SEP)

    # ------------------------------------------------------------ 1
    print("\n--- 1. A complete report ---")
    pdf = pdf_of()
    assert pdf.startswith(b"%PDF-") and pdf.rstrip().endswith(b"%%EOF")
    assert len(pdf) > 20_000, "the map image should make the file larger than this"
    for phrase in (b"GeoFlood AI: Flood Analysis Report", b"SYNTHETIC test flood", b"1. Event", b"2. Image and analysis",
                   b"3. Detected water", b"4. Flood extent map", b"5. Severity",
                   b"6. Infrastructure impact", b"7. Emergency response actions of this event",
                   b"8. Limitations and reliability", b"Close the test bridge", b"Test village A", b"Test clinic"):
        assert phrase in pdf, f"missing: {phrase!r}"
    ok("a valid PDF with all eight sections, the map, the event's actions and the listed features")

    # ------------------------------------------------------------ 2
    print("\n--- 2. The accuracy rules ---")
    assert b"Detected water is not confirmed flooding" in pdf
    assert b"New water relative to the baseline" in pdf
    assert b"1 road, 1.234 km flooded" in pdf, "the road count and length must leave out the bridge"
    assert b"1 bridge, 0.058 km" in pdf and b"Bridges over the detected water" in pdf
    assert b"not an official standard" in pdf
    assert b"not recorded" in pdf, "the observation date is missing in the data and must be said so"
    assert b"lower bounds" in pdf
    ok("detected water is not called flooding; the bridge is separate from the flooded roads; the missing "
       "observation date is stated; the severity rules are called provisional")

    # ------------------------------------------------------------ 3
    print("\n--- 3. Impact not computed ---")
    pdf = pdf_of(with_impact=False)
    assert b"Impact has not been computed for this analysis" in pdf
    assert b"1.234" not in pdf and b"Test village A" not in pdf, "no impact numbers may appear"
    assert b"not computed" in pdf, "the severity table must say 'not computed', not show zeros"
    ok("a clear notice instead of figures; the severity table says 'not computed' (never 0)")

    # ------------------------------------------------------------ 4
    print("\n--- 4. No baseline, no actions ---")
    pdf = pdf_of(baseline=False, with_actions=False)
    assert b"no baseline layer was used" in pdf
    assert b"No emergency actions have been recorded" in pdf
    assert b"Permanent water" not in pdf.split(b"3. Detected water")[1].split(b"4. Flood")[0]
    ok("new water is 'not available' without a baseline; an empty action list is said in words")

    # ------------------------------------------------------------ 5
    print("\n--- 5. Odd text ---")
    data = sample_data()
    assert "অ" in data["event"]["description"]
    pdf = build_report(data, compress=False)
    # the text "<b>Markup</b>" must be printed as it is; if it were read as markup the letter b would vanish
    # from the page and the word would turn bold. The PDF stores the pieces as separate (...) Tj items.
    assert b"(Markup) Tj" in pdf and b"(b) Tj" in pdf and b"(/b) Tj" in pdf
    assert safe("অসম") == "???" and safe(None) == "not recorded" and safe("  ") == "not recorded"
    ok("<, > and & in names are printed as text; characters the PDF font lacks become '?', no crash")

    # ------------------------------------------------------------ 6
    print("\n--- 6. Large and unusual input ---")
    data = sample_data()
    village = data["impact"]["layers"]["villages"]["features"][0]
    data["impact"]["layers"]["villages"]["features"] = [copy.deepcopy(village) for _ in range(40)]
    action = data["actions"][0]
    data["actions"] = [dict(action, action_id=i) for i in range(50)]
    pdf = build_report(data, compress=False)
    assert b"and 25 more" in pdf and b"and 20 more" in pdf
    empty = sample_data()
    empty["zones"] = collection()
    empty["analysis"]["bounds_wgs84"] = [93.4, 26.3, 93.4, 26.3]          # a single point
    assert build_report(empty).startswith(b"%PDF-")
    ok("long lists are cut after 15 villages and 30 actions with a 'more' line; no polygons and a zero-size image "
       "extent still give a report")

    # ------------------------------------------------------------ 7
    print("\n--- 7. The input is not changed ---")
    data = sample_data()
    before = copy.deepcopy(data)
    build_report(data)
    assert data == before
    assert ANALYSIS["severity"] is None and len(ZONES["features"]) == 3
    ok("building a report leaves the data as it was")

    print("\n" + SEP)
    print("  PDF report builder tests passed.")
    print(SEP)


if __name__ == "__main__":
    main()
