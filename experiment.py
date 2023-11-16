#!/root/venv/bin/python3

import argparse
import os
import time


def ns_system(ns, cmd, wait=True, pre_cmd=""):
    cmd2 = f"{pre_cmd} ip netns exec {ns} {cmd} {'&' if not wait else ''}"
    print(cmd2)
    os.system(cmd2)


def start_server(ns, loopback, nb_clients, nb_frames, expiration_timer, max_fec_rs):
    cmd = f'cargo run --bin mc-server-file --manifest-path ~/multicast-quic/apps/Cargo.toml --features qlog --release -- -s {loopback}:4433 -w {nb_clients} --app file --multicast --expiration-timer {expiration_timer} --authentication none --cert-path ~/multicast-quic/apps/src/bin/ -n {nb_frames} -r test_server_output.txt -k server_key.txt --max-fec-rs {max_fec_rs} --pacing 6 --reliable -u > server-log.txt 2>&1'
    pre_cmd = f'RUST_LOG=trace QLOGDIR="."'
    # pre_cmd = 'QLOGDIR="."'
    ns_system(ns, cmd, wait=False, pre_cmd=pre_cmd)


def start_client(ns, loopback, server_addr, wait=False):
    cmd = f'cargo run --manifest-path ~/multicast-quic/apps/Cargo.toml --bin mc-client-active --release -- {server_addr}:4433 -l {loopback} -o client_test-{ns}.txt --multicast --app file > client-log-{ns}.txt 2>&1'
    pre_cmd = 'RUST_LOG=trace QLOGDIR="."'
    # pre_cmd = ""
    ns_system(ns, cmd, wait, pre_cmd=pre_cmd)


def checkout_output(nb_clients, nb_frames):
    for i in range(1, nb_clients + 1):
        file = f"client_test-{i}.txt"
        with open(file) as fd:
            data = fd.read().strip().split("\n")
            nb_recv = 0
            nb_bytes_recv = 0
            recv_id = set()
            recv_bytes = []
            for line in data:
                if len(line) == 0: continue
                nb_recv += 1
                nb_bytes_recv += int(line.split(" ")[2])
                recv_id.add(int(line.split(" ")[0]))
                recv_bytes.append((int(line.split(" ")[0]), int(line.split(" ")[2])))
        if nb_recv != nb_frames:
            print(f"Not the same amount of received frames for file {file}. Recv: {nb_recv}. Theorerical: {nb_frames}")
            print("Missing frames: ", end="")
            for i in range(nb_frames):
                if i not in recv_id:
                    print(f"{i} ({i * 4 + 3})", end=" ")
            print()
        if nb_frames * 1100 != nb_bytes_recv:
            print("Not the same amount of receives bytes:", end="")
            for i, b in recv_bytes:
                if b < 1100:
                    print(f"{i * 4 + 3}: {b}", end=" ")
            print()
        assert(nb_recv == nb_frames)
        assert(nb_frames * 1100 == nb_bytes_recv)
        print(f"Ok for file {file}")
    print("Ok!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("loopbacks", help="Loopbacks file")
    parser.add_argument("--check-output", help="Check that all data has been received by the clients", action="store_true")
    parser.add_argument("--no-run", help="Does not run the experiment. Used for example to just check previous results", action="store_true")
    parser.add_argument("--nb-frames", help="Number of frames to send", type=int, default=200)
    parser.add_argument("--expiration-timer", help="Expiration timer used for the experiments at the source in ms", default=200, type=int)
    parser.add_argument("--max-fec-rs", help="Maximum number of repair symbols to send each ET", default=5, type=int)
    args = parser.parse_args()

    with open(args.loopbacks) as fd:
        txt = fd.read().split("\n")
        txt = [i for i in txt if len(i) > 0]
    nb_clients = len(txt) - 1
    # Read the loopbacks file and assign to each node.
    if not args.no_run:

            server = True
            server_addr = ""
            for i, line in enumerate(txt):
                tab = line.split(" ")
                ns, addr = int(tab[0]), tab[1][:-3]
                if server:
                    start_server(ns, addr, len(txt) - 1, args.nb_frames, args.expiration_timer, args.max_fec_rs)
                    server_addr = addr
                    time.sleep(1)
                else:
                    start_client(ns, addr, server_addr, wait=i == len(txt) - 1)
                server = False
    
    if args.check_output:
        if not args.no_run:
            print("Sleep for 5 seconds to ensure that the clients have time to write their logs")
            #time.sleep(5)
        checkout_output(nb_clients, args.nb_frames)
