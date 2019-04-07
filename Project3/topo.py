from itertools import izip, product
import os
import subprocess
import sys
import time

from mininet.clean import cleanup
from mininet.cli import CLI
from mininet.node import Node
from mininet.link import TCLink
from mininet.log import setLogLevel, info
from mininet.net import Mininet
from mininet.topo import Topo
from mininet.util import dumpNodeConnections, dumpNetConnections

class LinuxRouter( Node ):
    def config( self, **params ):
        super( LinuxRouter, self ).config( **params )
        self.cmd( 'sysctl net.ipv4.ip_forward=1' )

    def terminate( self ):
        self.cmd( 'sysctl net.ipv4.ip_forward=0' )
        super( LinuxRouter, self ).terminate()

class DumbbellTopo( Topo ):
    BACKBONE_BANDWIDTH_MBPS = 984
    ACCESS_ROUTER_BANDWIDTH_MBPS = 252
    HOST_BANDWIDTH_MBPS = 960

    BACKBONE_BANDWIDTH_PPMS = 82
    ACCESS_ROUTER_BANDWIDTH_PPMS = 21
    HOST_BANDWIDTH_PPMS = 80

    def build( self, delay_ms=21 ):
        # Some constants defining our network parameters.
        self.bandwidth_delay_product = DumbbellTopo.ACCESS_ROUTER_BANDWIDTH_PPMS * delay_ms
        self.backbone_queue_size = self.bandwidth_delay_product
        self.access_router_queue_size = int(0.2 * self.bandwidth_delay_product)

        # Add the backbone switches (L3 routers).
        bb1 = self.addHost( "bb1", cls=LinuxRouter, ip="10.0.0.1/24", defaultRotue="via 10.0.0.2" )
        bb2 = self.addHost( "bb2", cls=LinuxRouter, ip="10.0.0.2/24", defaultRoute="via 10.0.0.1" )

        # Set up link between backbone routers with given one-way propagation delay.
        delay_str = "%dms" % delay_ms
        self.addLink( bb1, bb2,
                      intfName1="bb1-eth0",
                      intfName2="bb2-eth0",
                      bw=DumbbellTopo.BACKBONE_BANDWIDTH_MBPS,
                      delay=delay_str,
                      max_queue_size=self.backbone_queue_size )

        # Add the access routers (L2 switches).
        ar1 = self.addSwitch( "ar1" )
        ar2 = self.addSwitch( "ar2" )

        # Setup the links between each access router and its corresponding backbone router.
        self.addLink( ar1, bb1, intfName2="bb1-eth1",
                      bw=DumbbellTopo.ACCESS_ROUTER_BANDWIDTH_MBPS,
                      max_queue_size=self.access_router_queue_size )

        self.addLink( ar2, bb2, intfName2="bb2-eth1",
                      bw=DumbbellTopo.ACCESS_ROUTER_BANDWIDTH_MBPS,
                      max_queue_size=self.access_router_queue_size )

        # Add the hosts.
        s1 = self.addHost( "s1", ip="10.0.1.2/24", defaultRoute="via 10.0.1.1" )
        s2 = self.addHost( "s2", ip="10.0.1.3/24", defaultRoute="via 10.0.1.1" )
        r1 = self.addHost( "r1", ip="10.0.2.2/24", defaultRoute="via 10.0.2.1" )
        r2 = self.addHost( "r2", ip="10.0.2.3/24", defaultRoute="via 10.0.2.1" )

        # Setup the links between each access router and its hosts.
        self.addLink( s1, ar1, bw=DumbbellTopo.HOST_BANDWIDTH_MBPS )
        self.addLink( s2, ar1, bw=DumbbellTopo.HOST_BANDWIDTH_MBPS )
        self.addLink( r1, ar2, bw=DumbbellTopo.HOST_BANDWIDTH_MBPS )
        self.addLink( r2, ar2, bw=DumbbellTopo.HOST_BANDWIDTH_MBPS )

def main( duration_sec, delay_sec, delay_ms, cc_alg, results_path, interactive=False ):
    topo = DumbbellTopo( delay_ms=delay_ms )
    net = Mininet( topo=topo, link=TCLink, autoStaticArp=True )
    net.start()

    try:
        # Update our access router interfaces to limit their transmit speeds to only 252 Mbps. Note that
        # this has to come after we start the network because during testing it seemed that net.start()
        # reloaded the original bandwidth that was set when the associated link was first created.
#        ars = (net["ar1"], net["ar2"])
#        ar_neighbors = (
#            (net["s1"], net["s2"], net["bb1"]),
#            (net["r1"], net["r2"], net["bb2"])
#        )

#        for ar, neighbors in izip( ars, ar_neighbors ):
#            for neighbor in neighbors:
                # This basically returns a list of pairs where for each pair the first item is the
                # interface on self and the second item is the interface on the node passed to
                # connectionsTo.
                #
                # According to the NIST study, bandwidth on the access router interfaces is 252 Mbps and
                # queue size is 20% of bandwidth delay product.
                #
