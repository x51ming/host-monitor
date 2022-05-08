.PHONY: install clean all dev static

all: hmonitor hm_pb2.py hm_pb2_grpc.py static

dev: hm_pb2.py hm_pb2_grpc.py hm.pb.go go.mod

hmonitor: main.go hm.pb.go go.mod
	go mod tidy ; go build -o hmonitor

hm.pb.go:
	protoc --go_out=plugins=grpc:. --go_opt=paths=source_relative hm.proto ;\
    sed -i 's/package __/package main/' hm.pb.go

go.mod: main.go
	go mod tidy

hm_pb2.py hm_pb2_grpc.py: hm.proto
	python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. hm.proto

clean:
	rm hmonitor hm.pb.go hm_pb2.py hm_pb2_grpc.py go.sum
	rm -rf static

install: all
	mkdir -pv ../bin
	cp -uvr templates/ ../bin/
	cp -uvr static/ ../bin/
	cp -uv hmonitor ../bin/
	cp -uv main.py hm_pb2.py hm_pb2_grpc.py ../bin/
	chmod +x ../bin/hmonitor
	chmod +x ../bin/main.py

static:
	mkdir -pv static; protoc hm.proto --js_out=./static/; cp templates/*.js templates/*.css ./static/

uninstall:
	rm -fv ../bin/hmonitor ../bin/main.py ../bin/hm_pb2.py ../bin/hm_pb2_grpc.py 
	rm -rfv ../bin/templates ../bin/static
	rmdir ../bin