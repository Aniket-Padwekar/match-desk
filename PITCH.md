# Match Desk: pitch text

## One line
Match recaps and answers where every sentence shows its receipts.

## The problem
AI match reports read well and are sometimes wrong: a changed number, a swapped team, an invented reason. For fans, clubs and media, one wrong sentence costs more trust than a hundred right ones.

## What we built
Match Desk takes a football event log and produces a recap, a pitch replay, a question box and a player table. The model writes. It is never trusted. Separate code re-derives every claim from the raw events, a second model call checks causes and comparisons, and anything that fails is rewritten or dropped. Click any sentence and the proof shows on the pitch. The interface works in seven languages, including Arabic right-to-left.

## How we measured it
We plant errors on purpose (wrong number, swapped team, invented cause, wrong citation, flipped comparison) and count what gets caught: 399 of 400, with 0 of 124 true sentences wrongly blocked. The test is on simulated matches and the errors are ours, so we say plainly what it does and does not prove. It is on the "How it's checked" tab.

## Microsoft technology
- **Microsoft Foundry**: hosts the gpt-5-mini deployment behind the writer, judge, editor and translator.
- **Microsoft Agent Framework (Python)**: the five agents (Stats analyst, Storyteller, Fact checker, Judge, Editor) run as a workflow graph in `maf_workflow.py`.
- **Azure OpenAI in Foundry**: the model calls.
- **GitHub Actions and GitHub Pages**: tests on every push; the demo is hosted free for judges.

## Current limits, said plainly
- Synthetic data only: fictional clubs and players, one matchweek of 8 matches.
- Typed questions are answered by rules over the same checked lookups, in English, with no model call. Questions the data cannot settle get "cannot tell".
- A live, model-based Ask is written (Azure Function with per-visitor and total caps) but not deployed, so the demo stays free and safe for judges.
- Tracing to Foundry is written but not yet run on a live resource.

## What full deployment looks like
Live Ask through the Azure Function with spending caps; Foundry tracing on every agent step; real event feeds in place of the simulator; more matchweeks and languages generated on a schedule; the same receipts-and-checks layer behind a club or broadcaster app.

## Built with AI assistance
Designed and directed by one person with no coding background, and written with AI assistance (Anthropic's Claude). Disclosed in the README.
