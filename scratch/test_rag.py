import os
import sys
import logging
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
load_dotenv()

print("DATABASE_URL:", os.environ.get("DATABASE_URL"))
print("LLM_PROVIDER:", os.environ.get("LLM_PROVIDER"))
print("LLM_MODEL:", os.environ.get("LLM_MODEL"))
print("ANTHROPIC_API_KEY set:", bool(os.environ.get("ANTHROPIC_API_KEY")))

from rag.retriever import retrieve
from rag.generator import generate_answer

query = "What are the setback requirements for a residential fence in Dallas?"
print("\n--- Testing Retrieval ---")
result = retrieve(query, top_k=10, municipality="dallas")
print(f"Retrieved {len(result.chunks)} chunks.")
for i, chunk in enumerate(result.passing_chunks):
    print(f"Chunk {i}: doc_id={chunk['doc_id']}, chunk_index={chunk['chunk_index']}, similarity={chunk.get('similarity')}")

print("\n--- Testing Generation ---")
gen = generate_answer(query, result.chunks)
print("\n--- Answer ---")
print(gen.answer)
print("\nCitations:", gen.citations)
