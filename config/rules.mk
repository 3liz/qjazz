
TOPTARGET:=test

.PHONY: $(DIRS)

TOPTARGETS:=\
test \
lint \
lint-preview \
typing \
clean \
configure \
build \
dist \
deliver \
install \
install-dev \
scan \
deadcode \
$(NULL)

$(TOPTARGETS):: $(DIRS)

requirements: $(DIRS)

$(DIRS):
	$(MAKE) -C $@ $(MAKECMDGOALS)

build::

# Add rules for python module
ifdef PYTHON_PKG
include $(topsrcdir)/config/python.mk
endif

echo-variable-%:
	@echo "$($*)"
