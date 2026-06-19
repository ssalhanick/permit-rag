import os
from dotenv import load_dotenv
from db.client import get_conn

load_dotenv()

with get_conn() as conn:
    # Check documents
    docs = conn.execute("SELECT id, doc_id, municipality, document_status FROM documents;").fetchall()
    print(f"Total documents: {len(docs)}")
    for d in docs:
        print(f" - {d['doc_id']} ({d['municipality']}): status={d['document_status']}")
        
    # Check chunks
    chunks_count = conn.execute("SELECT count(*) as n FROM chunks;").fetchone()
    print(f"Total chunks: {chunks_count['n']}")
    
    # Check if there are embeddings
    emb_count = conn.execute("SELECT count(*) as n FROM chunks WHERE embedding IS NOT NULL;").fetchone()
    print(f"Chunks with embeddings: {emb_count['n']}")
