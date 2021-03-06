#!/usr/bin/env python
# coding: utf-8

# This dumb thing is a way to convince Hubble there's a spunk endpoint here.

import os
import json
import time
import base64
import socket
import urllib3
from flask import Flask, request, jsonify, Response

app = Flask(__name__)
app.logger.setLevel(10)

HTTP = urllib3.PoolManager()
HOSTNAME = socket.getfqdn()
ENDPOINT = f"https://logs.logdna.com/logs/ingest?tags=hubble"
MAX_CONTENT_BYTES = 1e5
MAX_READ = 500000


@app.route("/services/collector/event", methods=["POST", "GET"])
def hec():
    now = int(time.time())
    host = HOSTNAME
    dec = json.JSONDecoder()
    data = request.stream.read(MAX_READ).decode()
    events = list()
    max_loops = 1000
    while data and max_loops > 1:
        max_loops -= 1
        try:
            j, r = dec.raw_decode(data)
            line = dict(app="hec2ldna", line="unknown", timestamp=now)
            for n, nn in (("sourcetype", "app"), ("event", "line"), ("time", "timestamp"), ("fields", "meta")):
                if n in j:
                    line[nn] = j.pop(n)
            if isinstance(line["line"], (list, tuple, dict)):
                e = line["line"]
                line["line"] = json.dumps(e)
                for item in ("host", "dest_host", "dest_fqdn"):
                    if item in e:
                        host = e[item]
                        break
                if "loggername" in e:
                    line["app"] = e["loggername"]
                if "log_level" in e:
                    line["level"] = e["log_level"]
            events.append(line)
            data = data[r:].lstrip()
        except json.JSONDecodeError as e:
            return Response(f"failed to parse remaining json: {e}; {data}", status=300)

    token = os.environ.get("LOGDNA_TOKEN")
    if not token:
        raise ValueError("token required, set LOGDNA_TOKEN env")
    headers = {
        "Authorization": f"Basic {base64.b64encode(token.encode()).decode()}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    if not events:
        return Response("please give me event data. I want the event data.", status=300)
    dat = json.dumps({"lines": events})
    url = f"{ENDPOINT}&hostname={host}&now={now}"
    app.logger.info("events=%d payload=%d url=%s", len(events), len(dat), url)
    res = HTTP.request("POST", url, body=dat, headers=headers)
    # app.logger.info("logdna res=%d %s", res.status, res.data)
    # app.logger.info("logdna payload keys %s", [ (list(x.keys()), list(x['meta'].keys())) for x in events ])
    # app.logger.info("logdna headers %s", res.headers)
    return Response(res.data, status=res.status, headers=dict(res.headers))
