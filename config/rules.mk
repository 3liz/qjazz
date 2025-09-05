
TOPTARGET:=test

.PHONY: $(DIRS)

TOPTARGETS:=\
bin-test \
test \
lint \
lint-fix \
lint-preview \
typecheck \
clean \
configure \
build \
dist \
deliver \
install \
scan \
deadcode \
doc \
prepare_commit \
$(NULL)

$(TOPTARGETS):: $(DIRS)

$(DIRS):
	$(MAKE) -C $@ $(MAKECMDGOALS)

build::

# Add rules for python module
ifdef PYTHON_PKG
include $(topsrcdir)/config/python.mk
endif

echo-variable-%:
	@echo "$($*)"
