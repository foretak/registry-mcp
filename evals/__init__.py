"""Makes `evals` a regular (not namespace) package.

Needed only so `mypy .`'s directory walk and `tests/test_evals_baseline.py`'s
`import evals.run` agree on one qualified module name for `evals/run.py`
("evals.run" both ways) — without this file, mypy resolves the same file to
two different module names ("run" via the walk, "evals.run" via the import)
and refuses to check it ("Source file found twice under different module
names"). Carries no behaviour: `evals/run.py` is still run directly as a
script (`python evals/run.py ...`), never imported as `evals.run` outside
of tests.
"""
