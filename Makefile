
DEPTH=.

include $(DEPTH)/config/config.mk

DIRS= \
	python_modules \
	qjazz-server \
	qjazz-processes \
	$(NULL)

docker-%:
	$(MAKE) -C docker $*

install-dev::
	pip install -U --upgrade-strategy=eager -r tests/requirements.txt

include $(topsrcdir)/config/rules.mk
