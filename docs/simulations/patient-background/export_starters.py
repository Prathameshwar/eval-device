"""Export reviewable background restoration drafts; no database/provider writes."""

import argparse
import json
from pathlib import Path

from training_contracts.conversation.background import restore_starter_background


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    source = root / "platform/api/migrations/versions/0014_patient_case_templates.json"
    rows = json.loads(source.read_text(encoding="utf-8"))
    result = [
        {"code": row["code"], "document": restore_starter_background(row["document"])}
        for row in rows
        if row["code"] in {"alex_chest_discomfort", "alex_wheeze"}
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
    print(f"Exported {len(result)} unreviewed starter drafts")


if __name__ == "__main__":
    main()
