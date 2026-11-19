# The learning loop — how Nour gets better from its mistakes

The model (gpt-oss-120b on Groq) can't be retrained from here. What learns is the **system**: mistakes are caught, measured, corrected, and the corrections are shown to the model for similar questions.

```
user 👎 + picks the correct sentence ──► feedback (Supabase)
                                              │  reviewed in the admin notebook (steps 7–8)
                                              ▼
                       corrections (question vector + correct evidence + short answer)
                                              │  similar new question?
                                              ▼
              shown to the model as a worked example before the passages
golden set (eval/golden.jsonl) ◄── each accepted mistake becomes a test
       │
       ▼  scripts/evaluate.py --llm --save  →  eval_runs: scores per version
```

## Your part: `backend/app/learning.py`

Three functions, each with a docstring describing inputs and expected behavior. Until one is written it raises `NotImplementedError` and the code around it degrades safely (nothing breaks in production).

| Function | Used by | What it decides |
|---|---|---|
| `evidence_matches(quote, expected)` | evaluation | Is the quoted sentence the expected evidence? (catches "right passage, wrong sentence") |
| `pick_corrections(candidates, min_similarity, max_examples)` | each answer | Which past corrections are close enough to show as examples |
| `format_example(correction)` | each answer | How a correction is written into the prompt |

Check your work: `cd backend && pytest -q tests/test_learning.py`. The tests are skipped while a function isn't written and run once it is. They include tonight's real mistake (the «ومن نسي السجود القبلي…» sentence must not count as «فللنقصان سجدتان قبل السلام»).

## Switching it on

1. Run `backend/supabase/learning.sql` once in the Supabase SQL Editor (tables `feedback`, `corrections`, `eval_runs`).
2. Deploy. The 👍 / 👎 buttons work right away; reports are stored but change nothing until reviewed.
3. Write `evidence_matches`, then run notebook step 5 to get a baseline score.
4. Write `pick_corrections` and `format_example`, then on Vercel set `USE_CORRECTIONS=true` and redeploy.
5. After each change, re-run step 5 with a new `--label` and compare in step 6. Keep a change only if the scores don't go down.

Settings (Vercel environment variables): `USE_CORRECTIONS` (default `false`), `CORRECTION_MIN_SIMILARITY` (default `0.85`), `MAX_CORRECTION_EXAMPLES` (default `2`).

## Good to know

- **Who can write feedback:** anyone using the site. `/api/feedback` limits sizes and checks that a picked sentence really exists in that unit, but nothing reaches the model until you accept it in the notebook. If spam appears, add a rate limit or a simple captcha.
- **Cost:** each correction example adds tokens to the prompt (Groq free tier: about 8,000 tokens per minute). Keep examples short and `MAX_CORRECTION_EXAMPLES` low.
- **A correction is not a fatwa:** it only says which sentence of *these two books* answers a question. The model must still quote from the retrieved passages, never from the examples: a quote that is only in an example fails the grounding check.
