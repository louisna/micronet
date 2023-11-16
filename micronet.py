import argparse
import os

MC_TABLE_NAME = "smcroute"

def ipv6(do_ipv6):
    return "-6" if do_ipv6 else "" 


class MicroNet:
    def __init__(self):
        self.netns = set()
        self.links = set()
        self.node2link = dict()
        self.loopbacks = dict()

    def add_netns(self, namespace: str):
        if namespace not in self.netns:
            os.system(f"ip netns add {namespace}")
            self.netns.add(namespace)

            # Activate IPv4.
            cmd = f"ip netns exec {namespace} sysctl net.ipv4.ip_forward=1"
            os.system(cmd)
    
    def add_link(self, n1, n2):
        if n1 not in self.netns or n2 not in self.netns:
            print(f"{n1} or {n2} not in the topology.")
            return
        
        self.links.add((n1, n2))
        l = self.node2link.get(n1, list())
        l.append(n2)
        self.node2link[n1] = l
        l = self.node2link.get(n2, list())
        l.append(n1)
        self.node2link[n2] = l
        
        link_lb = lambda i: f"veth-{n1}-{n2}-{i}"
        print(f"Add interfaces {link_lb(0)} and {link_lb(1)}")
        
        # Create new link.
        cmd = f"ip link add {link_lb(0)} type veth peer name {link_lb(1)}"
        os.system(cmd)

        # Assign to each namespace.
        cmd = f"ip link set {link_lb(0)} netns {n1}"
        os.system(cmd)
        cmd = f"ip link set {link_lb(1)} netns {n2}"
        os.system(cmd)

        # Assign IPv4 address to the link.
        # cmd = f"ip -n {n1} addr add {addr1} dev {link_lb(0)}"
        # os.system(cmd)
        # cmd = f"ip -n {n2} addr add {addr2} dev {link_lb(1)}"
        # os.system(cmd)
        # # TODO: do the same for IPv6.

        # Set the links (and the loopback of the namespace) up.
        cmd = f"ip -n {n1} link set dev lo up"
        os.system(cmd)
        cmd = f"ip -n {n1} link set dev {link_lb(0)} up"
        os.system(cmd)
        cmd = f"ip -n {n2} link set dev lo up"
        os.system(cmd)
        cmd = f"ip -n {n2} link set dev {link_lb(1)} up"
        os.system(cmd)

        # Remove TSO and GSO.
        cmd = f"ip netns exec {n1} ethtool -K {link_lb(0)} tso off"
        os.system(cmd)
        cmd = f"ip netns exec {n2} ethtool -K {link_lb(1)} tso off"
        os.system(cmd)
        cmd = f"ip netns exec {n1} ethtool -K {link_lb(0)} gso off"
        os.system(cmd)
        cmd = f"ip netns exec {n2} ethtool -K {link_lb(1)} gso off"
        os.system(cmd)
    
    def add_loopbacks(self, loopbacks_file, do_ipv6):
        with open(loopbacks_file) as fd:
            txt = fd.read().split("\n")
            for loopback_info in txt:
                if len(loopback_info) == 0:
                    continue
                ns1, loopback = loopback_info.split(" ")
                cmd = f"ip netns exec {ns1} ip {ipv6(do_ipv6)} addr add {loopback} dev lo"
                self.loopbacks[ns1] = loopback[:-3]
                os.system(cmd)
    
    def add_link_addr(self, links_file, do_ipv6):
        with open(links_file) as fd:
            txt = fd.read().split("\n")
            for link_info in txt:
                if len(link_info) == 0:
                    continue
                ns1, ns2, _, link, loopback = link_info.split(" ")
                if ns1 < ns2:
                    itf = f"veth-{ns1}-{ns2}-0"
                else:
                    itf = f"veth-{ns2}-{ns1}-1"

                # cmd = f"ip netns exec {ns1} sysctl net.ipv4.{itf}.ip_forward=1"
                # print("aaa")
                # os.system(cmd)
                cmd = f"ip netns exec {ns1} ip {ipv6(do_ipv6)} addr add {link} dev {itf}"
                os.system(cmd)
    
    def add_paths(self, paths_file, do_ipv6):
        with open(paths_file) as fd:
            txt = fd.read().split("\n")
            for path_info in txt:
                if len(path_info) == 0:
                    continue
                ns1, itf, link, loopback = path_info.split(" ")
                cmd = f"ip netns exec {ns1} ip {ipv6(do_ipv6)} route add {loopback} via {link}"
                print("Path command", cmd)
                os.system(cmd)
    
    def add_mc_paths(self, mc_paths_file):
        with open(mc_paths_file) as fd:
            txt = fd.read().split("\n")
            for path_info in txt:
                if len(path_info) == 0:
                    continue
                tab = path_info.split()
                node_id, in_itf, mc_group, out_itf = tab[0], tab[1], tab[2], tab[3:]
                out_itf_txt = ""
                src = self.node2link[node_id][int(in_itf)]
                for itf_idx in out_itf:
                    # Node index of the ith index.
                    nei = self.node2link[node_id][int(itf_idx)]
                    out_itf_txt += f"veth-{min(node_id, nei)}-{max(node_id, nei)}-{1 if node_id > nei else 0}"
                cmd = f"smcrouted -l debug -I {MC_TABLE_NAME}-{node_id} && smcroutectl -I {MC_TABLE_NAME}-{node_id} add veth-{min(node_id, src)}-{max(node_id, src)}-{1 if node_id > src else 0} {mc_group.split('/')[0]} {out_itf_txt}"
                print(node_id, cmd)

    def set_bw_delay_loss(self, bw, delay, loss):
        tmp = lambda ns, itf: f"ip netns exec {ns} tc qdisc add dev {itf} root netem delay {delay}ms rate {bw}mbit loss {int(loss)}%"
        for ns in self.netns:
            for nei in self.node2link[ns]:
                itf = f"veth-{min(ns, nei)}-{max(ns, nei)}-{1 if ns > nei else 0}"
                cmd = tmp(ns, itf)
                print(cmd)
                os.system(cmd)    

    def create_topo(loopbacks, links, paths, multicast, ipv6):
        net = MicroNet()

        # Add node network namespace.
        with open(loopbacks) as fd:
            txt = fd.read().split("\n")
            for node_info in txt:
                if len(node_info) == 0: continue
                node, loopback = node_info.split(" ")
                net.add_netns(node)
        
        # Add links between namespaces.
        print("Add links")
        with open(links) as fd:
            txt = fd.read().split("\n")
            for link_info in txt:
                if len(link_info) == 0: continue
                ns1, ns2, _, _, _ = link_info.split(" ")
                if (ns1, ns2) in net.links or (ns2, ns1) in net.links: continue
                net.add_link(ns1, ns2)
        
        # Add loopback addresses.
        print("Add loopbacks")
        net.add_loopbacks(loopbacks, args.ipv6)

        # Add links addresses.
        print("Add addresses")
        net.add_link_addr(links, args.ipv6)

        # Add paths.
        net.add_paths(paths, args.ipv6)

        # Add multicast routes.
        if multicast is not None:
            net.add_mc_paths(multicast)

        return net
    
    def clean(loopbacks):
        with open(loopbacks) as fd:
            txt = fd.read().split("\n")
            for node_info in txt:
                if len(node_info) == 0: continue
                node, loopback = node_info.split(" ")
                cmd = f"ip netns del {node}"
                os.system(cmd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-l", "--loopbacks", type=str,
                        default="configs/topo-loopbacks.txt")
    parser.add_argument("-i", "--links", type=str, default="configs/topo-links.txt")
    parser.add_argument("-p", "--paths", type=str, default="configs/topo-paths.txt")
    parser.add_argument("-m", "--multicast", help="Add multicast routes in the given path", default=None)
    parser.add_argument("--clean", help="Clean the network namespaces", action="store_true")
    parser.add_argument("--no-build", help="Does not build the network", action="store_true")
    parser.add_argument("--bw", help="Set bandwidth limit in megabits. Default: 1", default=1)
    parser.add_argument("--delay", help="Set bandwidth limit in ms. Default: 1", default=10)
    parser.add_argument("--loss", help="Set loss percentage. Default: 0. Does not work now", default=0.0, type=float)
    parser.add_argument("--ipv6", help="IPv6 instead of IPv4", action="store_true")
    args = parser.parse_args() 

    if args.clean:
        MicroNet.clean(args.loopbacks)
    if not args.no_build:
        net = MicroNet.create_topo(args.loopbacks, args.links, args.paths, args.multicast, args.ipv6)
        net.set_bw_delay_loss(args.bw, args.delay, args.loss)