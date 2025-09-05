
configure::
	@echo "Configuring $$(basename $$(pwd))"
	@sed -e 's/$${PIN_VERSION}/$(VERSION)/g' pyproject.toml.in > pyproject.toml

lint::
	@$(RUFF) check --output-format=concise  $(PYTHON_PKG) $(TESTDIR) $(EXAMPLES)

lint:: typecheck

lint-preview::
	@$(RUFF) check --preview $(PYTHON_PKG) $(TESTDIR) $(EXAMPLES)

lint-fix::
	@$(RUFF) check --fix $(PYTHON_PKG) $(TESTDIR) $(EXAMPLES)

lint-fix-preview::
	@$(RUFF) check --preview --fix $(PYTHON_PKG) $(TESTDIR) $(EXAMPLES)

format-diff::
	@$(RUFF) format --diff $(PYTHON_PKG) $(TESTDIR) $(EXAMPLES)

format::
	@$(RUFF) format $(PYTHON_PKG) $(TESTDIR) $(EXAMPLES)

#install::
#	pip install -U --upgrade-strategy=eager -e .$(INSTALL_DEPENDENCIES)

typecheck:: $(PYTHON_PKG)
	$(MYPY) $(PYTHON_PKG)

scan::
	$(BANDIT) -r $(PYTHON_PKG) $(SCAN_OPTS)

# Do not use in CI tests since it choke on false positive
deadcode:: 
	vulture $(PYTHON_PKG) --min-confidence 70


ifndef TESTDIR
test::
else
test::
	cd $(TESTDIR) && $(UV_RUN) pytest -v 
endif

prepare_commit:: lint scan test
