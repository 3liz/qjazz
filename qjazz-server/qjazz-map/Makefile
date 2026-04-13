
DEPTH=../..

include $(DEPTH)/config/config.mk

#
# Wheel
#
dist::
	maturin build --release --strip --features=monitor --out=$(DIST)

include $(topsrcdir)/config/rules.mk
