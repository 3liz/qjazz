
DEPTH=.

include $(DEPTH)/config/config.mk

DIRS= \
	python_modules \
	$(NULL)

docker-%:
	$(MAKE) -C docker $*

install-tests::
	pip install -r tests/requirements.txt

include $(topsrcdir)/config/rules.mk
