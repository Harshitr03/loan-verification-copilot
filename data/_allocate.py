from __future__ import annotations
from math import ceil


def plan_row_defects(row_rule_ids, eligible_indices, rng, n_loans,
                     per_type=35, defect_rate=0.10, max_per_row=2, footprints=None):
    """Map loan index -> ROW rule-ids (<= max_per_row each), spread across
    ~defect_rate*n_loans distinct rows.

    Two defects share a row only if their field `footprints` are disjoint, so a
    later corrupt never blanks a field an earlier one needs (crash) or heals an
    earlier defect (masking) -- either of which would break the superset oracle.
    `footprints=None` disables the check (original behavior; keeps callers that
    don't care backward-compatible)."""
    fp = footprints or {}
    flat = [rid for rid in row_rule_ids for _ in range(per_type)]
    rng.shuffle(flat)

    budget = round(defect_rate * n_loans)
    needed = ceil(len(flat) / max_per_row)
    n_rows = min(len(eligible_indices), max(budget, needed))

    order = [int(x) for x in rng.permutation(eligible_indices)]
    empty_rows = order[:n_rows]        # spread targets: each seeded with one defect first
    spare_rows = order[n_rows:]        # fallback when a defect fits no existing row

    def footprint(rid):
        return set(fp.get(rid, ()))

    assign: dict[int, list[str]] = {}
    occupied: dict[int, set] = {}      # row -> union of footprints on that row
    ei = si = 0

    for rid in flat:
        f = footprint(rid)
        # 1) prefer a fresh row -> maximizes spread (defect_rate stays meaningful)
        if ei < len(empty_rows):
            row = empty_rows[ei]; ei += 1
            assign[row] = [rid]; occupied[row] = set(f)
            continue
        # 2) else stack onto an existing row with room and a disjoint footprint
        placed = False
        for row, rids in assign.items():
            if len(rids) < max_per_row and rid not in rids and f.isdisjoint(occupied[row]):
                rids.append(rid); occupied[row] |= f; placed = True
                break
        if placed:
            continue
        # 3) else open a spare eligible row (a new 1-defect row)
        if si < len(spare_rows):
            row = spare_rows[si]; si += 1
            assign[row] = [rid]; occupied[row] = set(f)
        # (if no spare remains, drop; eligible pools are far larger than needed here)

    return {k: v for k, v in assign.items() if v}
