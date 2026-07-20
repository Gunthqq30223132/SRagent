"""Unit tests for scripts/check_gates_superset.py (M1-07).

Tests are written against the *specification*, not the implementation:
- gates.yml is loaded, project is identified, required gates checked.
- SRagent requires: secret_scan, lint_boundary, test_suite,
  compliance_check, clinical_firewall.
- Missing gate → exit 1 + stderr diagnostic.
- All present  → exit 0 + stdout success.
- parse_yaml falls back to a line-based parser when PyYAML is absent.
"""
import importlib
import os
import sys
import textwrap

import pytest


# ---------------------------------------------------------------------------
# Helper: import the script module from scripts/
# ---------------------------------------------------------------------------

def _import_module():
    """Import check_gates_superset as a module."""
    scripts_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts",
    )
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    # Force re-import to pick up any monkeypatching
    if "check_gates_superset" in sys.modules:
        del sys.modules["check_gates_superset"]
    return importlib.import_module("check_gates_superset")


# ---------------------------------------------------------------------------
# Gates YAML content helpers
# ---------------------------------------------------------------------------

_FULL_SRAGENT_GATES = textwrap.dedent("""\
    project: SRagent
    quality_gates:
      secret_scan:
        enabled: true
      lint_boundary:
        enabled: true
      test_suite:
        enabled: true
      compliance_check:
        enabled: true
    clinical_firewall:
      enabled: true
""")

_MISSING_GATE_SRAGENT = textwrap.dedent("""\
    project: SRagent
    quality_gates:
      secret_scan:
        enabled: true
      lint_boundary:
        enabled: true
      test_suite:
        enabled: true
    clinical_firewall:
      enabled: true
""")
# compliance_check is intentionally omitted above.


# ===========================================================================
# Tests
# ===========================================================================


class TestAllGatesPresentPasses:
    """When all required gates for SRagent are in gates.yml → exit 0."""

    def test_all_gates_present_passes(self, tmp_path, monkeypatch):
        # Arrange: create a valid gates.yml with all required gates.
        agents_dir = tmp_path / ".agents"
        agents_dir.mkdir()
        gates_file = agents_dir / "gates.yml"
        gates_file.write_text(_FULL_SRAGENT_GATES)

        # Point the module constants at our temp layout.
        mod = _import_module()
        monkeypatch.setattr(mod, "REPO_DIR", str(tmp_path))
        monkeypatch.setattr(
            mod, "GATES_YML", str(gates_file)
        )

        # Act & Assert: main() should call sys.exit(0).
        with pytest.raises(SystemExit) as exc_info:
            mod.main()
        assert exc_info.value.code == 0


class TestMissingGateFails:
    """When a required gate is absent → exit 1, stderr names the gate."""

    def test_missing_gate_fails(self, tmp_path, monkeypatch, capsys):
        # Arrange: gates.yml is missing compliance_check.
        agents_dir = tmp_path / ".agents"
        agents_dir.mkdir()
        gates_file = agents_dir / "gates.yml"
        gates_file.write_text(_MISSING_GATE_SRAGENT)

        mod = _import_module()
        monkeypatch.setattr(mod, "REPO_DIR", str(tmp_path))
        monkeypatch.setattr(mod, "GATES_YML", str(gates_file))

        # Act
        with pytest.raises(SystemExit) as exc_info:
            mod.main()

        # Assert
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "compliance_check" in captured.err


class TestFallbackParserWithoutPyYAML:
    """parse_yaml should work via fallback when PyYAML is unavailable."""

    def test_fallback_parser_without_pyyaml(self, tmp_path):
        # Arrange: write a simple gates.yml.
        gates_file = tmp_path / "gates.yml"
        gates_file.write_text(_FULL_SRAGENT_GATES)

        # Import then force yaml=None to trigger fallback.
        mod = _import_module()
        original_yaml = mod.yaml
        try:
            mod.yaml = None

            # Act
            result = mod.parse_yaml(str(gates_file))

            # Assert: the parsed dict should contain expected top-level keys.
            assert isinstance(result, dict)
            assert "project" in result
            assert result["project"] == "SRagent"
            assert "quality_gates" in result
        finally:
            mod.yaml = original_yaml
