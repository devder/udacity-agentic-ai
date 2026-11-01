PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
SWAP := scripts/openai_to_claude.py

.PHONY: help claude claude-preview require-nb

help: ## List available targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

claude: require-nb ## Swap OpenAI -> Claude in place: make claude NB="path/a.ipynb path/b.ipynb"
	$(PYTHON) $(SWAP) $(NB)

claude-preview: require-nb ## Show the per-cell diff without writing: make claude-preview NB=path/a.ipynb
	$(PYTHON) $(SWAP) --dry-run $(NB)

require-nb:
	@test -n "$(NB)" || { echo 'usage: make <target> NB="path/to/notebook.ipynb"'; exit 2; }
