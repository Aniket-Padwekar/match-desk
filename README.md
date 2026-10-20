# Match Desk

**Match recaps and answers where every sentence carries its receipts.**

Match Desk turns a football event log into a recap, a replay and a "chat with the match" assistant. The language model writes, but it is never trusted: a separate checker re-derives every claim from the raw events, and a sentence only reaches the reader if it passes. Each sentence shows the event numbers behind it (its *receipts*). When the data cannot answer a question, the assistant says so instead of guessing.

Live demo: https://aniket-padwekar.github.io/match-desk/

Built for the Microsoft x Premier League *Inside the Game* developer hackathon, by a single entrant.

## The problem

Recaps, match chats and AI commentary are only useful if people can trust them. A fluent sentence with one wrong number or an invented cause ("they pressed higher") is worse than no sentence. Match Desk is built around that: **write freely, publish only what can be proven.**

## What it does

| Tab | What you get |
|---|---|
| **Recap** | A short match report in three voices (fan, analyst, coach). Every sentence links to its receipts. |
| **Replay** | A second-screen timeline of the match: goals, big chances, cards, injuries, substitutions, possession spells, on a pitch. |
| **Ask the Match** | Ask in plain English ("Who made the most interceptions?", "Was anyone injured?"). Answers are computed from the event log and cited. Questions the data cannot answer (formations that were not recorded, how long a player will be out, whether the referee was right) get a clear "the match data cannot tell us this" and the reason. |
| **Trust** | A measured scorecard: how many deliberately planted errors the checker caught, and how many true sentences it wrongly blocked. |

## How it works: five agents in a loop

```
StatsAnalyst -> Storyteller -> FactChecker -> Judge -> Editor -> verified recap
```

1. **StatsAnalyst** builds a list of checkable facts straight from the event log (scores, shots, chance quality, goal roles such as "equalised", injuries, player ratings).
2. **Storyteller** (the language model) drafts sentences and must cite fact ids.
3. **FactChecker** is deterministic code. It re-computes every cited claim from the raw events and rejects wrong numbers (digits and spelled-out), names that are not in the cited facts, shortened team names, wrong possession comparisons, and jargon for fan readers.
4. **Judge** is a second model call for what rules cannot see: causes and comparisons ("because...", "more than..."). It fails closed: if the Judge cannot be reached or parsed, the sentence is blocked.
5. **Editor** rewrites a blocked sentence and sends it back through the checks, or drops it. Nothing unverified is shown.

**Ask the Match** follows the same idea: a planner chooses from a small set of deterministic lookups (score timeline, team stats, top players, ratings, injuries, substitutions, "why did the result happen"); a writer phrases the result; the same checker and Judge verify it; otherwise the answer is a code-written "cannot tell".

## Microsoft technology used

| Technology | Where |
|---|---|
| **Microsoft Foundry** (Azure AI Foundry) | Hosts the `gpt-5-mini` model deployment that the Storyteller, Judge, Editor and Ask planner/writer call. |
| **Microsoft Agent Framework** (Python) | `maf_workflow.py` runs the five agents as a workflow graph (executors connected by edges). It calls the same stage functions as the plain pipeline, so both give identical results. |
| **Azure OpenAI in Foundry** (`openai` SDK, `AzureOpenAI` client) | The model calls, with `reasoning_effort="low"` to keep cost down. |
| **GitHub Actions** | `.github/workflows/scorecard.yml` re-runs the verifier checks on every push so the checker cannot quietly get worse. |
| **GitHub Pages** | Hosts the demo site from `/docs` at no cost. |

Not used, and not claimed: Fabric, AKS, Container Apps, Logic Apps, Azure MCP, GitHub Copilot agent mode.

## Data: fully synthetic

No real match data, clubs or players are used. `simulate.py` generates football-realistic matches (positions, passes, shots with chance quality, fouls, cards, injuries and substitutions, possession spells) for **fictional clubs and invented players**; any resemblance to real ones is coincidental. A match is a list of numbered events, which is what makes "receipts" possible.

## The measured trust result

`real_scorecard` takes true sentences and plants known errors in them (wrong number, swapped team, invented cause, wrong citation, flipped comparison), then counts what the checker catches. Last run, with the real `gpt-5-mini` Judge on 6 synthetic matches:

- **399 of 400** planted errors caught
- **0 of 124** true sentences wrongly blocked
- The one miss: a wrong-citation case ("Redbridge Town scored 0.") that was true on its face
- In the recap run, **16 of 160** first drafts were blocked and then rewritten or dropped; none shown unverified

Honest limits:
- The errors are planted by the author, in the kinds the checker was designed for. It is evidence that the checker works, not proof that no error can ever slip through.
- The Judge and the writer use the same model family, so they can share blind spots.
- Ask the Match checks answers against the lookup's own text. If a lookup is too broad (for example omits a time window), the checker cannot see that. This is a known gap, and the lookups state their windows in their text.
- Everything is measured on synthetic matches.

## Run it yourself

The recap/answer generation needs a Foundry model deployment; the checker, simulator and tests do not.

Offline checks (no keys, no cost):
```bash
python tests/check.py
```

Generate recaps and answers with your own Azure model (Google Colab, free):
1. Create a Foundry project and deploy `gpt-5-mini` (the Azure free account is enough).
2. Open a new Colab notebook and paste `colab_build_site.py` into one cell.
3. Enter your endpoint and deployment name; type the key into the hidden prompt. The key is never stored in this repo.
4. Download the zip and copy `recaps.json`, `ask.json`, `scorecard.json` into `docs/data/`.

Quick check that the Agent Framework workflow runs: `colab_maf_check.py`.

## Repo layout

```
simulate.py        synthetic match generator (fictional clubs)
engine.py          stats, key moments, claims, independent verifier
insight.py         player ratings and "why did the result happen"
agents.py          the five stages, checker, model backends, scorecard
maf_workflow.py    the same five agents as a Microsoft Agent Framework workflow
ask.py             Ask the Match: lookups, planner, checked answers
build_site.py      builds docs/data from the simulator
docs/              the static demo site (GitHub Pages)
tests/check.py     offline regression check run by GitHub Actions
colab_*.py         one-cell Colab scripts
```

## How this was built

Match Desk was designed and directed by one person with no prior coding background, and **written with AI assistance (Anthropic's Claude)**: the code, the site and this README were produced in conversation with the AI, with the entrant choosing the idea, the product decisions and what to test, running every Azure step, and reviewing results. This is disclosed openly in line with the hackathon rules.

## Licence

Code released for the hackathon; licence to be confirmed by the author.
