"""
BS4 Consensus Ledger — Pure deterministic module (no LLM, no external I/O).

Implements §2-§5 of BS4-implementation.md:
- build_ledger: filters verified extractions, applies RoB weighting
- detect_conflicts: identifies contradictory claims
- build_anchor_set: extracts numeric tokens for pooling
- render_table: markdown output grouped by outcome
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
import unicodedata
import re


# §4 — Approximation lexicon for anchor extraction
APPROX_LEXICON = [
    "approximately", "about", "around", "roughly", "~",
    "khoảng", "xấp xỉ", "gần"
]


@dataclass
class Claim:
    """§2 — Ledger claim schema (byte-exact field names)."""
    claim_id: str
    run_id: str
    outcome_id: str
    uid: str
    field: str
    value: str
    quote: str
    rob_overall: str
    weight: float
    direction: str | None
    conflict_group: str | None
    created_at: str


def rob_weight(rob_overall: str) -> float:
    """
    §3 — RoB to weight mapping (deterministic).
    
    - "high" → 1.0
    - "some_concerns" → 0.5
    - "low" → 0.25
    - "VOID" → 0.0
    - unknown → 0.0
    """
    mapping = {
        "high": 1.0,
        "some_concerns": 0.5,
        "low": 0.25,
        "VOID": 0.0
    }
    return mapping.get(rob_overall, 0.0)


def build_ledger(
    extractions: list[dict[str, Any]],
    rob_map: dict[str, str],
    protocol: dict[str, Any]
) -> list[Claim]:
    """
    §3 — Build consensus ledger from verified extractions.
    
    Process:
    1. Filter verified==1 extractions only (2/0 rejected)
    2. Determine RoB: agent=='human' takes rob_a, else rob_map[uid]
    3. Map field → outcome_id via protocol.outcomes[].match_fields
    4. Detect direction via protocol.outcomes[].direction_terms (casefold substring)
    5. Calculate weight via rob_weight()
    6. VOID claims stay in ledger with weight=0.0
    
    Returns list of Claims (no conflicts detected yet).
    """
    claims = []
    
    # Build outcome field mapping (§3 — deterministic, ≤1 outcome per field)
    field_to_outcome: dict[str, str] = {}
    for outcome in protocol.get("outcomes", []):
        outcome_id = outcome["outcome_id"]
        for field in outcome.get("match_fields", []):
            field_to_outcome[field] = outcome_id
    
    # Build direction detection map per outcome
    outcome_directions: dict[str, dict[str, list[str]]] = {}
    for outcome in protocol.get("outcomes", []):
        outcome_id = outcome["outcome_id"]
        direction_terms = outcome.get("direction_terms", {})
        outcome_directions[outcome_id] = direction_terms
    
    for ext in extractions:
        # §3.1 — Only verified==1
        if ext.get("verified") != 1:
            continue
        
        uid = ext["uid"]
        field = ext["field"]
        agent = ext.get("agent", "")
        
        # §3.2 — RoB resolution: human wins rob_a, else rob_map
        if agent == "human":
            rob_overall = ext.get("rob_a", "VOID")
        else:
            rob_overall = rob_map.get(uid, "VOID")
        
        # §3.3 — Map field to outcome_id
        outcome_id = field_to_outcome.get(field, "__unmapped__")
        
        # §3.4 — Direction detection (deterministic substring match)
        direction = None
        if outcome_id != "__unmapped__":
            dir_terms = outcome_directions.get(outcome_id, {})
            quote_lower = ext.get("quote", "").casefold()
            
            matched_directions = []
            for dir_name, terms in dir_terms.items():
                for term in terms:
                    if term.casefold() in quote_lower:
                        matched_directions.append(dir_name)
                        break  # One match per direction is enough
            
            # ≥2 directions → NULL, exactly 1 → assign
            if len(set(matched_directions)) == 1:
                direction = matched_directions[0]
            elif len(set(matched_directions)) >= 2:
                direction = None
        
        # §3.5 — Calculate weight (VOID → 0.0, stays in ledger)
        weight = rob_weight(rob_overall)
        
        # §2 — Build claim
        claim = Claim(
            claim_id=ext["claim_id"],
            run_id=ext["run_id"],
            outcome_id=outcome_id,
            uid=uid,
            field=field,
            value=ext["value"],
            quote=ext.get("quote", ""),
            rob_overall=rob_overall,
            weight=weight,
            direction=direction,
            conflict_group=None,  # Assigned in detect_conflicts
            created_at=ext.get("created_at", datetime.utcnow().isoformat() + "Z")
        )
        claims.append(claim)
    
    return claims


def detect_conflicts(claims: list[Claim]) -> list[Claim]:
    """
    §5 — Detect contradictory claims and assign conflict_group.
    
    For each outcome_id (excluding __unmapped__):
    - Find pairs of claims with different uid, weight>0
    - If directions are contradictory:
      - increase ↔ decrease
      - no_difference ↔ any directional (increase/decrease)
    - Assign conflict_group = "cfl-<outcome_id>"
    
    Same direction or NULL directions → no conflict.
    NO ARITHMETIC between claim values.
    
    Returns modified claims list.
    """
    # Group by outcome_id
    outcome_groups: dict[str, list[Claim]] = {}
    for claim in claims:
        if claim.outcome_id == "__unmapped__":
            continue
        outcome_groups.setdefault(claim.outcome_id, []).append(claim)
    
    # Detect conflicts per outcome
    for outcome_id, group in outcome_groups.items():
        # Find claims with weight > 0
        active_claims = [c for c in group if c.weight > 0]
        
        # Check all pairs for conflicts
        conflict_found = False
        for i, claim_a in enumerate(active_claims):
            for claim_b in active_claims[i+1:]:
                # Must be different studies
                if claim_a.uid == claim_b.uid:
                    continue
                
                dir_a = claim_a.direction
                dir_b = claim_b.direction
                
                # Skip if either direction is NULL
                if dir_a is None or dir_b is None:
                    continue
                
                # Check contradiction rules
                is_conflict = False
                
                # increase ↔ decrease
                if {dir_a, dir_b} == {"increase", "decrease"}:
                    is_conflict = True
                
                # no_difference ↔ any directional
                if dir_a == "no_difference" and dir_b in {"increase", "decrease"}:
                    is_conflict = True
                if dir_b == "no_difference" and dir_a in {"increase", "decrease"}:
                    is_conflict = True
                
                if is_conflict:
                    conflict_found = True
                    break
            
            if conflict_found:
                break
        
        # Assign conflict_group to all claims in this outcome if conflict found
        if conflict_found:
            conflict_group = f"cfl-{outcome_id}"
            for claim in group:
                claim.conflict_group = conflict_group
    
    return claims


def build_anchor_set(claims: list[Claim]) -> set[str]:
    """
    §4 — Extract numeric anchors from claims for pooling preparation.
    
    For claims with weight>0 and mapped outcome (not __unmapped__):
    - Extract value verbatim (after strip)
    - Extract standalone numeric tokens
    - Extract <number><unit> pairs where unit ∈ protocol.unit_lexicon
    
    All strings normalized via NFKC before extraction.
    
    Returns set of anchor strings.
    """
    anchors = set()
    
    for claim in claims:
        if claim.weight <= 0:
            continue
        if claim.outcome_id == "__unmapped__":
            continue
        
        # Normalize and extract from value
        value_norm = unicodedata.normalize("NFKC", claim.value.strip())
        if value_norm:
            anchors.add(value_norm)
        
        # Extract numeric tokens (standalone numbers)
        # Pattern: optional sign, digits with optional decimal point
        number_pattern = r'[-+]?\d+\.?\d*'
        for match in re.finditer(number_pattern, value_norm):
            anchors.add(match.group())
        
        # Note: unit_lexicon would come from protocol in actual usage
        # For this pure module, we extract <number><unit> pattern generically
        # The protocol.unit_lexicon check would be done by caller
        # Here we extract potential number-unit pairs for the set
        unit_pattern = r'([-+]?\d+\.?\d*)\s*([a-zA-Z%]+)'
        for match in re.finditer(unit_pattern, value_norm):
            number, unit = match.groups()
            # Add the combined form
            combined = f"{number}{unit}"
            anchors.add(combined)
    
    return anchors


def render_table(claims: list[Claim]) -> str:
    """
    §6 — Render markdown table grouped by outcome.
    
    Format per row: "study·RoB·weight·value·[claim_id]"
    
    Groups:
    1. Non-conflicting claims grouped by outcome_id
    2. Conflicting claims in separate block with header "CONFLICTING — not pooled"
    
    Returns markdown string.
    """
    lines = []
    
    # Separate conflicting and non-conflicting
    conflicting = [c for c in claims if c.conflict_group is not None]
    non_conflicting = [c for c in claims if c.conflict_group is None]
    
    # Group non-conflicting by outcome_id
    outcome_groups: dict[str, list[Claim]] = {}
    for claim in non_conflicting:
        outcome_groups.setdefault(claim.outcome_id, []).append(claim)
    
    # Render non-conflicting groups
    for outcome_id in sorted(outcome_groups.keys()):
        group = outcome_groups[outcome_id]
        lines.append(f"## {outcome_id}")
        lines.append("")
        lines.append("| Study | RoB | Weight | Value | Claim ID |")
        lines.append("|-------|-----|--------|-------|----------|")
        
        for claim in group:
            lines.append(
                f"| {claim.uid} | {claim.rob_overall} | {claim.weight:.2f} | "
                f"{claim.value} | [{claim.claim_id}] |"
            )
        lines.append("")
    
    # Render conflicting block
    if conflicting:
        lines.append("## CONFLICTING — not pooled")
        lines.append("")
        
        # Group conflicts by conflict_group
        conflict_groups: dict[str, list[Claim]] = {}
        for claim in conflicting:
            conflict_groups.setdefault(claim.conflict_group, []).append(claim)
        
        for conflict_group in sorted(conflict_groups.keys()):
            group = conflict_groups[conflict_group]
            outcome_id = group[0].outcome_id if group else "unknown"
            
            lines.append(f"### {outcome_id} ({conflict_group})")
            lines.append("")
            lines.append("| Study | RoB | Weight | Value | Direction | Claim ID |")
            lines.append("|-------|-----|--------|-------|-----------|----------|")
            
            for claim in group:
                direction_str = claim.direction or "NULL"
                lines.append(
                    f"| {claim.uid} | {claim.rob_overall} | {claim.weight:.2f} | "
                    f"{claim.value} | {direction_str} | [{claim.claim_id}] |"
                )
            lines.append("")
    
    return "\n".join(lines)
