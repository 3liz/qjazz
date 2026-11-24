
export QGIS_SERVER_LIZMAP_REVEAL_SETTINGS=true

run-map:
	cargo run --bin qjazz-map-bin serve -C ./config-map.toml

run-map-single-backend:
	cargo run --bin qjazz-map-bin serve -C ./config-map-single.toml


run-rpc:
	cargo run --bin qjazz-rpc-bin serve -C ./config-rpc.toml

run-rpc-monitor:
	cargo run --features=monitor --bin qjazz-rpc-bin serve -C ./config-rpc.toml

# Run client tests against servers started
# with 'run-rpc' and 'run-map'
CLIENT_TESTS_HOST ?= localhost:4000

client-tests:
	cd clienttests && pytest -v --host $(CLIENT_TESTS_HOST) $(TEST_OPTS)
