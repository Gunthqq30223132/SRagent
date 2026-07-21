"""
Consensus Ledger — Pure deterministic module (no LLM, no I/O beyond parameters).

Builds a conflict-aware ledger from verified extractions, applies RoB weighting,
detects conflicts, and renders markdown tables. All logic is deterministic.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from unicodedata import normalize


# Constant: approximate value indicators (exportable)
APPROX_LEXICON = [
    "approximately", "about", "around", "roughly", "~",
    "khoảng", "xấp xỉ", "gần"
]


@dataclass
class Claim:
    """Ledger claim with conflict detection metadata."""
    claim_id: str
    run_id: str
    outcome_id: str
    uid: str
    field: str
    value: str  # byte-exact from extraction
    quote: str
    rob_overall: str
    weight: float
    direction: str | None
    conflict_group: str | None
    created_at: str  # ISO 8601


def rob_weight(rob_overall: str) -> float:
    """
    Convert RoB grade to numeric weight.
    
    Args:
        rob_overall: RoB grade string
        
    Returns:
        1.0 for LOW, 0.5 for SOME_CONCERNS, 0.0 for HIGH/VOID
    """
    grade = rob_overall.upper()
    if grade == "LOW":
        return 1.0
    elif grade == "SOME_CONCERNS":
        return 0.5
    else:  # HIGH, VOID, or any other value
        return 0.0


def build_ledger(
    extractions: list[dict[str, Any]],
    rob_map: dict[str, str],
    protocol: dict[str, Any]
) -> list[Claim]:
    """
    Build consensus ledger from verified extractions.
    
    Only accepts extractions with verified==1 (rejects 2/0).
    For each doc: agent='human' wins over rob_a.
    VOID entries remain in ledger with weight 0.0.
    
    Args:
        extractions: List of extraction dicts with verified==1
        rob_map: {uid: rob_overall} mapping
        protocol: Protocol dict with outcomes and direction_terms
        
    Returns:
        List of Claims with deterministic outcome/direction mapping
    """
    claims = []
    created_at = datetime.utcnow().isoformat() + "Z"
    
    # Filter verified==1 only
    verified = [e for e in extractions if e.get("verified") == 1]
    
    # Group by (run_id, uid, field) to handle agent priority
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for ext in verified:
        key = (ext["run_id"], ext["uid"], ext["field"])
        groups.setdefault(key, []).append(ext)
    
    # Process each group: human wins over rob_a
    for (run_id, uid, field), group in groups.items():
        # Find human agent entry first
        human_entries = [e for e in group if e.get("agent") == "human"]
        if human_entries:
            winning = human_entries[0]
        else:
            # Use rob_a if no human
            winning = group[0]
        
        # Map outcome
        outcome_id = "__unmapped__"
        for outcome in protocol.get("outcomes", []):
            if field in outcome.get("match_fields", []):
                outcome_id = outcome["id"]
                break
        
        # Determine direction (only if outcome is mapped)
        direction = None
        if outcome_id != "__unmapped__":
            direction = _determine_direction(
                winning.get("quote", ""),
                protocol.get("outcomes", []),
                outcome_id
            )
        
        # Get RoB and weight
        rob_overall = rob_map.get(uid, "VOID")
        weight = rob_weight(rob_overall)
        
        # Create claim
        claim = Claim(
            claim_id=winning.get("extraction_id", ""),
            run_id=run_id,
            outcome_id=outcome_id,
            uid=uid,
            field=field,
            value=winning.get("value", ""),
            quote=winning.get("quote", ""),
            rob_overall=rob_overall,
            weight=weight,
            direction=direction,
            conflict_group=None,
            created_at=created_at
        )
        claims.append(claim)
    
    return claims


def _determine_direction(
    quote: str,
    outcomes: list[dict[str, Any]],
    outcome_id: str
) -> str | None:
    """
    Determine direction from quote based on direction_terms in protocol.
    
    Uses casefold + exact substring matching.
    If ≥2 direction groups match: NULL
    If exactly 1 group matches: assign that direction
    If no direction_terms defined: NULL
    
    Args:
        quote: Quote text to analyze
        outcomes: List of outcome definitions
        outcome_id: Target outcome ID
        
    Returns:
        Direction string or None
    """
    # Find the outcome
    outcome = None
    for o in outcomes:
        if o["id"] == outcome_id:
            outcome = o
            break
    
    if not outcome:
        return None
    
    direction_terms = outcome.get("direction_terms", {})
    if not direction_terms:
        return None
    
    quote_lower = quote.casefold()
    
    # Check which direction groups have matches
    matched_directions = []
    for direction, terms in direction_terms.items():
        for term in terms:
            if term.casefold() in quote_lower:
                matched_directions.append(direction)
                break  # One match per direction is enough
    
    # Remove duplicates while preserving order
    matched_directions = list(dict.fromkeys(matched_directions))
    
    if len(matched_directions) == 1:
        return matched_directions[0]
    else:
        # 0 or ≥2 matches → NULL
        return None


def detect_conflicts(claims: list[Claim]) -> list[Claim]:
    """
    Detect conflicts within each outcome_id (excluding __unmapped__).
    
    For each outcome, if 2 claims have:
    - Different uid
    - weight > 0
    - Opposing directions (increase↔decrease, no_difference↔any direction)
    → Assign conflict_group = "cfl-<outcome_id>"
    
    Same direction or NULL → no conflict group.
    NO arithmetic between claims.
    
    Args:
        claims: List of Claims
        
    Returns:
        Same list with conflict_group populated where applicable
    """
    # Group by outcome_id (exclude __unmapped__)
    outcome_groups: dict[str, list[Claim]] = {}
    for claim in claims:
        if claim.outcome_id != "__unmapped__" and claim.weight > 0:
            outcome_groups.setdefault(claim.outcome_id, []).append(claim)
    
    # Check each outcome for conflicts
    for outcome_id, group in outcome_groups.items():
        # Check all pairs
        for i, claim1 in enumerate(group):
            for claim2 in group[i + 1:]:
                # Must be different studies
                if claim1.uid == claim2.uid:
                    continue
                
                # Check if directions conflict
                if _is_conflicting(claim1.direction, claim2.direction):
                    # Assign conflict group to both
                    claim1.conflict_group = f"cfl-{outcome_id}"
                    claim2.conflict_group = f"cfl-{outcome_id}"
    
    return claims


def _is_conflicting(dir1: str | None, dir2: str | None) -> bool:
    """
    Check if two directions are conflicting.
    
    Conflicts:
    - increase ↔ decrease
    - no_difference ↔ any non-null direction
    
    Args:
        dir1: First direction
        dir2: Second direction
        
    Returns:
        True if conflicting
    """
    if dir1 is None or dir2 is None:
        return False
    
    # increase ↔ decrease
    if {dir1, dir2} == {"increase", "decrease"}:
        return True
    
    # no_difference ↔ any direction
    if dir1 == "no_difference" and dir2 in ["increase", "decrease"]:
        return True
    if dir2 == "no_difference" and dir1 in ["increase", "decrease"]:
        return True
    
    return False


def build_anchor_set(claims: list[Claim]) -> set[str]:
    """
    Build anchor set from claims with weight>0 and mapped outcome.
    
    Extracts:
    - Raw value strings
    - Numeric tokens
    - <number><unit> pairs where unit ∈ protocol.unit_lexicon (after NFKC)
    
    Args:
        claims: List of Claims with protocol context
        
    Returns:
        Set of anchor strings
    """
    anchors = set()
    
    # Filter claims: weight > 0 and mapped outcome
    eligible = [c for c in claims if c.weight > 0 and c.outcome_id != "__unmapped__"]
    
    for claim in eligible:
        value = claim.value
        if not value:
            continue
        
        # Add raw value
        anchors.add(value)
        
        # Normalize for unit extraction
        normalized = normalize("NFKC", value)
        
        # Extract numeric tokens and number-unit pairs
        tokens = normalized.split()
        for i, token in enumerate(tokens):
            # Try to extract number from token
            num = _extract_number(token)
            if num:
                anchors.add(num)
                
                # Check if next token is a unit
                if i + 1 < len(tokens):
                    next_token = tokens[i + 1]
                    # Simple unit detection (would need protocol.unit_lexicon in production)
                    # For now, just add the pair if next token looks like a unit
                    if _looks_like_unit(next_token):
                        anchors.add(f"{num}{next_token}")
    
    return anchors


def _extract_number(token: str) -> str | None:
    """Extract numeric part from token."""
    # Remove common non-numeric characters and check if remainder is numeric-like
    cleaned = token.strip("()[]{}:;,.")
    
    # Try to identify if it contains digits
    if any(c.isdigit() for c in cleaned):
        # Extract the numeric portion (simple approach)
        num_chars = []
        for c in cleaned:
            if c.isdigit() or c in ".-+":
                num_chars.append(c)
            elif num_chars:  # Stop at first non-numeric after digits start
                break
        
        if num_chars:
            result = "".join(num_chars)
            # Validate it's a reasonable number
            try:
                float(result)
                return result
            except ValueError:
                pass
    
    return None


def _looks_like_unit(token: str) -> bool:
    """Simple heuristic to identify potential units."""
    # Common unit patterns: short, mostly letters, may have /
    token = token.lower().strip("()[]{}:;,.")
    if not token:
        return False
    
    # Units are typically short and alphanumeric with /
    if len(token) > 10:
        return False
    
    # Must have at least one letter
    if not any(c.isalpha() for c in token):
        return False
    
    # Common unit patterns
    common_units = {
        "mg", "g", "kg", "ml", "l", "mm", "cm", "m", "km",
        "%", "mmol", "mol", "iu", "μg", "ng", "pg",
        "mg/dl", "mmol/l", "mg/l", "μmol/l"
    }
    
    return token in common_units or "/" in token


def render_table(claims: list[Claim]) -> str:
    """
    Render markdown table grouped by outcome.
    
    Format: "study·RoB·weight·value·[claim_id]"
    Conflict groups rendered separately with "CONFLICTING — not pooled" header.
    
    Args:
        claims: List of Claims
        
    Returns:
        Markdown string
    """
    if not claims:
        return "*(no claims)*\n"
    
    lines = []
    
    # Separate conflicting and non-conflicting
    conflicting = [c for c in claims if c.conflict_group is not None]
    non_conflicting = [c for c in claims if c.conflict_group is None]
    
    # Group non-conflicting by outcome
    outcome_groups: dict[str, list[Claim]] = {}
    for claim in non_conflicting:
        outcome_groups.setdefault(claim.outcome_id, []).append(claim)
    
    # Render non-conflicting outcomes
    for outcome_id in sorted(outcome_groups.keys()):
        group = outcome_groups[outcome_id]
        lines.append(f"## {outcome_id}\n")
        
        for claim in sorted(group, key=lambda c: (c.uid, c.field)):
            row = f"{claim.uid}·{claim.rob_overall}·{claim.weight:.1f}·{claim.value}·[{claim.claim_id}]"
            lines.append(row)
        
        lines.append("")  # Blank line between outcomes
    
    # Render conflicting claims
    if conflicting:
        lines.append("## CONFLICTING — not pooled\n")
        
        # Group by conflict_group
        conflict_groups: dict[str, list[Claim]] = {}
        for claim in conflicting:
            if claim.conflict_group:
                conflict_groups.setdefault(claim.conflict_group, []).append(claim)
        
        for conflict_id in sorted(conflict_groups.keys()):
            group = conflict_groups[conflict_id]
            lines.append(f"### {conflict_id}\n")
            
            for claim in sorted(group, key=lambda c: (c.uid, c.field)):
                row = f"{claim.uid}·{claim.rob_overall}·{claim.weight:.1f}·{claim.value}·[{claim.claim_id}]"
                lines.append(row)
            
            lines.append("")
    
    return "\n".join(lines)
