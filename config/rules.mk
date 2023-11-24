
TOPTARGET:=test

.PHONY: $(DIRS)

TOPTARGETS:=test lint configure dist deliver install

$(TOPTARGETS):: $(DIRS)

$(DIRS):
	$(MAKE) -C $@ $(MAKECMDGOALS)

# Add rules for python module
ifdef PYTHON_PKG
include $(topsrcdir)/config/python.mk
endif

echo-variable-%:
	@echo "$($*)"
