"""
evaluation/langsmith_upsert_dataset.py — sync a checked-in JSON fixture into LangSmith
========================================================================================
The JSON file under evaluation/langsmith_datasets/ is the source of truth, not
LangSmith. On each run, existing examples for the named dataset are deleted and
recreated from the file. Do NOT hand-edit examples in the LangSmith UI -- they
will be silently clobbered on the next upsert.

Import boundary: evaluation/ -> rag/, db/, standard library only (AGENTS.md).

CLI usage:
    py -m evaluation.langsmith_upsert_dataset
    py -m evaluation.langsmith_upsert_dataset --file evaluation/langsmith_datasets/permit_rag_security_v1.json
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_DATASET_PATH = Path("evaluation/langsmith_datasets/permit_rag_eval_v1.json")


def upsert_dataset(json_path: Path = DEFAULT_DATASET_PATH) -> str:
    """Create-or-update a LangSmith dataset from the checked-in JSON fixture.

    Returns the dataset ID.
    """
    from langsmith import Client

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    dataset_name = payload["dataset_name"]
    description = payload.get("description", "")
    examples = payload["examples"]

    client = Client()

    try:
        dataset = client.read_dataset(dataset_name=dataset_name)
        log.info("Dataset %r already exists (id=%s)", dataset_name, dataset.id)
        existing = list(client.list_examples(dataset_id=dataset.id))
        if existing:
            client.delete_examples(example_ids=[ex.id for ex in existing])
            log.info("Deleted %d existing example(s) before re-upsert", len(existing))
    except Exception:
        dataset = client.create_dataset(dataset_name=dataset_name, description=description)
        log.info("Created dataset %r (id=%s)", dataset_name, dataset.id)

    client.create_examples(
        inputs=[ex["inputs"] for ex in examples],
        outputs=[ex["outputs"] for ex in examples],
        dataset_id=dataset.id,
    )
    log.info("Upserted %d example(s) into %r", len(examples), dataset_name)
    return str(dataset.id)


if __name__ == "__main__":
    import argparse

    from api.load_env import bootstrap_env

    bootstrap_env()

    parser = argparse.ArgumentParser(description="Upsert a permit_rag eval dataset into LangSmith")
    parser.add_argument("--file", type=Path, default=DEFAULT_DATASET_PATH)
    args = parser.parse_args()

    logging.basicConfig(level="INFO", format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")

    dataset_id = upsert_dataset(args.file)
    print(f"Dataset ready: {dataset_id}")
