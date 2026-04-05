.PHONY: dev test lint format typecheck clean build release bench

dev:
	pip install -e ".[dev]"

test:
	pytest -v

lint:
	ruff check src tests

format:
	ruff format src tests

typecheck:
	mypy src

bench:
	python benchmarks/bench.py

bench-json:
	python benchmarks/bench.py --json --output benchmarks/results.json

build:
	pip install build
	python -m build

# Usage: make release VERSION=0.2.0
release:
	@if [ -z "$(VERSION)" ]; then echo "Usage: make release VERSION=x.y.z"; exit 1; fi
	@echo "Bumping version to $(VERSION) ..."
	sed -i.bak 's/^version = .*/version = "$(VERSION)"/' pyproject.toml && rm -f pyproject.toml.bak
	sed -i.bak 's/^__version__ = .*/__version__ = "$(VERSION)"/' src/codeatlas/__init__.py && rm -f src/codeatlas/__init__.py.bak
	git add pyproject.toml src/codeatlas/__init__.py
	git commit -m "release v$(VERSION)"
	git tag "v$(VERSION)"
	git push origin main "v$(VERSION)"
	@echo "Tag v$(VERSION) pushed — GitHub Actions will build and publish to PyPI."

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -name "*.pyc" -delete
	rm -rf dist/ build/ coverage.xml .coverage
