"""Answer generation (Design.md §2 steps 2-11, §7).

The query path from a resolved question to a cited, validated answer:

    rewriter.py    multi-turn follow-up -> standalone query (§2 step 2)
    gate.py        confidence check BEFORE generation (§7 technique 5)
    prompts.py     the closed-book prompt, context block, few-shot abstention
    generator.py   grounded generation, streaming, abstention detection
    citations.py   parse [n] markers, verify each one post-hoc (§7)
    escalation.py  the abstain path's durable record (§2 branch A)
    pipeline.py    orchestration + tracing

Read them in that order; each depends only on the ones above it.

The design principle running through all of it (Design.md §7's closing line):
hallucination is not solved by prompt engineering. It is defended in layers —
retrieval confidence gate, then grounded prompt, then post-hoc citation
validation — and no single layer is trusted on its own.
"""
