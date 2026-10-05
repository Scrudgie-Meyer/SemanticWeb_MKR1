"""Execute the three Wikidata queries and save CSV results and answers."""
import csv
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
ENDPOINT = "https://query.wikidata.org/sparql"


def execute(query):
    for attempt in range(4):
        response = requests.get(
            ENDPOINT,
            params={"query": query, "format": "json"},
            headers={"User-Agent": "mkr1/1.0", "Accept": "application/sparql-results+json"},
            timeout=120,
        )
        if response.status_code in (429, 502, 503, 504) and attempt < 3:
            time.sleep(min(int(response.headers.get("Retry-After", "5")), 30))
            continue
        response.raise_for_status()
        data = response.json()
        columns = data["head"]["vars"]
        rows = [{col: row.get(col, {}).get("value", "") for col in columns}
                for row in data["results"]["bindings"]]
        return columns, rows


def main():
    results = {}
    note = None
    for name in ("q1", "q2", "q3"):
        path = ROOT / f"{name}.rq"
        query = path.read_text(encoding="utf-8")
        columns, rows = execute(query)
        if name == "q1" and len(rows) < 5:
            match = re.search(r"FILTER\(\?value > ([\d.]+)\)", query)
            threshold = float(match[1]) / 2
            query = query[:match.start(1)] + f"{threshold:g}" + query[match.end(1):]
            columns, rows = execute(query)
            path.write_text(query, encoding="utf-8")
            note = f"Примітка: Q1 повернув менше 5 рядків; поріг зменшено удвічі до {threshold:g} м."
        with (ROOT / f"{name}.csv").open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        results[name] = rows
        print(f"{name}.csv: {len(rows)} rows", flush=True)
    (ROOT / "meta.json").write_text(json.dumps(
        {"retrieved_at": datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
    answers = [
        f"Q1: {results['q1'][0]['itemLabel']} — {results['q1'][0]['value']} м." if results['q1'] else "Q1: результат порожній.",
        f"Q2: {results['q2'][0]['regionLabel']} — {results['q2'][0]['cnt']} об’єктів." if results['q2'] else "Q2: результат порожній.",
        f"Q3: {results['q3'][0]['population']}." if results['q3'] else "Q3: результат порожній.",
    ]
    if note:
        answers.append(note)
    (ROOT / "ANSWERS.md").write_text("\n".join(answers) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
