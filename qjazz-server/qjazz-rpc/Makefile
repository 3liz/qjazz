
DEPTH=../..

include $(DEPTH)/config/config.mk

DIRS= \
	python \
	$(NULL)

#
# Wheel
#
dist::
	maturin build --release --strip --out=$(DIST)

include $(topsrcdir)/config/rules.mk
