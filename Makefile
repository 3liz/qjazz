
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

install::
	@uv sync --all-extras --frozen $(ACTIVE_VENV) $(UV_INSTALL_GROUPS)

# Upgrade all packages dependencies - will update uv.lock
upgrade::
	@uv sync -U --all-extras $(ACTIVE_VENV) $(UV_INSTALL_GROUPS)

upgrade:: requirements.txt

reinstall::
	@uv sync --reinstall --all-extras $(ACTIVE_VENV) $(UV_INSTALL_GROUPS)


include $(topsrcdir)/config/rules.mk


