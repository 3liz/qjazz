
test:: ${DIRS}
	@for d in $^; do \
		$(MAKE) -C $$d test; \
	done

lint:: ${DIRS}
	@for d in $^; do \
		$(MAKE) -C $$d lint; \
	done

configure:: $(DIRS)
	@for d in $^; do \
		$(MAKE) -C $$d configure; \
	done

# Add rules for python module
ifdef PYTHON_PKG
include $(topsrcdir)/config/python.mk
endif

echo-variable-%:
	@echo "$($*)"
