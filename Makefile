.PHONY: install-dev
install-dev:
	python -m pip install --upgrade --editable .[dev,test]
	pre-commit install

.PHONY: upgrade-dev
upgrade-dev:
	python -m pip install --upgrade pip-tools
	pip-compile --resolver=backtracking requirements/requirements.in
	pip-compile --resolver=backtracking requirements/requirements-dev.in
	pip-compile --resolver=backtracking requirements/requirements-test.in

.PHONY: coverage
coverage:
	coverage run -m pytest tests/
	coverage report -m

.PHONY: docker-test
docker-test:
	docker build -t pydocker-test .
	docker run -it --rm pydocker-test

.PHONY: build-dist
build-dist:
	python -m pip install --upgrade build
	python -m build

.PHONY: clean
clean:
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '__pycache__' -exec rm -rf {} +
	find . -name '.mypy_cache' -exec rm -rf {} +
	rm -rf .nox
	rm -f coverage.xml
	rm -f coverage.json
	rm -rf htmlcov
	rm -rf .coverage
	rm -rf .coverage.*
	find . -name '.pytest_cache' -exec rm -rf {} +
	rm -rf dist
	rm -rf build
