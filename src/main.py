#!/usr/bin/env python3
import re
import click
from flask import Flask, render_template, request, session, redirect
from threading import Thread
from flask import jsonify
from datetime import timedelta
import time
from dataclasses import dataclass
from typing import Dict, List
import hm_pb2
import base64
import dbm
DATABASE = dbm.open("host.db", "c")
for k in DATABASE:
    print(k.decode("utf8"), DATABASE[k].decode("utf8"))

KVSTORE = dbm.open("kvstore.db", "c")
for k in KVSTORE:
    print(k.decode("utf8"), KVSTORE[k].decode("utf8"))
    
try:
    from settings import servers as servers
    print(servers)
except Exception as e:
    print(e)
    servers = {"local": "127.0.0.1:7203"}

try:
    from settings import token as auth_token
    print("auth token:", auth_token)
except Exception as e:
    print(e)
    auth_token = "test"

try:
    from settings import secret as secret
    print("secret:", secret)
except Exception as e:
    print(e)
    import os
    secret = os.urandom(24)
####################

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
        print(name, str(e).replace("\n", ";"))
        return hm_pb2.HostInfo(id=name, err=str(e)), name


#######################
app = Flask(__name__)
app.config['SECRET_KEY'] = secret
app.permanent_session_lifetime = timedelta(days=30)


def parse_exp(data):
    if data == 0:
        return "Unkown"
    if data == 1:
        return "Forever"
    t = time.localtime(data)
    if data < time.time():
        return "Expired"
    styled = time.strftime("%Y-%m-%d", t)
    return styled


def get_note(user, host):
    # print(user, host)
    return DATABASE.get(f"{user}@{host}", default=b"").decode("utf8")


def append(l, v):
    if v in l:
        return ""
    l.append(v)
    return ""


def query(k):
    return KVSTORE.get(k, default=b"").decode("utf8")


app.add_template_filter(append)
app.add_template_filter(parse_exp)
app.add_template_filter(get_note)
app.add_template_filter(len, "get_len")
app.add_template_filter(query)


###########################
@app.route("/")
def greet():
    if session.get("auth", "") != "ok":
        return redirect("/login")
    return render_template('all.html', servers=g.server_responses, notice=query("notice"))


@app.get("/login")
def login1():
    return render_template('login.html')


@app.post("/login")
def login2():
    token = request.form["token"]
    if token == auth_token:
        session["auth"] = "ok"
        session.permanent = True
        return redirect("/")
    return redirect("/login")


@app.route("/pk")
def greet2():
    if session.get("auth", "") != "ok":
        return redirect("/login")
    import hm_pb2
    obj = hm_pb2.HistMap(data={
        k: hm_pb2.HistResp(
            t=g.timestamps[k][::12],
            v=g.history_data_gpumem[k][::12]) for k in g.history_data_gpumem
    }).SerializeToString()
    return base64.b64encode(obj), 200


@app.get("/table")
def greet3():
    if session.get("auth", "") != "ok":
        return redirect("/login")
    return render_template("table.html",
                           labels=["用户", "服务器", "说明"],
                           content=[(
                               k[:k.index(b"@")].decode("utf8"),
                               k[k.index(b"@")+1:].decode("utf8"),
                               DATABASE[k].decode("utf8")) for k in DATABASE])


ALLOWED_KEYS = {"notice"}


@app.post("/set")
def greet6():
    if session.get("auth", "") != "ok":
        return redirect("/login")
    key = request.args.get("key", "notice")
    if key not in ALLOWED_KEYS:
        return "not allowed", 400
    redirect_ = request.args.get("redirect", "/")
    data = request.form.get("value", "")
    # data = data_filter(data)
    KVSTORE[key] = data
    # for k in KVSTORE:
    # print(KVSTORE[k])
    print("[ED1]", request.remote_addr, key, data, "<<")
    return redirect(redirect_)


illegal = re.compile("[\\\\%</>&;]")


def data_filter(s: str):
    s = illegal.sub("", s)
    return s


@app.get("/edit")
def greet4():
    if session.get("auth", "") != "ok":
        return redirect("/login")
    data = request.args
    if data:
        user = data_filter(data.get("user", ""))
        host = data_filter(data.get("host", ""))
        note = data_filter(data.get("note", ""))
        if user and host:
            DATABASE[f"{user}@{host}"] = note
            print("[ED0]", request.remote_addr, user, host, note, "<<")
            return "ok", 200
    return "fail", 400


@app.get("/rm")
def greet5():
    if session.get("auth", "") != "ok":
        return redirect("/login")
    data = request.args
    if data:
        user = data.get("user", "")
        host = data.get("host", "")
        if user and host:
            DATABASE.pop(f"{user}@{host}")
            return "ok", 200
    return "fail", 400


@app.get("/notice")
def greet7():
    return render_template("notice.html", notice=query("notice"))
####################


def filter_len(gg: GlobalState, max_len=6 * 60 * 24 * 10):
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


@ click.command()
@ click.option("--addr", default="0.0.0.0")
@ click.option("--port", default=5000, type=int)
def entry(addr, port):
    Thread(target=update).start()
    app.run(addr, port, debug=False)


if __name__ == "__main__":
    entry()
