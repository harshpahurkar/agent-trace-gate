"""Unit tests for the static import scanners."""

from pathlib import Path

from agenttrace.static_checks import node_imports, py_imports

ROOT = Path(__file__).resolve().parents[1]


def test_python_scan_finds_hallucinated_import():
    source = (ROOT / "samples/python/hallucinated_import/report_gen.py").read_text(encoding="utf-8")
    found = py_imports.check_file(source)
    modules = {imp.module: imp.resolution for imp in found}
    assert modules["pandas_profiling_lite"] == "unknown"


def test_python_scan_resolves_stdlib():
    source = (ROOT / "samples/python/passing/weather_report.py").read_text(encoding="utf-8")
    found = py_imports.check_file(source)
    assert found, "expected at least one import"
    assert all(imp.resolution in ("stdlib", "builtin") for imp in found)


def test_python_relative_imports_ignored():
    found = py_imports.scan_imports("from . import sibling\nfrom .util import helper\n")
    assert found == []


def test_node_scan_flags_fabricated_package():
    source = (ROOT / "samples/node/hallucinated_import/fetch_prices.mjs").read_text(encoding="utf-8")
    found = node_imports.check_file(source, ROOT)
    modules = {imp.module: imp.resolution for imp in found}
    assert modules["axios-scraper"] == "unknown"


def test_node_scan_resolves_declared_dependency():
    source = (ROOT / "samples/node/hallucinated_method/slugify.mjs").read_text(encoding="utf-8")
    found = node_imports.check_file(source, ROOT)
    modules = {imp.module: imp.resolution for imp in found}
    assert modules["lodash"] == "installed"


def test_node_scoped_package_name():
    assert node_imports.package_name("@opentelemetry/api") == "@opentelemetry/api"
    assert node_imports.package_name("lodash/fp") == "lodash"


def test_node_relative_specifiers_ignored():
    found = node_imports.scan_imports('import { x } from "./local.mjs";\n')
    assert found == []
