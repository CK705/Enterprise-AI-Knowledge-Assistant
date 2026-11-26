"""Collect authenticated pipeline outputs for offline evaluation."""

import argparse
import getpass
import os
from pathlib import Path

import pandas as pd
import requests

DATASET = Path(__file__).resolve().parent / "data_and_results" / "dataset.csv"
ENDPOINTS = {
    "Pipeline_A": "/query/naive",
    "Pipeline_B": "/query/hybrid",
    "Pipeline_C": "/query/multihop",
    "Pipeline_D": "/query/self_correct",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--encoding", default="cp1252")
    parser.add_argument("--base-url", default="http://localhost:8001")
    parser.add_argument("--ids", nargs="+", required=True, help="Explicit dataset case IDs")
    parser.add_argument("--username", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.output.exists():
        parser.error("--output must name a new file")
    cases = pd.read_csv(args.dataset, encoding=args.encoding, dtype={"ID": str})
    if cases["ID"].duplicated().any():
        parser.error("Dataset contains duplicate case IDs")
    cases = cases.set_index("ID", drop=False)
    unknown = set(args.ids).difference(cases.index)
    if unknown or len(set(args.ids)) != len(args.ids):
        parser.error(f"Select unique, known case IDs. Unknown IDs: {sorted(unknown)}")

    base_url = args.base_url.rstrip("/")
    password = os.getenv("RAG_EVAL_PASSWORD") or getpass.getpass("Benchmark password: ")
    results = []
    failed = False
    with requests.Session() as session:
        try:
            login = session.post(
                f"{base_url}/api/documents/login",
                json={"username": args.username, "password": password},
                timeout=15,
            )
            login.raise_for_status()
            identity = login.json()
            session.headers["Authorization"] = f"Bearer {identity['access_token']}"
            role = identity["role"]
        except (requests.RequestException, ValueError, KeyError) as exc:
            parser.exit(1, f"Benchmark login failed: {exc}\n")

        for _, case in cases.loc[args.ids].iterrows():
            result = case.to_dict()
            result["Role"] = role
            for name, endpoint in ENDPOINTS.items():
                result[f"{name}_Error"] = ""
                try:
                    response = session.post(
                        base_url + endpoint, json={"question": case["Question"]}, timeout=120
                    )
                    response.raise_for_status()
                    data = response.json()
                    result[f"{name}_Answer"] = data["answer"]
                    result[f"{name}_Latency"] = data.get("latency")
                    tokens = data.get("tokens") or {}
                    result[f"{name}_Tokens"] = tokens.get("total_tokens")
                    result[f"{name}_Context"] = "\n".join(data.get("retrieved_chunks") or [])
                except (requests.RequestException, ValueError, KeyError) as exc:
                    failed = True
                    result[f"{name}_Error"] = str(exc)
                    print(f"Case {case['ID']} {name}: {exc}", flush=True)
            results.append(result)
            pd.DataFrame(results).to_csv(
                args.output, index=False, encoding="utf-8", mode="x" if len(results) == 1 else "w"
            )
            print(f"Saved case {case['ID']} ({len(results)}/{len(args.ids)})", flush=True)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
