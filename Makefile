
DEPTH=.

include $(DEPTH)/config/config.mk

DIRS= \
	qjazz-contrib \
	qjazz-server \
	qjazz-processes \
	$(NULL)

install-dev::
	pip install -U --upgrade-strategy=eager \
	  -r dev-requirements.txt \
	  -r doc/requirements.txt \
	  $(NULL)

include $(topsrcdir)/config/rules.mk
