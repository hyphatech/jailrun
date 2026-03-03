PROJECT_NAME := jrun

BOLD := $(shell tput bold 2>/dev/null)
RESET := $(shell tput sgr0 2>/dev/null)

.DEFAULT: help
.PHONY: help test lint

help: ## show this help
	@echo ""
	@echo "$(BOLD)$(PROJECT_NAME)$(RESET)"
	@echo "===="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-12s\033[0m %s\n", $$1, $$2}'
	@echo ""

target ?= tests
test: ## run all tests
	uv run pytest -x -s -v $(target) --color=yes --code-highlight=yes --ff

lint: ## run ruff and mypy
	uv run ruff format
	uv run ruff check --fix
	uv run mypy
