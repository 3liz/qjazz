
test:: ${DIRS}
	@for d in $^; do \
		$(MAKE) -C $$d test || exit 1; \
	done

lint:: ${DIRS}
	@for d in $^; do \
		$(MAKE) -C $$d lint; \
	done

configure:: ${DIRS}
	@for d in $^; do \
		$(MAKE) -C $$d configure; \
	done

dist:: ${DIRS}
	for d in $^; do  \
		$(MAKE) -C $$d dist || exit 1; \
	done

deliver:: ${DIRS}
	for d in $^; do  \
		$(MAKE) -C $$d deliver || exit 1; \
	done


# Add rules for python module
ifdef PYTHON_PKG
include $(topsrcdir)/config/python.mk
endif

echo-variable-%:
	@echo "$($*)"
