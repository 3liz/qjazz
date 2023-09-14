
SDIST=dist

configure::
	@echo "Configuring $(PYTHON_PKG)"
	@sed -e 's/$${PIN_VERSION}/$(VERSION)/g' pyproject.toml.in > pyproject.toml

dist::
	mkdir -p $(SDIST)
	rm -rf *.egg-info
	$(PYTHON) setup.py sdist --dist-dir=$(SDIST)

clean::
	rm -rf $(SDIST) *.egg-info

deliver:
	twine upload -r storage $(SDIST)/*


lint::
	@flake8 $(PYTHON_PKG) $(TESTDIR)

autopep8:
	@autopep8 -v --in-place -r --max-line-length=120 $(PYTHON_PKG) $(TESTDIR)

ifndef TESTDIR
test::
else
test:: lint
	cd $(TESTDIR) && pytest -v $(PYTEST_ARGS)
endif
