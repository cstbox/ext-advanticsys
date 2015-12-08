# CSTBox framework
#
# Makefile for building the Debian distribution package containing the
# AdvanticSys Modbus products support.
#
# author = Eric PASCUAL - CSTB (eric.pascual@cstb.fr)

# name of the CSTBox module
MODULE_NAME=ext-advanticsys

include $(CSTBOX_DEVEL_HOME)/lib/makefile-dist.mk

copy_files: \
	check_metadata_files \
	copy_devices_metadata_files \
	copy_python_files 

