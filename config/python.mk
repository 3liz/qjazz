
SDIST=dist

configure::
	@echo "Configuring $$(basename $$(pwd))"
	@sed -e 's/$${PIN_VERSION}/$(VERSION)/g' pyproject.toml.in > pyproject.toml

dist::
	mkdir -p $(SDIST)
	rm -rf *.egg-info
	$(PYTHON) -m build --no-isolation --sdist --outdir=$(SDIST)


clean::
	rm -rf $(SDIST) *.egg-info

deliver::
	twine upload -r storage $(SDIST)/*

lint::
	@ruff check  --output-format=concise  $(PYTHON_PKG) $(TESTDIR) $(EXAMPLES)

lint:: typecheck

lint-preview::
	@ruff check --preview $(PYTHON_PKG) $(TESTDIR) $(EXAMPLES)

lint-fix::
	@ruff check --fix $(PYTHON_PKG) $(TESTDIR) $(EXAMPLES)

lint-fix-preview::
	@ruff check --preview --fix $(PYTHON_PKG) $(TESTDIR) $(EXAMPLES)

format-diff::
	@ruff format --diff $(PYTHON_PKG) $(TESTDIR) $(EXAMPLES)

format::
	@ruff format $(PYTHON_PKG) $(TESTDIR) $(EXAMPLES)

#install::
#	pip install -U --upgrade-strategy=eager -e .$(INSTALL_DEPENDENCIES)

typecheck:: $(PYTHON_PKG)
	$(MYPY) $(foreach pkg,$^,-p $(pkg))

scan::
	bandit -r $(PYTHON_PKG) $(SCAN_OPTS)

# Do not use in CI tests since it choke on false positive
deadcode:: 
	vulture $(PYTHON_PKG) --min-confidence 70


ifndef TESTDIR
test::
else
test:: lint typing scan
	cd $(TESTDIR) && pytest -v 
endif
