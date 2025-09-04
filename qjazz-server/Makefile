
DEPTH=..

include $(DEPTH)/config/config.mk

DIRS= \
	python \
	$(NULL)

#
# Rust
#

include $(topsrcdir)/config/rules.mk

build::
	cargo build --release --bins --features monitor

BINS=\
	qjazz-map-bin \
	qjazz-rpc-bin \
	$(NULL)

dist:: build
	@for f in $(BINS); do \
		cp -v target/release/$$f $(DIST)/; \
	done

bin-test::
	cargo test

install::
	cd tests && ln -s $$(which qgis-plugin-manager) || true

doc::
	make -C $(topsrcdir)/doc

