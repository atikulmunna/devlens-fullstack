# Model Selection: Chat and Summary

Decision (2026-10-15): **`openai/gpt-4.1-mini` for both chat answers (`LLM_CHAT_MODEL`) and the
architecture summary (`LLM_SUMMARY_MODEL`)**, through OpenRouter. It scored best in every graded
round. `google/gemini-2.5-flash-lite` is the fallback if cost ever outweighs quality: close behind
in the latest chat round at about a quarter of the price.

Total spend across all three rounds: under $0.03.

## Method

- Real retrieval on locally indexed repos, the production prompt for each task, the same contexts
  for every model in a question.
- Answers shuffled under letters and graded 0 to 3 before unmasking: correct against the code,
  honest about gaps in the evidence, citations that point at the right context. Grading by the
  agent that built the pipeline, against the code it was reading.
- Cost from OpenRouter's reported usage; time is the full non-streamed response.

Prices at the time (per million tokens, input / output): gpt-4.1-mini $0.40 / $1.60,
gpt-4o-mini $0.15 / $0.60, gpt-4.1-nano $0.10 / $0.40, gemini-2.5-flash-lite $0.10 / $0.40,
qwen3-235b-a22b-2507 $0.09 / $0.55.

## Round 1 (2026-10-10): chat, a famous repo

Production prompt and retrieval on `pallets/itsdangerous`, 5 questions, 6 models. All six answered
all five correctly, which says more about the repo (models know it from training) than the models.

| Model | Cost per 5 answers | First token | Total |
|---|---:|---:|---:|
| openai/gpt-4o-mini | $0.00153 | 2.15 s | 3.24 s |
| openai/gpt-4.1-nano | $0.00098 | 1.48 s | 2.39 s |
| google/gemini-2.5-flash-lite | $0.00099 | 2.89 s | 3.23 s |
| mistralai/mistral-small-3.2-24b-instruct | $0.00087 | 1.67 s | 4.15 s |
| qwen/qwen3-coder-30b-a3b-instruct | $0.00073 | 1.97 s | 6.76 s |
| qwen/qwen3-235b-a22b-2507 | $0.00164 | 1.85 s | 5.84 s |

## Round 2 (2026-10-10): chat, unknown code, graded blind

DevLens's own code (unknown to every model), 6 hard questions including a hallucination trap.

| Model | Score /18 | Per question | Cost / 6 answers | Total time |
|---|---:|---|---:|---:|
| openai/gpt-4.1-mini | 16 | 3, 2, 3, 2, 3, 3 | $0.00483 | 2.65 s |
| qwen/qwen3-235b-a22b-2507 | 15 | 3, 3, 2, 1, 3, 3 | $0.00216 | 9.68 s |
| openai/gpt-4o-mini | 14 | 3, 1, 3, 1, 3, 3 | $0.00174 | 3.22 s |
| google/gemini-2.5-flash-lite | 13 | 3, 0, 3, 1, 3, 3 | $0.00126 | 2.67 s |
| openai/gpt-4.1-nano | 12 | 3, 1, 2, 0, 3, 3 | $0.00118 | 2.24 s |

Round 1's apparent winner (gpt-4.1-nano) came last: it confidently invented an answer. No model fell
for the trap. Chat moved to gpt-4.1-mini after this round.

## Round 3 (2026-10-15): the improved pipeline

After Phase 4 changed the pipeline (summary mode with the README first, numbered `[n]` citations,
test files ranked lower), both tasks were re-run.

**Architecture summary** (the worker's prompt with README, manifest, and entry-point code), three
repos (`pallets/itsdangerous`, `pallets-eco/blinker`, DevLens):

| Model | Score /9 | Per repo (DevLens, blinker, itsdangerous) | Cost per summary | Time |
|---|---:|---|---:|---:|
| openai/gpt-4.1-mini | 9 | 3, 3, 3 | $0.00078 | 2.5 s |
| openai/gpt-4.1-nano | 7 | 2, 3, 2 | $0.00019 | 2.1 s |
| openai/gpt-4o-mini (previous default) | 6 | 2, 2, 2 | $0.00027 | 2.7 s |
| google/gemini-2.5-flash-lite | 5 | 1, 2, 2 | $0.00020 | 3.5 s |

gpt-4.1-mini was the only model to cover the DevLens pipeline, every API group, and how it runs;
flash-lite described DevLens as "the backend" only. A summary is written once per analysis, so the
price difference is irrelevant.

**Chat** (7 questions: 5 on itsdangerous including a summary and a trap, 2 on DevLens):

| Model | Score /21 | Per question | Invalid citations | Cost per answer | Time |
|---|---:|---|---:|---:|---:|
| openai/gpt-4.1-mini | 18 | 3, 3, 1, 3, 3, 3, 2 | 1 | $0.00089 | 2.3 s |
| google/gemini-2.5-flash-lite | 17 | 2, 3, 3, 2, 3, 3, 1 | 0 | $0.00023 | 2.6 s |
| openai/gpt-4o-mini | 16 | 3, 2, 2, 3, 2, 2, 2 | 0 | $0.00033 | 3.1 s |

All three handled the trap ("which database stores the tokens?": none). gpt-4.1-mini cited a
context `[6]` that did not exist on one answer; chat simply shows no source for an unknown number.

## Findings for the pipeline

- **Contexts are cut at 1,200 characters in the prompt** (`chat_synthesizer._build_prompt`), while
  chunks run to 120 lines. On "how are keyword and vector results combined?" the fusion weights sit
  at the end of the retrieved function and no model saw them. Raising the cap trades cost for
  completeness (about 2.5 times the input tokens at full chunks); worth measuring.
- Out-of-range citation markers could be dropped from the stored answer text.
