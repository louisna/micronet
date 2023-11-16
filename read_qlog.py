from utils import *
import argparse
from jsonseq.decode import JSONSeqDecoder
import matplotlib.pyplot as plt
import numpy as np


def read_json(filename):
    with open(filename) as fd:
        data = [obj for obj in JSONSeqDecoder().decode(fd)]
    return data


def plot_stream(args):
    data = read_json(args.filename)
    stream_data = list()
    for obj in data[1:]:
        if obj["name"] == "transport:packet_sent":
            stream_data.append((obj["time"], obj["data"]["raw"]["length"]))
    
    stream_data = sorted(stream_data)
    x = [i[0] for i in stream_data]
    y = [i[1] for i in stream_data]

    fig, ax = plt.subplots()
    ax.scatter(x, y, s=3)
    # ax.set_xlim((3000, 4000))
    plt.savefig("test-stream_len.png")


def plot_cwin(args):
    data = read_json(args.filename)
    cwin = list()
    for obj in data[1:]:
        if obj["name"] == "recovery:metrics_updated":
            if "congestion_window" in obj["data"]:
                cwin.append((obj["time"], obj["data"]["congestion_window"]))
    
    x = [i[0] for i in cwin]
    y = [i[1] for i in cwin]

    fig, ax = plt.subplots()
    if args.line:
        ax.plot(x, y, marker="*")
    else:
        ax.scatter(x, y, s=3)

    # Plot baseline
    debit = 10000000
    cwin = debit * 0.2 / 8
    # ax.hlines(cwin, -100, max(x) + 1000)
    ax.set_xlim((min(x), max(x)))
    # ax.set_ylim((0, 60000))
    ax.set_xlabel("Time [ms]")
    ax.set_ylabel("Cwin [bytes?]")
    plt.savefig("test-cc.png")
    

def plot_fec(args):
    files = args.filename.split(",")
    recovered_info = dict()
    for i, file in enumerate(files):
        data = read_json(file)

        # Look for FEC information only.
        fec_rec = list()
        for obj in data[1:]:
            if obj["name"] == "transport:fec_recovered":
                fec_rec.append(obj["data"]["ssid"])
        
        recovered_info[i] = fec_rec
    
    # Cumulative sum.
    y_s = dict()
    for k, v in recovered_info.items():
        y_s[k] = np.cumsum([1] * len(v))

    fig, ax = plt.subplots()
    for i, rec_info in recovered_info.items():
        ax.step(rec_info, y_s[i], label=i)
    ax.legend()
    ax.set_xlabel("Recovered SSID")
    ax.set_ylabel("Cumulated number of recovered symbols")
    plt.savefig("fec.png")


def plot_reliable(args):
    files = args.filename.split(",")
    retransmit_info = dict()
    for i, file in enumerate(files):
        data = read_json(file)
        for obj in data[1:]:
            if obj["name"] == "transport:mc_retransmit":
                retr_obj = obj["data"]
                client_id = retr_obj["client_id"]
                if args.frames:
                    tmp = retransmit_info.get(client_id, list())
                    tmp.append((retr_obj["stream_id"], retr_obj["offset"], retr_obj["len"], retr_obj["fin"]))
                else:
                    tmp = retransmit_info.get(client_id, set())
                    tmp.add(retr_obj["stream_id"])
                retransmit_info[client_id] = tmp
    
    # Sort the streams by ID.
    x_s = dict()
    for k, v in retransmit_info.items():
        x_s[k] = sorted(list(v))
    
    # Cumulative sum.
    y_s = dict()
    for k, v in x_s.items():
        y_s[k] = np.cumsum([1] * len(v))

    fig, ax = plt.subplots()
    for i, stream_ids in x_s.items():
        if args.frames:
            stream_ids = [i[0] for i in stream_ids]
        ax.step(stream_ids, y_s[i], label=i)
    ax.legend()
    ax.set_xlabel("Retransmitted stream ids")
    ax.set_ylabel("Cumulated number of retransmissions")
    plt.savefig("retransmission.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("filename", help="Filename containing the sQLOG trace; or list separated by commas")
    parser.add_argument("--type", help="Type of plot to do", choices=["stream", "cwin", "fec", "reliable"], default="cwin", type=str)
    parser.add_argument("--line", help="Do line plot instead of scatter", action="store_true")
    parser.add_argument("--frames", help="For reliable, count the number of retransmitted frames instead of streams", action="store_true")
    args = parser.parse_args()

    match args.type:
        case "cwin":
            plot_cwin(args)
        case "stream":
            plot_stream(args)
        case "fec":
            plot_fec(args)
        case "reliable":
            plot_reliable(args)