.PHONY: stubs stubs-check test

# Regenerate `pm.d.ts` and `pm.pyi` from `src/services/scripting/pm_api_schema.py`.
stubs:
	PYTHONPATH=src .venv/bin/python -m services.lsp.stubs_generator

# CI guard: regenerate and fail if committed stubs are stale.
stubs-check: stubs
	git diff --exit-code data/lsp/stubs/

test:
	.venv/bin/python -m pytest
