"""The feedback flywheel (Design.md §10).

    "Feedback loop RAG system ko static se living system banata hai — main ise
     as a data flywheel treat karta hoon: production failures -> labeled data
     -> retrieval/reranker fine-tuning -> better system."

    triage.py   classify a thumbs-down: retrieval, generation, or stale data

The classification lives in its own module (not in the script that prints it)
so it is a pure function over trace data — testable without a database, and
reusable by anything else that wants to know why an answer was bad.
"""
