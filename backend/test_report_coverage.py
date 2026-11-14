"""
GeoFlood AI - Phase 30 test: the reference-data coverage notice inside the PDF report (SYNTHETIC data, no database).

Usage (project root):  python -m backend.test_report_coverage
"""

import re

from backend.report_fixtures import sample_data
from backend.services.coverage import describe_coverage
from backend.services.report import build_report

SEP = "=" * 70


def ok(message):
    print(f"  [OK] {message}")


def text_of(pdf):
    """All the text of an uncompressed report as one string (line breaks become single spaces)."""
    pieces = re.findall(rb"\(((?:[^()\\]|\\.)*)\) Tj", pdf)
    joined = b" ".join(pieces).decode("latin-1")
    return re.sub(r"\s+", " ", joined.replace("\\(", "(").replace("\\)", ")"))


def report(counts, **kwargs):
    data = sample_data(**kwargs)
    if counts is not None:
        data["coverage"] = describe_coverage(counts)
    return text_of(build_report(data, compress=False))


def main():
    print(SEP)
    print("  GeoFlood AI - Phase 30 Report Coverage Test (synthetic data)")
    print(SEP)

    print("\n--- 1. No reference data inside the image ---")
    text = report({"villages": 0, "roads": 0, "farmland": 0, "infrastructure": 0})
    assert "there is no data for this area, not that nothing was affected" in text, text[:300]
    ok("the impact section says that 0 means 'no data', not 'nothing affected'")

    print("\n--- 2. Some layers empty ---")
    text = report({"villages": 1, "roads": 10, "farmland": 0, "infrastructure": 0})
    assert "no farmland and facilities inside this image" in text
    ok("the empty layers are named")

    print("\n--- 3. Everything has data ---")
    text = report({"villages": 1, "roads": 104, "farmland": 1, "infrastructure": 3})
    assert "Reference data inside this image: 1 village, 104 road segments" in text
    assert "not that nothing was affected" not in text
    ok("a plain line with the counts, and no warning")

    print("\n--- 4. Reports built without coverage data still work ---")
    text = report(None)
    assert "6. Infrastructure impact" in text and "Test village A" in text
    ok("the report is unchanged when no coverage information is given")

    print("\n--- 5. Impact not computed: no coverage notice among the figures ---")
    text = report({"villages": 0, "roads": 0, "farmland": 0, "infrastructure": 0}, with_impact=False)
    assert "Impact has not been computed for this analysis" in text
    assert "Reference data inside this image" not in text and "no data for this area" not in text
    ok("the 'not computed' notice stays the only message in that section")

    print("\n" + SEP)
    print("  Report coverage tests passed.")
    print(SEP)


if __name__ == "__main__":
    main()
