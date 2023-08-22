DIST:=dist

PYTHON=python3

PACKAGE=py_qgis_contrib

dist:
	mkdir -p $(DIST)
	rm -rf *.egg-info
	$(PYTHON) setup.py sdist --dist-dir=$(DIST)

clean:
	rm -rf $(DIST) *.egg-info

deliver:
	twine upload -r storage $(DIST)/*

lint:
	@flake8 $(PACKAGE) tests

autopep8:
	@autopep8 -v --in-place -r --max-line-length=120 $(PACKAGE) tests

test: lint
	cd tests && pytest -v $(PYTEST_ARGS) 
