.PHONY: test validate load test-routing test-routing-live test-behavior catalog install

# Free, fast checks (no model calls).
test: validate load

validate:
	python3 scripts/validate_agents.py --strict

load:
	bash scripts/test_loading.sh

# These spend API credits.
test-routing:
	python3 scripts/test_routing.py --mode select

test-routing-live:
	python3 scripts/test_routing.py --mode live

test-behavior:
	python3 scripts/test_behavior.py

# Regenerate the catalog table in README.md from agent frontmatter.
catalog:
	python3 scripts/gen_catalog.py

# Copy agents into ~/.claude/agents (use ARGS="--link" to symlink, ARGS="--help" for options).
install:
	bash install.sh $(ARGS)
