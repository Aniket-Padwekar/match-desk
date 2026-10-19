# Match Desk

Verified match intelligence for the Microsoft x Premier League *Inside the Game* hackathon.
Every sentence a recap shows is checked against the raw event log, and carries its receipts (the event numbers behind it).

Status: work in progress.
- `simulate.py` synthetic match generator (no real data)
- `engine.py` stats, key moments, claims, independent verifier, planted-error scorecard
- `insight.py` ratings explainer and "why the result defied the chances"
- `agents.py` Storyteller, FactChecker and Editor loop (stand-in model or Azure)
