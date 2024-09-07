
DEPTH=../..

include $(DEPTH)/config/config.mk

PYTHON_PKG= \
	py_qgis_rpc   \
	py_qgis_http  \
	py_qgis_admin \
	$(NULL)

TESTDIR=tests

proto:
	cd py_qgis_rpc/_grpc && python -m grpc_tools.protoc -I./protos \
		--python_out=. \
		--pyi_out=. \
		--grpc_python_out=. \
		./protos/api.proto
	@sed -i 's/import api_pb2 as/from . import api_pb2 as/' py_qgis_rpc/_grpc/api_pb2_grpc.py

include $(topsrcdir)/config/rules.mk

