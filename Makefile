
DEPTH=.

include $(DEPTH)/config/config.mk

DIRS= \
	qjazz-contrib \
	qjazz-server \
	qjazz-processes \
	$(NULL)


install::
	@uv sync --all-extras --frozen --active

# Upgrade all packages dependencies - will update uv.lock
upgrade::
	@uv sync --all-extras --active

upgrade:: requirements.txt

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


include $(topsrcdir)/config/rules.mk
