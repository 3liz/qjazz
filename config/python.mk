
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

deliver::
	twine upload -r storage $(SDIST)/*

lint::
	@ruff check --preview $(PYTHON_PKG) $(TESTDIR)

install::
	pip install -e .

autopep8:
	@ruff check --preview --fix $(PYTHON_PKG) $(TESTDIR)
	# Only fix E303 E302 error
	# since ruff does no implement this yet
	@autopep8 --in-place -r --select E303,E302 $(PYTHON_PKG) $(TESTDIR)

mypy:
	@mypy --config-file=$(topsrcdir)/config/mypy.ini -p $(PYTHON_PKG)


ifndef TESTDIR
test::
else
test:: lint mypy
	cd $(TESTDIR) && pytest -v $(PYTEST_ARGS)
endif
