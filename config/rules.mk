
TOPTARGET:=test

.PHONY: $(DIRS)

TOPTARGETS:=\
bin-test \
test \
lint \
lint-fix \
lint-preview \
format \
typecheck \
clean \
configure \
build \
dist \
deliver \
install \
scan \
deadcode \
check-fix \
doc \
prepare_commit \
coverage \
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
