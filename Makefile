
DEPTH=.

include $(DEPTH)/config/config.mk

DIRS= \
	python_modules \
	$(NULL)

docker-%:
	$(MAKE) -C docker $*

install-dev::
	pip install -U --upgrade-strategy=eager -r tests/requirements.txt

build-release:
	cargo build --release

include $(topsrcdir)/config/rules.mk
