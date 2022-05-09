package main

/*
compile:
	go mod init <any-name-you-like>
	go get -u -v github.com/golang/protobuf/protoc-gen-go
	# download protoc from github or install via apt
	protoc --go_out=plugins=grpc:. --go_opt=paths=source_relative hm.proto
	sed -i 's/package __/package main/' hm.pb.go
	go mod tidy
*/
import (
	context "context"
	"encoding/csv"
	"log"
	"net"
	"os"
	"strings"
	"syscall"

	"github.com/NVIDIA/go-nvml/pkg/nvml"
	"github.com/shirou/gopsutil/process"
	grpc "google.golang.org/grpc"
	"google.golang.org/grpc/reflection"
)

type server struct{}

func (s *server) GetInfo(ctx context.Context, in *RequestInfo) (*HostInfo, error) {
	if hostInfo.Err == "" {
		for i, dev := range devices {
			hostInfo.Gpus[i] = getDevice(dev)
		}
	}

	UpdateDiskInfo()
	return &hostInfo, nil
}

func getDevice(device nvml.Device) *GPUInfo {
	info := &GPUInfo{}
	i, _ := device.GetIndex()
	info.Id = int32(i)
	info.Name, _ = device.GetName()
	info.Temp, _ = device.GetTemperature(0)
	ut, _ := device.GetUtilizationRates()
	info.Utilization = int32(ut.Gpu)
	mm, _ := device.GetMemoryInfo()
	info.MemUsed = mm.Used
	info.MemTotal = mm.Total

	info.Fanspeed, _ = device.GetFanSpeed()

	procs, state := device.GetComputeRunningProcesses()
	if state == nvml.SUCCESS {
		info.Procs = []*ProcInfo{}
		for _, p := range procs {
			thisInfo := &ProcInfo{
				Pid: p.Pid,
				Mem: p.UsedGpuMemory,
			}
			if ps, err := process.NewProcess(int32(p.Pid)); err == nil {
				thisInfo.Username, _ = ps.Username()
				thisInfo.Basename, _ = ps.Name()
			}
			info.Procs = append(info.Procs, thisInfo)
		}
	}

	return info
}

var devices []nvml.Device
var hostInfo HostInfo

var Allowed *net.IPNet
var err error

func main() {
	// 初始化，读取环境变量
	allowedIP := os.Getenv("GOHM_ALLOW")
	if allowedIP == "" {
		allowedIP = "127.0.0.1/32"
	}
	_, Allowed, err = net.ParseCIDR(allowedIP)
	if err != nil {
		log.Fatalf("Wrong format AllowIP: %s\n", allowedIP)
	}
	log.Printf("Allowed IP: %s\n", Allowed.String())

	// 处理本机IP信息
	if err := localIP(); err != nil {
		log.Fatalln(err)
	}

	// 处理显卡相关信息
	ret := nvml.Init()
	if ret != nvml.SUCCESS {
		log.Printf("Unable to initialize NVML: %v\n", nvml.ErrorString(ret))
		hostInfo.Err = nvml.ErrorString(ret)
	} else {

		defer func() {
			ret := nvml.Shutdown()
			if ret != nvml.SUCCESS {
				log.Fatalf("Unable to shutdown NVML: %v\n", nvml.ErrorString(ret))
			}
		}()

		count, ret := nvml.DeviceGetCount()
		if ret != nvml.SUCCESS {
			log.Printf("Unable to get device count: %v\n", nvml.ErrorString(ret))
			hostInfo.Err = nvml.ErrorString(ret)
		} else {
			devices = make([]nvml.Device, count)
			hostInfo.Gpus = make([]*GPUInfo, count)
			for i := 0; i < count; i++ {
				devices[i], ret = nvml.DeviceGetHandleByIndex(i)
				if ret != nvml.SUCCESS {
					log.Printf("Unable to get device at index %d: %v", i, nvml.ErrorString(ret))
					hostInfo.Err = nvml.ErrorString(ret)
					break
				}
			}
		}
	}

	// 启动服务器
	listen_addr := os.Getenv("GOHM_ADDR")
	if listen_addr == "" {
		listen_addr = "0.0.0.0:9203"
	}
	lis, err := NewListenerWithAC("tcp4", listen_addr)
	if err != nil {
		log.Fatalf("监听端口失败: %s\n", err)
		return
	}
	s := grpc.NewServer()
	RegisterHostMonitorServer(s, &server{})
	reflection.Register(s)
	err = s.Serve(lis)
	if err != nil {
		log.Fatalf("开启服务失败: %s\n", err)
		return
	}
}

