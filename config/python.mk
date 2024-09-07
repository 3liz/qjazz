
SDIST=dist

configure::
	@echo "Configuring $$(basename $$(pwd))"
	@sed -e 's/$${PIN_VERSION}/$(VERSION)/g' pyproject.toml.in > pyproject.toml

dist::
	mkdir -p $(SDIST)
	rm -rf *.egg-info
	$(PYTHON) setup.py sdist --dist-dir=$(SDIST)

clean::
	rm -rf $(SDIST) *.egg-info

deliver::
	twine upload -r storage $(SDIST)/*

lint::
	@ruff check  --output-format=concise  $(PYTHON_PKG) $(TESTDIR)

lint-preview::
	@ruff check --preview $(PYTHON_PKG) $(TESTDIR)

lint-fix::
	@ruff check --preview --fix $(PYTHON_PKG) $(TESTDIR)

install::
	pip install -U --upgrade-strategy=eager -e .

typing:: $(PYTHON_PKG)
	$(MYPY) $(foreach pkg,$^,-p $(pkg))

scan::
	bandit -r $(PYTHON_PKG)


.PHONY: $(REQUIREMENTS)

# Output frozen requirements
requirements: $(REQUIREMENTS)
	@echo "Optional dependencies: $(OPTIONAL_DEPENDENCIES)"
	@pipdeptree -p "$$($(DEPTH)/requirements $(OPTIONAL_DEPENDENCIES))" -f \
		| sed "s/^[ \t]*//" | sed "/^\-e .*/d" \
		| sort | uniq > $<
	@echo "Requirements written in $<"


ifndef TESTDIR
test::
else
test:: lint typing scan
	cd $(TESTDIR) && pytest -v 
endif
