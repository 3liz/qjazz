
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

dist-clean:
	rm -rf $(DIST)/*

clean:: dist-clean

build::

# Add rules for python module
ifdef PYTHON_PKG
include $(topsrcdir)/config/python.mk
endif

echo-variable-%:
	@echo "$($*)"
