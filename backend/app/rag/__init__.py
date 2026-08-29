# RAG package (app.rag)
#
# Separate RAG module for the repository. Sub-modules:
#   rag_knowledge.py  -> curated "issues & remedies" runbook + corpus (static / retrieval index)
#   rag.py            -> the RAG engine: retrieval + LLM grounding for admin Q&A
#   rag_pipeline.py   -> orchestration: gathers live context (user_db, events, feedback,
#                        verification, metrics) and feeds it to the RAG engine
#
# Re-exported here so the rest of the backend can simply do:
#   from app.rag import get_rag, ask_admin, pipeline_status
from app.rag.rag import get_rag
from app.rag.rag_pipeline import ask_admin, pipeline_status
from app.rag import rag_knowledge
