#!/usr/bin/env python3
"""
Phase 17: real, deterministic 1D cutting-stock solving for Cutlist
Optimization Agent — never a model-asserted layout. A real first-fit-
decreasing (FFD) bin-packing heuristic: sorts required cut lengths
descending, packs each into the first bin (stock length) with enough
remaining room (accounting for blade kerf between cuts), opening a new
bin only when none fits. Honest about what it is: a real, deterministic
heuristic, not a proven-optimal solver — the "algorithm" field in the
output says so explicitly.

Usage: cutlist_solver.py <stock_length> <cut_lengths_json> [kerf]
Prints {"bins": [[...]], "bins_used": N, "waste_total": X, "algorithm": "first_fit_decreasing"}
on success, {"error": "..."} with exit 1 on failure.
"""
import json
import sys


class InvalidInput(Exception):
    pass


def solve(stock_length: float, cut_lengths: list[float], kerf: float = 0.0) -> dict:
    if stock_length <= 0:
        raise InvalidInput(f"stock_length must be positive: {stock_length}")
    if kerf < 0:
        raise InvalidInput(f"kerf cannot be negative: {kerf}")
    for length in cut_lengths:
        if length <= 0:
            raise InvalidInput(f"cut length must be positive: {length}")
        if length > stock_length:
            raise InvalidInput(f"cut length {length} exceeds stock_length {stock_length} — no bin could ever fit it")

    remaining_by_bin: list[float] = []
    bins: list[list[float]] = []

    for length in sorted(cut_lengths, reverse=True):
        placed = False
        for i, remaining in enumerate(remaining_by_bin):
            needed = length if not bins[i] else length + kerf
            if needed <= remaining:
                bins[i].append(length)
                remaining_by_bin[i] -= needed
                placed = True
                break
        if not placed:
            bins.append([length])
            remaining_by_bin.append(stock_length - length)

    waste_total = sum(remaining_by_bin)
    return {
        "bins": bins,
        "bins_used": len(bins),
        "waste_total": round(waste_total, 6),
        "waste_per_bin": [round(r, 6) for r in remaining_by_bin],
        "algorithm": "first_fit_decreasing",
    }


def main():
    if len(sys.argv) not in (3, 4):
        print(json.dumps({"error": "usage: cutlist_solver.py <stock_length> <cut_lengths_json> [kerf]"}))
        sys.exit(1)
    try:
        stock_length = float(sys.argv[1])
        cut_lengths = json.loads(sys.argv[2])
        if not isinstance(cut_lengths, list):
            raise ValueError("cut_lengths_json must be a JSON array")
        kerf = float(sys.argv[3]) if len(sys.argv) == 4 else 0.0
    except (ValueError, json.JSONDecodeError) as e:
        print(json.dumps({"error": f"invalid input: {e}"}))
        sys.exit(1)

    try:
        result = solve(stock_length, cut_lengths, kerf)
    except InvalidInput as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
