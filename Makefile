
DEPTH=.

include $(DEPTH)/config/config.mk

PYTHON_MODULES= \
	python_modules/py-qgis-contrib \
	python_modules/py-qgis-project-cache \
	python_modules/py-qgis-worker \
	python_modules/py-qgis-scripts \
	python_modules/py-qgis-admin \
	$(NULL)

test: ${PYTHON_MODULES}
	@for d in $^; do \
		$(MAKE) -C $$d test; \
	done

lint: ${PYTHON_MODULES}
	@for d in $^; do \
		$(MAKE) -C $$d lint; \
	done

configure: $(PYTHON_MODULES)
	@for d in $^; do \
		$(MAKE) -C $$d configure; \
	done


docker-%:
	$(MAKE) -C docker $*

include $(topsrcdir)/config/rules.mk
