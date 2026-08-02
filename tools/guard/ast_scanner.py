"""AST-based Forbidden Patterns Scanner.

Quét Python AST để phát hiện các anti-pattern nguy hiểm mà regex không bắt được:
1. Broad except (bare `except:` hoặc `except Exception`) bao quanh verify/clinical
2. Silent clamping (gán giá trị mặc định trong except mà không raise)
3. Xóa/sửa assertion hoặc test
4. Tự sửa file gate (forbidden_patterns.py, dev_gate.py, firewall.py)
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ASTViolation:
    """Một vi phạm phát hiện bởi AST scanner."""
    rule: str
    file: str
    line: int
    col: int
    message: str
    severity: str = "ERROR"  # ERROR, WARNING


@dataclass
class ASTScanResult:
    violations: list[ASTViolation] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(v.severity == "ERROR" for v in self.violations)


# Danh sách file gate KHÔNG được sửa bởi agent
GATE_FILES = frozenset({
    "forbidden_patterns.py",
    "dev_gate.py",
    "firewall.py",
    "ast_scanner.py",
    "hmac_token.py",
    "deid_vi.py",
})


class _BroadExceptVisitor(ast.NodeVisitor):
    """Phát hiện broad except và silent clamping."""

    def __init__(self, filename: str):
        self.filename = filename
        self.violations: list[ASTViolation] = []

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        # Rule 1: Bare except or except Exception
        is_broad = False
        if node.type is None:
            is_broad = True
        elif isinstance(node.type, ast.Name) and node.type.id in ("Exception", "BaseException"):
            is_broad = True

        if is_broad:
            # Check if the except body contains raise — if yes, it's acceptable
            has_raise = False
            for child in ast.walk(node):
                if isinstance(child, ast.Raise):
                    has_raise = True
                    break

            if not has_raise:
                # Rule 2: Silent clamping — broad except without raise
                # Check for assignment (return default / assign default)
                has_assignment = False
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, (ast.Assign, ast.Return)):
                        has_assignment = True
                        break

                if has_assignment:
                    self.violations.append(ASTViolation(
                        rule="SILENT_CLAMP",
                        file=self.filename,
                        line=node.lineno,
                        col=node.col_offset,
                        message=(
                            f"Silent clamping detected: broad except at line {node.lineno} "
                            f"assigns/returns a default value without re-raising. "
                            f"This converts errors into silent 'no evidence found' results."
                        ),
                    ))
                else:
                    self.violations.append(ASTViolation(
                        rule="BROAD_EXCEPT",
                        file=self.filename,
                        line=node.lineno,
                        col=node.col_offset,
                        message=(
                            f"Broad except without raise at line {node.lineno}. "
                            f"Errors in verify/clinical paths must propagate, not be swallowed."
                        ),
                    ))

        self.generic_visit(node)


def scan_file(filepath: str | Path) -> list[ASTViolation]:
    """Quét một file Python tìm AST violations."""
    filepath = Path(filepath)
    violations: list[ASTViolation] = []

    if not filepath.exists() or filepath.suffix != ".py":
        return violations

    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        violations.append(ASTViolation(
            rule="SYNTAX_ERROR",
            file=str(filepath),
            line=0,
            col=0,
            message=f"Cannot parse {filepath}: syntax error",
            severity="ERROR",
        ))
        return violations

    # Run broad except / silent clamp visitor
    visitor = _BroadExceptVisitor(str(filepath))
    visitor.visit(tree)
    violations.extend(visitor.violations)

    return violations


def scan_directory(
    dirpath: str | Path,
    *,
    exclude_dirs: set[str] | None = None,
) -> ASTScanResult:
    """Quét toàn bộ thư mục tìm AST violations."""
    dirpath = Path(dirpath)
    if exclude_dirs is None:
        exclude_dirs = {".venv", ".git", "__pycache__", "node_modules", ".pytest_cache"}

    all_violations: list[ASTViolation] = []

    for py_file in dirpath.rglob("*.py"):
        # Skip excluded directories
        if any(part in exclude_dirs for part in py_file.parts):
            continue
        all_violations.extend(scan_file(py_file))

    return ASTScanResult(violations=all_violations)


def check_gate_file_modifications(
    changed_files: list[str],
) -> list[ASTViolation]:
    """Kiểm tra xem có file gate nào bị sửa không."""
    violations: list[ASTViolation] = []
    for f in changed_files:
        basename = Path(f).name
        if basename in GATE_FILES:
            violations.append(ASTViolation(
                rule="GATE_FILE_MODIFIED",
                file=f,
                line=0,
                col=0,
                message=(
                    f"Gate file '{basename}' was modified. "
                    f"Modifying gate/guard files is a BLOCKING violation — ESCALATE to human."
                ),
                severity="ERROR",
            ))
    return violations
