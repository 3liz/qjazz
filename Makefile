
DEPTH=.

include $(DEPTH)/config/config.mk

DIRS= \
	qjazz-contrib \
	qjazz-server \
	qjazz-processes \
	$(NULL)


UV_INSTALL_GROUPS=$(foreach grp,$(INSTALL_GROUPS),--group $(grp))


clean-dist: 
	rm -r $(DIST)

clean:: clean-dist

#
# Requirements
#

REQUIREMENT_GROUPS=\
	tests \
	lint \
	doc \
	$(NULL)

# Rebuild requirements only if uv.lock change
requirements.txt: uv.lock

# Export requirements for all projects
# in the workspace
requirements.txt:
	@echo "Updating requirements.txt"
	@uv export --all-extras --no-dev --format requirements.txt \
		--no-emit-workspace \
		--no-annotate \
		--no-editable \
		--no-hashes -q -o requirements.txt

update-requirements: requirements.txt $(patsubst %, update-requirements-%, $(REQUIREMENT_GROUPS))

# Update requirements groups

# Test requirements require project's dependencies
update-requirements-tests:
	@echo "Updating requirements for 'tests'"; \
	uv export --all-extras --no-dev --group tests --format requirements.txt \
		--no-annotate \
		--no-editable \
		--no-hashes \
		-q -o requirements/tests.txt;

update-requirements-%:
	@echo "Updating requirements for '$*'"; \
	uv export --format requirements.txt \
		--no-annotate \
		--no-editable \
		--no-hashes \
		--only-group $*\
		-q -o requirements/$*.txt;

# Install all dev requirementa using frozen packagess 
install::
	@uv sync --all-extras --frozen $(ACTIVE_VENV) $(UV_INSTALL_GROUPS)

# Upgrade all packages dependencies - will update uv.lock
upgrade::
	@uv sync -U --all-extras $(ACTIVE_VENV) $(UV_INSTALL_GROUPS)

upgrade:: update-requirements

reinstall::
	@uv sync --reinstall --all-extras $(ACTIVE_VENV) $(UV_INSTALL_GROUPS)


include $(topsrcdir)/config/rules.mk


