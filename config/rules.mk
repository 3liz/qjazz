
# Add rule for python module
ifdef PYTHON_PKG
include $(topsrcdir)/config/python.mk
endif


echo-variable-%:
	@echo "$($*)"
