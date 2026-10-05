"""Retrieval tool, grounded answering loop and a small RAG evaluation set."""

from rag_lab.agent import AnswerRun, ExtractiveAnswerer, run_question
from rag_lab.chunking import ingest_directory
from rag_lab.evaluation import evaluate, load_cases
from rag_lab.store import VectorStore, build_index
from rag_lab.tools import RetrievalTools

__all__ = [
    "AnswerRun",
    "ExtractiveAnswerer",
    "RetrievalTools",
    "VectorStore",
    "build_index",
    "evaluate",
    "ingest_directory",
    "load_cases",
    "run_question",
]