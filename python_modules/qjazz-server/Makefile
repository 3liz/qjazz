
DEPTH=../..

include $(DEPTH)/config/config.mk

OPTIONAL_DEPENDENCIES=minio

INSTALL_DEPENDENCIES=[minio]

PYTHON_PKG= \
	qjazz_rpc   \
	qjazz_http  \
	qjazz_admin \
	$(NULL)

TESTDIR=tests

proto:
	cd qjazz_rpc/_grpc && python -m grpc_tools.protoc -I./protos \
		--python_out=. \
		--pyi_out=. \
		--grpc_python_out=. \
		./protos/qjazz.proto
	@sed -i 's/import qjazz_pb2 as/from . import qjazz_pb2 as/' qjazz_rpc/_grpc/qjazz_pb2_grpc.py

include $(topsrcdir)/config/rules.mk

