
DEPTH=..

include $(DEPTH)/config/config.mk

DIRS= \
	qjazz-rpc \
	qjazz-map \
	$(NULL)

#
# Rust
#

include $(topsrcdir)/config/rules.mk

bin-test::
	cargo test

install::
	cd tests && ln -s $$(which qgis-plugin-manager) || true

doc::
	make -C $(topsrcdir)/doc

