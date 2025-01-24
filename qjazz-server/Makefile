
DEPTH=..

include $(DEPTH)/config/config.mk

DIRS= \
	python \
	$(NULL)

build-release:
	cargo build --release --all-targets --bins

include $(topsrcdir)/config/rules.mk

