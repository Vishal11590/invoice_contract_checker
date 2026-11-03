# Invoice vs contract checker

A small prototype for my Tresata take-home. It checks the lines on a vendor invoice against the rates in a signed contract (MSA) and says what is wrong, how much money it is, and where in each document to look.

Everything here is made up: the vendor, the contract, the amendment, the invoice and the page references. No real client data.

## How to run it

You need Python 3.8 or newer (check with `python --version`). There is nothing to install.

1. Download or clone this repo and open a terminal in the folder.
2. Run the three scripts:

```
python audit.py         # report for the sample invoice (about 1 second)
python test_audit.py    # all the examples, 10 tests, should end with OK
python bench.py         # rough speed of the rules part (about 2 seconds)
```

On Mac or Linux use `python3` if `python` is not found.

What you should see: `audit.py` ends with `Confirmed loss: $11100.00` and `Waiting for a person: L07, L12`. `test_audit.py` ends with `OK`. Saved copies of my runs are in `sample_output.txt`, `test_output.txt` and `bench_output.txt`.

These three scripts use the hard-coded table in place of an AI model, so they need no key and no internet.

### Optional: run it with a real model

1. Make a free account on OpenRouter and create an API key.
2. Copy `.env.example` to a new file named `.env`.
3. Put your key after `OPENROUTER_API_KEY=` and a free model id after `OPENROUTER_MODEL=`.
4. `python try_llm.py` compares the model with a person's answers on 7 invoice wordings.
5. Set `USE_LLM=1` in `.env` and run `python audit.py` to send the whole invoice through the model.

`.env` is listed in `.gitignore`. Never commit it and never paste a key into a file you upload.

## What is real and what is not

| Part | Status |
|---|---|
| Rate lookup by service date (so an amendment only applies from its start date) | real code |
| Money maths with `Decimal`, volume discount, duplicate check | real code |
| Currency gate, low-confidence gate, grounding check, citations on each finding | real code |
| The AI step (matching "Sr. Cloud Architect" to "Level 4 Engineer") | **mocked**: a hard-coded table in `MOCK_MAP` |
| `map_line_llm()` (OpenRouter call) | written, **never run**. I had no API key |

**No AI model was used for any result in this repo**, so none of it says anything about how accurate a real model would be. To try a real model, run `try_llm.py` (next section). The model only picks an item from a fixed list and gives a confidence. It never sees an amount.

## Trying a real model

The model only picks an item from a fixed list and gives a confidence. It never sees an amount. Replies outside the list, or errors, count as confidence 0, which sends the line to a person. `try_llm.py` counts answers that are correct, sent to a person, and *confidently wrong*, which is the dangerous kind (see F1 below). The tests and the speed check always use the mock.

Results from a real model: none yet. If I run it, the model id and the counts go here.

## Examples I tested (16)

The sample invoice has 13 lines. I knew the right answer for each before running.

| Line | What I planted | What the checker says | Loss |
|---|---|---|---|
| L01 | correct line | OK | 0 |
| L02 | billed 120/h, contract 100/h | RATE_TOO_HIGH | 1,600 |
| L03 | "Sr. Cloud Architect", correct | OK | 0 |
| L04 | "Tech Support Fee", not in contract | NOT_IN_CONTRACT | 500 |
| L05 | 100 h x 150 billed as 15,500 | MATH_ERROR | 500 |
| L06 | 200 h, discount missing | DISCOUNT_MISSED | 400 |
| L07 | "Consultant (misc)", vague | NEEDS_REVIEW | 0 |
| L08 | billed under the contract rate | BELOW_CONTRACT | 0 |
| L09 | same as L01 | DUPLICATE | 8,000 |
| L10 | amended rate used before it starts | RATE_TOO_HIGH | 100 |
| L11 | amended rate after it starts | OK | 0 |
| L12 | billed in EUR, contract is USD | NEEDS_REVIEW | 0 |
| L13 | 200 h, discount applied | OK | 0 |

All 13 match. Confirmed loss is $11,100. Two lines (L07, L12) wait for a person and are not counted in that number.

Three grounding tests also pass: the real terms are accepted, an invented rate (105) is rejected, and a wrong discount (15% when the text says 10%) is rejected.

L13 exists because my first version got it wrong. A 200,000-line run flagged every correctly discounted line as a maths error, and my first twelve lines only had a tier line where the discount was missing.

## Where it fails

Three more examples, where the checker is wrong. The tests assert the wrong answer so the problem stays visible.

| | Case | Checker says | Truth |
|---|---|---|---|
| F1 | "Cloud Architect" billed correctly at 185, but the mapper is confidently wrong | RATE_TOO_HIGH, $850 (false alarm) | OK |
| F2 | 100 h + 100 h of Project Manager in one month, clause is "over 160 h a month" | both lines OK | $600 overbilled |
| F3 | Same 80 h billed twice, second date is one day later | both lines OK | duplicate, $8,000 |

Other limits:
- The confidence gate only helps when the model knows it is unsure. F1 shows what happens when it is wrong and sure.
- The discount is applied per line. Real contracts usually say per month.
- No PDF reading. The citations are strings, not real page coordinates, and the "source text" the grounding check reads is typed in by hand.
- The grounding check only knows three patterns: `USD <number>`, `above <number>` and `<number>%`. Real clauses are messier.
- The 13 lines were written by me next to the code, so this is a sanity check and not a benchmark.
- Speed: about 100,000 lines a second on one core (91,000 to 105,000 over three runs), with the mock mapper and everything in memory. A real model call would be far slower, which is why the design caches it.

## Files

- `audit.py`: terms, mock AI step, checks, report
- `test_audit.py`: the 16 examples plus grounding tests
- `bench.py`: speed check
- `try_llm.py`: compares a real model with the mock (needs your own key)
- `.env.example`: copy to `.env` for your key (never commit `.env`)
- `architecture.png`: the design diagram from the brief
