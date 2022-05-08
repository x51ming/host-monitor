# 编译

`make -C src install`

# 本地测试

- shell-1: `GOHM_ADDR=127.0.0.1:9203 GOHM_ALLOW=127.0.0.1/8 bin/hmonitor`

- shell-2: `cp $setting bin/settings.py ; bin/main.py`

- 浏览器打开:  `http://{IP}:5000`

# 部署上线

- 将`bin/hmonitor`拷贝到要监控的主机上，在要监控的机器上运行`hmonitor`， 依赖`NVML`（nvidia的库，这也是nvidia-smi的依赖），能用nvidia-smi就能用hmonitor，主要是各个机器的`python`不统一，有的没`pip`，所以采用直接部署可执行文件的方式
 

- 将整个`bin`目录拷贝到管理主机上，在管理主机上运行`main.py`，依赖库`grpcio grpcio-tools flask`，需要在`bin`目录下创建`settings.py`

# settings.py

- 导出一个字典，形如

```python
servers = {"local": "127.0.0.1:9203"}
```

# 一些说明

- hmonitor不需要管理员权限，环境变量GOHM_ADDR为监听的地址和端口，GOHM_ALLOW为允许访问API的机器，如10.1.2.3/32表示只有管理主机10.1.2.3允许获取每个机器的状态，设置成前端所部署在的服务器即可
  
- 前端也不需要管理员权限

- main.go中为了获取本机ip，硬编码了"10."，即在所有IP中最后一个10.开头的，才会显示在hostInfo.Ip中，否则该机器IP在前端会显示成空，对监控没影响

- 所有通信都未经过加密，如果有证书，可以使用SSL/TLS

- 本代码中未包含与实验室具体IP相关的参数，运行时需要自行设定`GOHM_ALLOW GOHM_ADDR settings.py`

# 原理

- 监控部分：NVML(NVIDIA Management Library) + golang

- 主机间通信部分：protobuf + gRPC

- 前端、前后端通信：flask + protobuf + base64


# 效果

![截图](snapshot.png)


# protobuf

- 下面是具体的protobuf定义

- 目前GPU相关信息采集已经实现

- DISK相关信息待开发

```protobuf
syntax = "proto3";
package gpu;
option go_package=".";
message ProcInfo {
    uint32 pid = 1;
    int32 uid = 2;
    string username = 3;
    string basename = 4;
    uint64 expiration = 5;
    int32 utilization = 6;
    uint64 mem = 7;
}
message GPUInfo{
    int32 id = 1;
    uint64 mem_used = 2;
    uint64 mem_total = 3;
    int32 utilization = 4;
    uint32 temp = 5;
    string name = 6;
    uint32 fanspeed = 7;
    repeated ProcInfo procs = 8;
}
message DiskInfo {
    string device = 1;
    uint64 used = 2;
    uint64 total = 3;
    string mount = 4;
}
message HostInfo {
    string id = 1;
    repeated GPUInfo gpus = 2;
    repeated DiskInfo disks = 3;
    string ip = 4;
    string hostname = 5;
    string err = 6;
}


message RequestInfo {
    string token = 1; // reserved
    string reqtype = 2; 
}

service HostMonitor {
    rpc GetInfo (RequestInfo) returns (HostInfo) {}
}

message HistReq{
    string id = 1;
    uint64 timestamp = 2;
    string type = 3;
}

message HistResp{
    repeated uint64 t = 1;
    repeated uint64 v = 2;
}

message HistMap{
    map<string, HistResp> data = 1;
}

service History {
    rpc GetHistory (HistReq) returns (HistResp) {}
}
```