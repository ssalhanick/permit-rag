"""Quick test: chunk the Dallas charter and print stats."""
from ingestion.chunker import chunk_document

r = chunk_document("city-of-dallas-charter")

print(f"\nChunks:  {r['num_chunks']}")
print(f"Chars:   {r['clean_chars']:,}")
print(f"Scanned: {r['is_scanned']}")

if r["chunks"]:
    first = r["chunks"][0]
    print(f"\nFirst chunk ({first['char_count']} chars):")
    print(first["content"][:300])
