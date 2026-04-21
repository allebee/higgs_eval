# Rubric: Factual correctness

The agent's final answer must be factually correct **with respect to the
local corpus**. If FETCHED_PAGES is provided, treat that page text as
authoritative — the corpus may contain statements that differ from the
open-internet version of the same topic, and the agent is required to
match the corpus, not your background knowledge.

## How to evaluate

1. Extract the factual claims from the answer (dates, numbers, named
   entities, relationships).
2. For each claim, check it against FETCHED_PAGES if provided. If not,
   check against the `must_contain_claim` field and general plausibility.
3. Verify any `must_contain_claim` substance appears (paraphrase OK).

## Pass criteria
- Every factual claim in the answer is supported by a fetched page (or
  the broader corpus, if pages weren't fetched).
- `must_contain_claim` content is present (paraphrase OK, meaning must
  match).
- Numbers, dates, and named entities match the corpus.

## Fail criteria
- A claim contradicts a fetched page.
- A numeric value or date is wrong.
- The answer fabricates entities or facts not in any fetched page.
- `must_contain_claim` is missing or contradicted.

## Partial
- Directionally correct but omits a required claim or has a minor
  inaccuracy a reader would likely catch.

Be strict on numbers and dates; be lenient on phrasing.
