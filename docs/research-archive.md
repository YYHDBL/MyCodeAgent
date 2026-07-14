# Research archive

The removed Agent Teams research runtime is preserved only in Git history. Its
exact pre-removal commit is `f497b172c9bce8279d9a26eb69273e25db7392cf`.

Inspect it with `git show f497b172c9bce8279d9a26eb69273e25db7392cf:experimental/teams/manager.py`.
It is not a supported product surface.

The removed self-modifying Skills research system remains recoverable from
Git commit `7c391feed9eb6da9c57f0e6308dd792514e14322`
(`docs: polish readme and add skill evolution lifecycle reports`). That commit
contains its implementation, tests, and design documents as they existed at
the final research revision. Inspect it without restoring it to the stable
product with:

```bash
git show 7c391feed9eb6da9c57f0e6308dd792514e14322 -- extensions/skill_evolution docs/skill_evolution docs/SKILL_EVOLUTION_DESIGN.md tests/extensions/test_skill_evolution.py
```
