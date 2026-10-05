# Retrieval tools

Retrieval is a tool, not a stage of the pipeline. The agent decides that it lacks an answer, calls an allowed search tool, receives a small list of references with scores, and only then loads the text of the chunks it actually needs.

## Two steps instead of one

A search tool returns references, short snippets and similarity scores. A separate read tool loads the full text of one chunk by identifier. Splitting the two steps keeps the context budget under control and gives the runtime a place to log what was searched and what was read.

## Never send the whole corpus

Injecting every document into every model call is the most common way to make a retrieval feature expensive and unreliable. Only the context required for the current task belongs in the prompt; everything else stays in the index until a query needs it.

## When nothing relevant is found

A similarity score below a configured threshold means the corpus does not answer the question. The agent must report insufficient context and stop, instead of writing a confident answer from its own prior knowledge. A retrieval tool that always returns something trains the workflow to invent.

## Provenance

Every retrieved fragment keeps the document name, the section heading and the chunk identifier. Two retrieved chunks may quote the same source document, so provenance travels with each chunk instead of with the answer. Citations are built from those fields, so an operator can open the source and check the claim.
