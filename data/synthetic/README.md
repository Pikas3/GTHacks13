# Synthetic data notice

Everything under `data/` is **synthetic** and exists only for the Impiricus Lepius hackathon prototype.

- **HCPs** (Dr. Maya Morgan, Dr. Ethan Chen, Dr. Sofia Patel) are invented people. Any resemblance to real
  clinicians is coincidental.
- **Products** (Novara, Cardexa, Lumetrex) are **fictional**. They are not real medicines, are not based on
  real medicines, and nothing in these documents is medical guidance.
- **Clinical content** uses obvious placeholders ("Placeholder Units", "Regimen A", "Condition X",
  "Category Alpha events"). Numbers are made up to exercise retrieval and diffing, not to be realistic.
- **No patient data** of any kind is present.

Seed files live in `data/seed/`:

| File | Purpose |
| --- | --- |
| `hcps.json` | Synthetic HCP profiles, preferences and starting topic-interest scores |
| `resources/*.md` | Fictional "approved" resources (front matter + `##` sections → chunks) |
| `history.json` | Prior engagement events (e.g. Dr. Morgan viewed Novara PI v1 on 2026-06-14) |

Add resources by dropping a new Markdown file into `data/seed/resources/` with the same front-matter keys,
then re-run `make seed`. Use `supersedes: <key>` to model a new version of an existing resource.
