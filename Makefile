
DEPTH=.

include $(DEPTH)/config/config.mk

DIRS= \
	python_modules \
	$(NULL)

docker-%:
	$(MAKE) -C docker $*

include $(topsrcdir)/config/rules.mk
