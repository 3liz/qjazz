
DEPTH=.

include $(DEPTH)/config/config.mk

DIRS= \
	python_modules \
	$(NULL)

docker-%:
	$(MAKE) -C docker $*

install-tests::
	pip install -U --upgrade-strategy=eager -r tests/requirements.txt

include $(topsrcdir)/config/rules.mk
