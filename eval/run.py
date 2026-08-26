#!/usr/bin/env python3
"""Mierzy trafnosc routingu: python eval/run.py"""

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

import httpx
import yaml

CASES = Path(__file__).parent / "cases.yaml"
DEPARTMENTS = ["it", "help_desk", "human_resources", "kadry", "other"]


def clear_mailbox(mailhog: str) -> None:
    try:
        httpx.delete(f"{mailhog}/api/v1/messages", timeout=5)
    except httpx.HTTPError:
        print(f"! nie udalo sie wyczyscic skrzynki ({mailhog}) - stare maile zostaja")


def model_name(api: str) -> str:
    try:
        return httpx.get(f"{api}/api/v1/health", timeout=5).json()["model"]
    except (httpx.HTTPError, KeyError):
        return "?"


def run_case(client: httpx.Client, api: str, index: int, message: str) -> dict:
    started = time.perf_counter()
    response = client.post(
        f"{api}/api/v1/route",
        json={"email": f"eval+{index:02d}@example.com", "message": message},
    )
    elapsed = time.perf_counter() - started

    if response.status_code != 200:
        return {"got": None, "routed_by": None, "model_output": "",
                "seconds": elapsed, "error": f"HTTP {response.status_code}"}

    body = response.json()
    return {"got": body["department"], "routed_by": body["routed_by"],
            "model_output": body.get("model_output") or "",
            "seconds": elapsed, "error": None}


def print_matrix(rows: list[dict]) -> None:
    counts = Counter((r["expected"], r["got"]) for r in rows if r["got"])
    width = max(len(d) for d in DEPARTMENTS) + 2

    print("\nMacierz pomylek (wiersz = oczekiwany, kolumna = otrzymany)")
    print(" " * width + "".join(f"{d[:9]:>11}" for d in DEPARTMENTS))
    for expected in DEPARTMENTS:
        line = f"{expected:<{width}}"
        for got in DEPARTMENTS:
            n = counts[(expected, got)]
            line += f"{n if n else '.':>11}"
        print(line)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--mailhog", default="http://localhost:8025")
    parser.add_argument("--threshold", type=float, default=0.8,
                        help="ponizej tej trafnosci skrypt konczy sie kodem 1")
    parser.add_argument("--keep-mail", action="store_true",
                        help="nie czysc skrzynki przed przebiegiem")
    args = parser.parse_args()

    cases = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    if not args.keep_mail:
        clear_mailbox(args.mailhog)

    print(f"Model: {model_name(args.api_url)} | przypadkow: {len(cases)}\n")

    rows = []
    with httpx.Client(timeout=180) as client:
        for i, case in enumerate(cases):
            result = run_case(client, args.api_url, i, case["message"])
            result["expected"] = case["expected"]
            result["message"] = case["message"]
            rows.append(result)

            ok = "OK " if result["got"] == case["expected"] else "BLAD"
            print(f"  [{i + 1:2}/{len(cases)}] {ok} {result['seconds']:5.1f}s  "
                  f"{case['message'][:44]:46} -> {result['got'] or result['error']}")
            reply = result["model_output"].replace("\n", " ").strip()
            if reply:
                print(f"          {reply[:100]}")
            elif result["routed_by"] == "fallback":
                print("          (brak tool_call — fallback)")

    hits = sum(1 for r in rows if r["got"] == r["expected"])
    fallbacks = sum(1 for r in rows if r["routed_by"] == "fallback")
    errors = [r for r in rows if r["error"]]
    accuracy = hits / len(rows)
    avg = sum(r["seconds"] for r in rows) / len(rows)

    print(f"\nTrafnosc: {hits}/{len(rows)} ({accuracy:.0%})")
    print(f"Fallback: {fallbacks}/{len(rows)}   (model nie wybral dzialu)")
    print(f"Sredni czas: {avg:.1f} s")
    if errors:
        print(f"Bledy HTTP: {len(errors)}")

    print_matrix(rows)

    misses = [r for r in rows if r["got"] and r["got"] != r["expected"]]
    if misses:
        print("\nPomylki:")
        for r in misses:
            print(f'  "{r["message"][:52]}"')
            print(f"      {r['expected']} -> {r['got']}")

    return 0 if accuracy >= args.threshold else 1


if __name__ == "__main__":
    sys.exit(main())
