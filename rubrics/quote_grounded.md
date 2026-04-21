# Rubric: Quote-grounded answer (faithfulness)

**You will be given the fetched page text in FETCHED_PAGES.** Use it as the
authoritative source of truth. Do not guess whether quotes are paraphrased —
check them against the provided page text.

## How to evaluate

1. Identify every quoted passage in the answer (text in quotation marks).
2. For each quote, search FETCHED_PAGES for a verbatim or near-verbatim
   match (ignore whitespace differences, smart-quote normalization, and
   minor punctuation). A match is "verbatim" if the distinctive content
   words appear in the same order on some fetched page.
3. Identify every specific factual claim (dates, numbers, named entities).
   For each, confirm that a fetched page supports that claim.
4. Check that every URL in `citations` was actually fetched (i.e. appears
   as a key in FETCHED_PAGES). A citation that was not fetched is a fail.

## Pass criteria
- Every quoted passage matches text in some fetched page (verbatim,
  allowing the normalizations above).
- Every specific factual claim is supported by at least one fetched page.
- All cited URLs appear in FETCHED_PAGES.

## Fail criteria
- Any quoted passage does **not** appear verbatim in any fetched page — it
  has been paraphrased, summarized, or fabricated. This is the primary
  faithfulness failure we want to catch.
- A specific claim (number, date, entity) is not supported by any fetched
  page.
- A cited URL does not appear in FETCHED_PAGES.

## Partial
- Main claims are grounded, but one peripheral claim or one non-essential
  stylistic paraphrase is present.

## Notes

One URL can legitimately source multiple claims when all of them come from
that page — do not penalize citation count. The question is strictly:
"does the fetched page support this content?"

If FETCHED_PAGES is empty (the agent did not fetch anything), this rubric
becomes "does the answer look grounded in *something* plausible?" — in that
case, a cite-less answer with specific claims should be a fail.
