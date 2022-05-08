#!/usr/bin/env python3
from flask import Flask, render_template
from threading import Thread
from flask import jsonify
import time
from dataclasses import dataclass
from typing import Dict, List
import hm_pb2
import base64
try:
    from settings import servers as servers
    print(servers)
except Exception as e:
    print(e)
    servers = {"local": "127.0.0.1:9203"}
####################
# global
####################


@dataclass
class GlobalState:
    server_ip_port: Dict[str, str]
    server_names: List[str]
    server_responses: Dict[str, hm_pb2.HostInfo]

    timestamps: Dict[str, List[int]]
    history_data_fan: Dict[str, List[int]]
    history_data_gpumem: Dict[str, List[int]]
    history_data_temp: Dict[str, List[int]]
    history_data_util: Dict[str, List[int]]


g = GlobalState(servers, list(servers.keys()), dict(),
                {}, {}, {}, {}, {})


def update_server_data(threads=8):
    from concurrent.futures import ThreadPoolExecutor
    for resp, name in ThreadPoolExecutor(threads).map(get_data, g.server_names):
        g.server_responses[name] = resp


def get_data(name):
    import grpc
    import hm_pb2
    import hm_pb2_grpc
    try:
        now = time.time_ns()

        with grpc.insecure_channel(g.server_ip_port[name]) as channel:
            stub = hm_pb2_grpc.HostMonitorStub(channel)
            response: hm_pb2.HostInfo = stub.GetInfo(hm_pb2.RequestInfo())

            for v in response.gpus:
                gpu_id = name+"_"+str(v.id)
                g.timestamps.setdefault(gpu_id, []).append(
                    now)
                g.history_data_gpumem.setdefault(gpu_id, []).append(
                    int(v.mem_used / v.mem_total * 10000))
                g.history_data_util.setdefault(gpu_id, []).append(
                    v.utilization)
                g.history_data_temp.setdefault(gpu_id, []).append(
                    v.temp)
                g.history_data_fan.setdefault(gpu_id, []).append(
                    v.fanspeed)

            return response, name
    except Exception as e:
        # print(e)
        return hm_pb2.HostInfo(id=name, err=str(e)), name


app = Flask(__name__)


@app.route("/")
def greet():
    return render_template('all.html', servers=g.server_responses)


@app.route("/hist")
def greet1():
    return jsonify(g.history_data_gpumem)


pickle_header = [("Content-Type", "application/octet-stream"),
                 ("Access-Control-Allow-Origin", "*")]


@app.route("/pk")
def greet2():
    import hm_pb2
    obj = hm_pb2.HistMap(data={
        k: hm_pb2.HistResp(
            t=g.timestamps[k],
            v=g.history_data_gpumem[k]) for k in g.history_data_gpumem
    }).SerializeToString()
    return base64.b64encode(obj), 200


def filter_len(gg:GlobalState, max_len = 6 * 60 * 24 * 10):
    # 最长保留十天
    for name in gg.server_names:
        n = len(gg.timestamps.get(name, []))
        if n > max_len:
            gg.timestamps[name] = gg.timestamps[name][n-max_len:]
            gg.history_data_fan[name] = gg.history_data_fan[name][n-max_len:]
            gg.history_data_gpumem[name] = gg.history_data_gpumem[name][n-max_len:]
            gg.history_data_temp[name] = gg.history_data_temp[name][n-max_len:]
            gg.history_data_util[name] = gg.history_data_util[name][n-max_len:]


def update():
    import time
    import pickle as pk
    global g
    try:
        with open("last.pk", "rb") as f:
            _1 = g.server_ip_port.copy()
            _2 = g.server_names.copy()
            _3 = dict()
            g = pk.load(f)
            filter_len(g)
            g.server_ip_port = _1
            g.server_names = _2
            g.server_responses = _3
    except Exception as e:
        print(e)

    last_save = 0
    while 1:
        try:
            update_server_data()
        except Exception as e:
            print(e)

        now = time.time()
        if now - last_save > 60 * 10:
            with open("last.pk", "wb") as f:
                filter_len(g)
                pk.dump(g, f)
            last_save = now
        time.sleep(10)


if __name__ == "__main__":
    # Thread(target=server.serve).start()
    Thread(target=update).start()
    app.run("0.0.0.0", 5000, debug=False)