#                ar_iface, _ = ar.connectionsTo( neighbor )[0]
#                ar_iface.config( bw=DumbbellTopo.ACCESS_ROUTER_BANDWIDTH_MBPS,
#                                 max_queue_size=topo.access_router_queue_size )

        # TCLink ignores any sort of IP address we might specify for non-default interfaces when we are
        # creating links via Topo.addLink. This reassigns the addresses we want for those interfaces on
        # our backbone routers. We also add routing rules to each backbone router so that each router
        # can forward traffic to the subnet they are not directly connected to.
        net["bb1"].intf( "bb1-eth1" ).setIP( "10.0.1.1/24" )
        net["bb2"].intf( "bb2-eth1" ).setIP( "10.0.2.1/24" )
        net["bb1"].cmd( "route add -net 10.0.2.0 netmask 255.255.255.0 gw 10.0.0.2 dev bb1-eth0" )
        net["bb2"].cmd( "route add -net 10.0.1.0 netmask 255.255.255.0 gw 10.0.0.1 dev bb2-eth0" )

        info( "Dumping host connections\n" )
        dumpNodeConnections( net.hosts )

        info( "Dumping net connections\n" )
        dumpNetConnections( net )

        # Get rid of initial delay in network.
        net.pingAll()

        if interactive:
            CLI( net )
        else:
            # Restart tcp_probe.
            print "Restarting tcp_probe"
            subprocess.call( 'modprobe -r tcp_probe', shell=True )
            subprocess.call( 'modprobe tcp_probe full=1', shell=True )

            read_tcp_probe_command = 'dd if=/proc/net/tcpprobe of=%s' % results_path
            subprocess.call( '%s &' % read_tcp_probe_command, shell=True )

            try:
                # Run one iperf stream between r1 and s1 and another between r2 and s2.
                print "Running iperf tests"
                print "Sender 1 duration: %d" % duration_sec
                print "Sender 2 duration: %d" % (duration_sec - delay_sec)
                print "Sender 2 delay: %d" % delay_sec
    
                r1_output = "r1-output-%d-%s.txt" % (delay_ms, cc_alg)
                r2_output = "r2-output-%d-%s.txt" % (delay_ms, cc_alg)
                s1_output = "s1-output-%d-%s.txt" % (delay_ms, cc_alg)
                s2_output = "s2-output-%d-%s.txt" % (delay_ms, cc_alg)

                # 1500 == MTU.
                iperf_window = topo.bandwidth_delay_product * 1500
                print "Iperf window (bytes): %d" % iperf_window

                net["r1"].sendCmd( 'iperf -s -p 5001 -w %d &> %s' % (iperf_window, r1_output) )
                net["r2"].sendCmd( 'iperf -s -p 5002 -w %d &> %s' % (iperf_window, r2_output) )
    
                net["s1"].sendCmd( 'iperf -c %s -p 5001 -i 1 -w %d -t %d -Z %s &> %s' %
                                   (net["r1"].IP(), iperf_window, duration_sec, cc_alg, s1_output) )

                # Delay the second sender by a certain amount and then start it.
                time.sleep( delay_sec )
                net["s2"].sendCmd( 'iperf -c %s -p 5002 -i 1 -w %d -t %d -Z %s &> %s' %
                                   (net["r2"].IP(), iperf_window, duration_sec - delay_sec, cc_alg, s2_output) )

                # Wait for all iperfs to close. On server side, we need to send sentinel to output for
                # waitOutput to return.
                net["s2"].waitOutput()
                net["s1"].waitOutput()
    
                net["r2"].sendInt()
                net["r2"].waitOutput()
    
                net["r1"].sendInt()
                net["r1"].waitOutput()
                print "Completed iperf tests"
            finally:
                # Stop tcp_probe.
                print "Stopping tcp_probe"
                subprocess.call( 'pkill -f "%s"' % read_tcp_probe_command, shell=True )
                subprocess.call( 'modprobe -r tcp_probe', shell=True )
    finally:
        net.stop()

if __name__ == "__main__":
    duration_sec = 1000
    delay_sec = 250
    #delays = [21, 81, 162]
    #cc_algs = ["reno", "cubic", "dctcp", "cdg"]
    delays = [21]
    cc_algs = ["reno", "cubic"]

    for delay_ms, cc_alg in product( delays, cc_algs ):
        print "Running simulation for delay=%sms, CC algorithm=%s" % (delay_ms, cc_alg)

        # NOTE: sys.path[0] is defined to be the directory containing the script used to
        # invoke the Python interpreter, i.e., this script's directory.
        results_path = os.path.join( sys.path[0],
            "tcp-probe-results-%s-%s.txt" % (delay_ms, cc_alg) )
        setLogLevel( 'info' )
        main( duration_sec, delay_sec, delay_ms, cc_alg, results_path, interactive=False )
        cleanup()
