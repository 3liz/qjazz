
DEPTH=.

include $(DEPTH)/config/config.mk

DIRS= \
	qjazz-contrib \
	qjazz-server \
	qjazz-processes \
	qjazz-metapackage \
	$(NULL)


UV_INSTALL_GROUPS=$(foreach grp,$(INSTALL_GROUPS),--group $(grp))


clean-dist: 
	rm -r $(DIST) || true

clean:: clean-dist
	rm -r ./**/.qjazz-settings || true

#
# Requirements
#

REQUIREMENT_GROUPS=\
	dev \
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

#
# Version
#
# The version is defined in the VERSION file and propagated
# to the package manifests (see scripts/version.py)
#

VERSION_SCRIPT=$(PYTHON) $(topsrcdir)/scripts/version.py

# Print the version
version:
	@$(VERSION_SCRIPT) show

# Set the version: update VERSION, manifests and lock files
set-version:
	@test -n "$(V)" || { echo "Usage: make set-version V=X.Y.Z"; exit 1; }
	@$(VERSION_SCRIPT) set $(V)

# Update manifests from the VERSION file
sync-version:
	@$(VERSION_SCRIPT) sync

# Check that manifests (and the release tag in CI) match the VERSION file
check-version:
	@$(VERSION_SCRIPT) check $(if $(CI_COMMIT_TAG),--tag $(CI_COMMIT_TAG))

lint:: check-version

.PHONY: version set-version sync-version check-version

reinstall::
	@uv sync --reinstall --all-extras $(ACTIVE_VENV) $(UV_INSTALL_GROUPS)

include $(topsrcdir)/config/rules.mk