func localIP() error {
	addrs, err := net.InterfaceAddrs()
	if err != nil {
		return err
	}
	for _, address := range addrs {
		if ipnet, ok := address.(*net.IPNet); ok && !ipnet.IP.IsLoopback() {
			if ipnet.IP.To4() != nil &&
				ipnet.IP.String()[:3] == "10." {
				hostInfo.Id = strings.Split(ipnet.IP.String(), ".")[3]
				hostInfo.Ip = ipnet.IP.String()
			}
		}
	}
	return nil
}

type ListenerWithAC struct {
	Lc net.Listener
}

func NewListenerWithAC(network, address string) (net.Listener, error) {
	lc, err := net.Listen(network, address)
	return ListenerWithAC{Lc: lc}, err
}

func (lc ListenerWithAC) Accept() (net.Conn, error) {
	conn, err := lc.Lc.Accept()
	if err != nil {
		return conn, err
	}
	remote := conn.RemoteAddr().String()
	anchor := strings.LastIndex(remote, ":")
	remote = remote[:anchor]
	ip := net.ParseIP(remote)
	if Allowed.Contains(ip) {
		return conn, nil
	}
	log.Printf("Reject: %s\n", remote)
	_ = conn.Close()
	return conn, nil
}

func (lc ListenerWithAC) Close() error {
	return lc.Lc.Close()
}

func (lc ListenerWithAC) Addr() net.Addr {
	return lc.Lc.Addr()
}

type DiskStatus struct {
	All   uint64 `json:"all"`
	Used  uint64 `json:"used"`
	Free  uint64 `json:"free"`
	Dev   string `json:"device"`
	Mount string `json:"mount"`
	Type  string `json:"type"`
}

// disk usage of path/disk
func DiskUsage(disk *DiskStatus) {
	fs := syscall.Statfs_t{}
	err := syscall.Statfs(disk.Mount, &fs)
	if err != nil {
		return
	}
	disk.All = fs.Blocks * uint64(fs.Bsize)
	disk.Free = fs.Bfree * uint64(fs.Bsize)
	disk.Used = disk.All - disk.Free
}

func ParseMounts() ([]DiskStatus, error) {
	ret := make([]DiskStatus, 0)
	f, err := os.Open("/proc/mounts")
	if err != nil {
		return ret, err
	}
	reader := csv.NewReader(f)
	reader.Comma = ' '
	rec, err := reader.ReadAll()
	if err != nil {
		return ret, err
	}
	for _, line := range rec {
		if strings.HasPrefix(line[2], "ext") {
			st := DiskStatus{
				Dev:   line[0],
				Mount: line[1],
				Type:  line[2],
			}
			DiskUsage(&st)
			ret = append(ret, st)
		}
	}
	return ret, nil
}

func UpdateDiskInfo() {
	disks, err := ParseMounts()
	if err != nil {
		log.Println(err)
		return
	}

	hostInfo.Disks = make([]*DiskInfo, 0)
	for _, d := range disks {
		hostInfo.Disks = append(hostInfo.Disks, &DiskInfo{
			Device: d.Dev,
			Mount:  d.Mount,
			Total:  d.All,
			Used:   d.Used,
		})
	}
}
