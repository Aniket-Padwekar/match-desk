# Match Desk

**Match recaps and answers where every sentence carries its receipts.**

Match Desk turns a football event log into a recap, a pitch replay, a "chat with the match" assistant and a player table. A language model writes the recap, but it is never trusted: separate code re-derives every claim from the raw events, and a second model call checks causes and comparisons. Anything that fails is rewritten or dropped, so nothing unchecked is shown.

Live demo: https://aniket-padwekar.github.io/match-desk/

Built for the Microsoft x Premier League *Inside the Game* developer hackathon, by a single entrant.

## The problem

Recaps, match chats and AI commentary are only useful if people can trust them. A fluent sentence with one wrong number or an invented cause ("they pressed higher") is worse than no sentence. Match Desk is built around that: every sentence links to the events that prove it, and the checker's accuracy is measured and shown.

## What you can do on the site

| Tab | What you get |
|---|---|
| **Recap** | A short match report. Every sentence is checked against the event log and links to its receipts; select a sentence to see the players and passes behind it on the pitch. Below it, a **Player data** table counted by code from the event log. |
| **Replay** | Scrub or play the match. The pitch shows the one event the caption describes (who, where, and the pass or goal direction), next to a chance-quality line and a minute-by-minute feed. |
| **Ask** | Eleven prepared questions that went through the full pipeline (planner, lookups, writer, checker, judge). You can also type your own question: it is matched by rules to a lookup over the event log, answered with receipts, or answered "cannot tell". No model is called for typed questions. |
| **League table** | The table after matchweek 1. |
| **How it's checked** | A measured scorecard (deliberately planted errors vs. what the checker caught), the five agents, and a box where you can edit a sentence and run the rule layer in your browser. |

The site is in English, German, Spanish, French, Italian, Portuguese and Arabic (right-to-left). Prepared answers and recaps are translated by the model with number and name checks. Typed questions are understood in English.

## How it works: five agents in a loop

```
StatsAnalyst -> Storyteller -> FactChecker -> Judge -> Editor -> verified recap
```

1. **StatsAnalyst** builds a list of checkable facts straight from the event log. Plain code, no model.
2. **Storyteller** (the language model) drafts sentences and must cite fact numbers.
3. **FactChecker** is deterministic code. It re-computes every cited claim from the raw events and rejects wrong numbers, names that are not in the cited facts, shortened team names and wrong citations.
4. **Judge** is a second model call for what rules cannot see: causes and comparisons ("because...", "more than..."). It fails closed: if it cannot be reached or parsed, the sentence is blocked.
5. **Editor** rewrites a blocked sentence from its own facts and re-checks it, or drops it.

**Ask** uses a small set of deterministic lookups (score timeline, team stats, top players, player stats, ratings, injuries, substitutions, "why did the result happen"). If no lookup can answer, the answer is a plain "the match data cannot tell us this", written by code.

## Microsoft technology used

| Technology | Where |
|---|---|
| **Microsoft Foundry** | Hosts the `gpt-5-mini` deployment used by the Storyteller, Judge, Editor, translator and the prepared Ask answers. |
| **Microsoft Agent Framework** (Python) | `maf_workflow.py` runs the five agents as a workflow graph (executors connected by edges). It calls the same stage functions as the plain pipeline. |
| **Azure OpenAI in Foundry** (`openai` SDK, `AzureOpenAI`) | The model calls, with low reasoning effort to keep cost down. |
| **GitHub Actions** | `.github/workflows/scorecard.yml` re-runs the offline checker tests on every push. |
| **GitHub Pages** | Hosts the static demo site from `/docs`, free for judges. |

Written but **not deployed**: `function_app.py` and `live_ask.py` (an Azure Function that would answer typed questions with the model, with a per-visitor limit and a hard total cap). It is switched off on purpose so judges can use the demo for free and nobody can run up a bill. `tracing.py` can send the workflow's traces to Azure Monitor / Foundry Tracing; it is off by default and has not been run against a live Azure resource.

Not used, and not claimed: Fabric, AKS, Container Apps, Logic Apps, Azure MCP, GitHub Copilot agent mode.

## Data: fully synthetic

No real match data, clubs or players are used. `simulate.py` generates football-realistic matches (positions, passes, shots with chance quality, fouls, cards, injuries, substitutions) for fictional clubs. The demo has one matchweek of 8 matches.

## The measured trust result

`real_scorecard` takes true sentences, plants known errors in them (wrong number, swapped team, invented cause, wrong citation, flipped comparison) and counts what the checker catches. Last run with the real `gpt-5-mini` deployment, on 6 simulated matches:

- **399 of 400** planted errors caught
- **0 of 124** true sentences wrongly blocked
- The one miss: a wrong-citation case ("Redbridge Town scored 0.") that was true on its face

Honest limits:
- The errors are planted by the author, in the kinds the checker was designed for. This shows the checker works on those; it is not proof that no error can slip through. A repeat of the same test is not independent evidence.
- The Judge and the writer use the same model family, so they can share blind spots.
- Prepared Ask answers are checked against the lookup's own text. If a lookup were too broad (say, it left out a time window), the checker could not see that.
- Everything is measured on synthetic matches.
- Typed questions only cover what the rules recognise (stats, teams, halves, minute ranges, player names). Anything else gets "cannot tell". That is intended, but it is narrower than a model-based Ask.

## What was tested

- `python tests/check.py`: offline tests of the simulator, engine, checker and Ask lookups (no keys, no cost).
- The recaps, prepared answers, translations and scorecard were generated on the real Azure `gpt-5-mini` deployment in Google Colab.
- The website was checked in a browser with a scripted test (every minute of the replay shows at most one dot, one arrow and one name; typed questions return the expected answers). Not tested: a full accessibility audit, and phone layouts beyond a quick look.

## Run it yourself

Offline checks (no keys, no cost): `python tests/check.py`

Generate a matchweek with your own Azure model (Google Colab): paste `colab_season.py` into one cell, enter your endpoint and deployment name, and type the key into the hidden prompt. The key is never stored in this repo. Estimate cost before you run: one matchweek in 6 languages was a few euros on `gpt-5-mini`.

## Repo layout

```
simulate.py        synthetic match generator (fictional clubs)
engine.py          stats, key moments, claims, independent verifier
insight.py         player ratings and "why did the result happen"
agents.py          the five stages, checker, model backends, scorecard
maf_workflow.py    the same five agents as a Microsoft Agent Framework workflow
tracing.py         optional tracing to Azure Monitor (off by default, untested live)
ask.py             prepared Ask answers: lookups, planner, checked answers
season.py          fictional league and fixtures
build_season.py    builds the season and matchweek files from the simulator
season_run.py      model-written recaps, answers and translations for one matchweek
translate.py       translation with number and name checks
ui_en.py           interface labels (English source)
live_ask.py        live Ask logic, caps and limits (offline testable, not deployed)
function_app.py    Azure Function wrapper for live Ask (not deployed)
docs/              the static demo site (GitHub Pages); site code is docs/index.html
tests/check.py     offline regression check run by GitHub Actions
colab_*.py         one-cell Colab scripts
```

## How this was built

Match Desk was designed and directed by one person with no prior coding background, and **written with AI assistance (Anthropic's Claude)**: the code, the site, the interface translations of newer labels and this README were produced in conversation with the AI. The entrant chose the idea and the product decisions, set the cost limits, ran every Azure step, and reviewed the results. This is disclosed in line with the hackathon rules.

## Licence

MIT, see `LICENSE`.
