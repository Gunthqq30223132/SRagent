#!/usr/bin/env python3
"""CI gate-compare script that validates .agents/gates.yml contains all
required quality gates for a given project.

Reads the project name from gates.yml, looks up the corresponding set of
required gates (e.g. secret_scan, lint_boundary, test_suite, …), and
verifies every required gate is declared.  Exits 0 on success, 1 when
any gate is missing or the config file is absent.
"""
import os
import sys

# PyYAML không nằm trong deps dự án (pyproject zero-touch — CLAUDE.md #1/#4);
# thiếu thì dùng fallback parser bên dưới, vốn được viết cho đúng trường hợp này.
try:
    import yaml
except ModuleNotFoundError:
    yaml = None

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
REPO_DIR = os.path.dirname(SCRIPT_DIR)
GATES_YML = os.path.join(REPO_DIR, ".agents", "gates.yml")

# Standard required gates per project instance
REQUIRED_GATES = {
    "SRagent": [
        "secret_scan",
        "lint_boundary",
        "test_suite",
        "compliance_check",
        "clinical_firewall"
    ],
    "AnesthOS": [
        "secret_scan",
        "lint_boundary",
        "test_suite",
        "compliance_check",
        "clinical_firewall"
    ],
    "AnesthOS-app": [
        "secret_scan",
        "lint_boundary",
        "build",
        "test",
        "test_coverage"
    ]
}

def parse_yaml(filepath):
    """Parse a YAML file and return its contents as a dict.

    Attempts to use PyYAML (``yaml.safe_load``) first.  When PyYAML is
    not installed, falls back to a simple line-based parser that handles
    the flat and single-nested key/value structures used by gates.yml.

    Args:
        filepath: Absolute or relative path to the YAML file.

    Returns:
        A ``dict`` representing the parsed YAML contents.
    """
    try:
        if yaml is None:
            raise ModuleNotFoundError("PyYAML unavailable")
        with open(filepath, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        # Fallback simple parser
        config = {}
        curr = None
        with open(filepath, 'r') as f:
            for line in f:
                l = line.strip()
                if not l or l.startswith('#'): continue
                if ':' in l:
                    if l.endswith(':'):
                        curr = l[:-1].strip()
                        config[curr] = {}
                    else:
                        k, v = l.split(':', 1)
                        k, v = k.strip(), v.strip().strip('"').strip("'")
                        if curr: config[curr][k] = v
                        else: config[k] = v
        return config

def main():
    """Entry point for the gate-compare check.

    Loads the gates configuration from ``.agents/gates.yml``, determines
    the project name, retrieves the set of required gates for that
    project, and checks that every required gate is present in the
    config.  Prints a diagnostic to *stderr* and exits with code 1 if
    any gate is missing; otherwise prints a success message to *stdout*
    and exits with code 0.
    """
    if not os.path.exists(GATES_YML):
        print(f"[-] Error: {GATES_YML} missing.", file=sys.stderr)
        sys.exit(1)

    config = parse_yaml(GATES_YML) or {}
    project = config.get("project", "")
    quality_gates = config.get("quality_gates", {})
    if isinstance(quality_gates, dict):
        present_gates = set(quality_gates.keys())
    else:
        present_gates = set()

    if config.get("clinical_firewall"):
        present_gates.add("clinical_firewall")
    if config.get("tier_top_verify"):
        present_gates.add("tier_top_verify")

    required = set(REQUIRED_GATES.get(project, []))
    if not required:
        # Default fallback required gates
        required = {"secret_scan", "lint_boundary", "build", "test"}

    missing = required - present_gates
    if missing:
        print(f"❌ CI Gate-Compare FAILED: gates.yml in '{project}' is missing required gates: {sorted(list(missing))}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"✅ CI Gate-Compare PASSED: gates.yml in '{project}' satisfies all required standard gates: {sorted(list(required))}")
        sys.exit(0)

if __name__ == "__main__":
    main()
