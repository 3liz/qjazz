
TOPTARGET:=test

.PHONY: $(DIRS)

TOPTARGETS:=test lint lint-preview typing configure dist deliver install install-tests security

$(TOPTARGETS):: $(DIRS)

requirements: $(DIRS)

$(DIRS):
	$(MAKE) -C $@ $(MAKECMDGOALS)

# Add rules for python module
ifdef PYTHON_PKG
include $(topsrcdir)/config/python.mk
endif

echo-variable-%:
	@echo "$($*)"
