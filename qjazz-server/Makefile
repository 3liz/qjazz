
DEPTH=..

include $(DEPTH)/config/config.mk

DIRS= \
	python \
	$(NULL)

build-release:
	cargo build --release  --bins

build-release-monitor:
	cargo build --release  --bins --features monitor

include $(topsrcdir)/config/rules.mk

bin-test::
	cargo test

install-dev::
	cd tests && ln -s $$(which qgis-plugin-manager) || true


