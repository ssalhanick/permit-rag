# DFW Construction Document Harvester

Downloads, names, and tags all municipal permit/zoning documents
for Dallas, Plano, Frisco, McKinney, Fort Worth + Texas state + federal sources.
Outputs a master registry.json with full governance metadata ready to attach
to your pgvector chunks.

---

## Setup

```bash
pip install -r requirements.txt
python ingestion.harvester.py harvest
```

---

## Commands

### Download everything

```bash
python ingestion.harvester.py harvest
```

### Force re-download even if unchanged

```bash
python ingestion.harvester.py harvest --force
```

### Check all sources for changes (run weekly)

```bash
python ingestion.harvester.py monitor
```

### Print governance summary

```bash
python ingestion.harvester.py report
```

---

## Output structure

```
documents/
  raw/
    dallas-municode-zoning.html
    dallas-building-permit-checklist.pdf
    osha-1926-construction.html
    ...
  metadata/
    dallas-municode-zoning.json       <- governance sidecar per doc
    dallas-building-permit-checklist.json
    ...
  registry.json                       <- master registry (all docs)
  harvest.log
```

---

## Metadata schema (attaches to every pgvector chunk)

```json
{
  "doc_id": "dallas-zoning-ord-2024-03",
  "source_url": "https://...",
  "municipality": "dallas",
  "authority_level": "municipal",
  "doc_type": "zoning_ordinance",
  "subject_tags": ["easements", "setbacks", "residential"],
  "effective_date": "2024-03-01",
  "document_status": "active",
  "is_current": true,
  "retrieval_weight": 1.0,
  "review_due": "2024-06-01",
  "checksum_sha256": "a3f9...",
  "source_etag": "\"abc123\"",
  "ingested_at": "2024-05-01T14:22:00Z"
}
```

---

## Marking a document as superseded

When a city publishes a new version of a code:

```python
from dfw_doc_harvester import mark_superseded

mark_superseded(
    old_doc_id="dallas-zoning-ord-2022-11",
    new_doc_id="dallas-zoning-ord-2024-03"
)
```

This sets the old doc to `retrieval_weight: 0.1` so it's heavily
deprioritized in RAG retrieval but still queryable for historical queries.

---

## Adding new documents

Add an entry to `DOCUMENT_CATALOG` in `dfw_doc_harvester.py`:

```python
{
    "doc_id":          "allen-municode-zoning",
    "url":             "https://library.municode.com/tx/allen/codes/code_of_ordinances",
    "municipality":    "allen",
    "authority_level": "municipal",
    "doc_type":        "zoning_ordinance",
    "subject_tags":    ["zoning", "land-use", "setbacks"],
    "version":         None,
    "notes":           "Allen TX municipal code via Municode",
    "review_days":     90,
},
```

Then run `python dfw_doc_harvester.py harvest`.

---

## Weekly monitoring (cron)

Add to your crontab to run every Monday at 7am:

```
0 7 * * 1 cd /path/to/project && python dfw_doc_harvester.py monitor >> harvest.log 2>&1
```

Or deploy as AWS Lambda + EventBridge rule for production.

---

## Next step: chunking + embedding

Once documents are harvested, pipe them into your RAG chunker:

```python
import json
from pathlib import Path

registry = json.loads(Path("documents/registry.json").read_text())

for doc_id, meta in registry.items():
    if meta["document_status"] != "active":
        continue
    raw_path = Path("documents") / meta["local_path"]
    # Pass raw_path + meta to your LangChain / LlamaIndex chunker
    # Attach meta as chunk metadata in pgvector
```
