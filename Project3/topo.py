from itertools import izip, product
import os
import subprocess
import sys
import time

from mininet.clean import cleanup
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.link import TCLink
from mininet.util import dumpNodeConnections, dumpNetConnections
from mininet.log import setLogLevel, info

def calculate_queue_size( bw_ppms, delay_ms, factor=1.0 ):
    return int( bw_ppms * (delay_ms) * factor )

class DumbbellTopo( Topo ):
    def build( self, delay_ms=21 ):
        # Add the hosts.
        s1 = self.addHost( "s1" )
        s2 = self.addHost( "s2" )
        r1 = self.addHost( "r1" )
        r2 = self.addHost( "r2" )

        # Add the backbone switches.
        bb1 = self.addSwitch( "bb1" )
        bb2 = self.addSwitch( "bb2" )

        # Add the access routers.
        ar1 = self.addSwitch( "ar1" )
        ar2 = self.addSwitch( "ar2" )

        # Set up link between backbone routers with given one-way propagation delay.
        # According to the NIST study, each backbone router can transmit up to 984 Mbps.
        # According to the professor's post on Piazza, we'll also want to set the max queue size to
        # 100% of the bandwidth delay product.
        bb_bw = 984
        bb_ppms = 82
        delay_str = "%dms" % delay_ms
        queue_size = calculate_queue_size( bb_ppms, delay_ms )
        self.addLink( bb1, bb2, bw=bb_bw, delay=delay_str, max_queue_size=queue_size )

        # Setup the links between each access router and its corresponding backbone router and
        # hosts. According to the NIST study:
        #
        #  * Each backbone router can transmit up to 984 Mbps.
        #  * Each host can transmit up to 960 Mbps.
        #  * Each access router can only transmit up to 252 Mbps.
        #
        # To handle this asymmetry, we first create all the links. This will create symmetric,
        # bidirectional links. Afterward, we modify the interface of the access routers to limit
        # their bandwidths.
        #
        # NOTE: We cannot modify the interfaces here because they're technically not created yet.
        # We're only constructing a graph representation of our network topology. Mininet creates
        # the objects in the graph after this method returns. We need to do our interface updates
        # after the Mininet constructor runs inside main().
        #
        host_bw = 960
        ar_bw = 252
        ar_ppms = 21
        ar_queue_size = calculate_queue_size( ar_ppms, delay_ms, factor=0.2 )
        self.addLink( s1, ar1, bw=host_bw )
        self.addLink( s2, ar1, bw=host_bw )
        self.addLink( ar1, bb1, bw=ar_bw, max_queue_size=ar_queue_size )
        self.addLink( r1, ar2, bw=host_bw )
        self.addLink( r2, ar2, bw=host_bw )
        self.addLink( ar2, bb2, bw=ar_bw, max_queue_size=ar_queue_size )

def main( duration_sec, delay_sec, delay_ms, cc_alg, results_path ):
    topo = DumbbellTopo( delay_ms=delay_ms )
    net = Mininet( topo=topo, link=TCLink, autoStaticArp=True )
    net.start()

    # Update our access router interfaces to limit their transmit speeds to only 252 Mbps. Note that
    # this has to come after we start the network because during testing it seemed that net.start()
    # reloaded the original bandwidth that was set when the associated link was first created.
    ars = (net["ar1"], net["ar2"])
    ar_neighbors = (
        (net["s1"], net["s2"], net["bb1"]),
        (net["r1"], net["r2"], net["bb2"])
    )

    for ar, neighbors in izip( ars, ar_neighbors ):
        for neighbor in neighbors:
            # This basically returns a list of pairs where for each pair the first item is the
            # interface on self and the second item is the interface on the node passed to
            # connectionsTo.
            #
            # According to the NIST study, bandwidth on the access router interfaces is 252 Mbps and
            # queue size is 20% of bandwidth delay product.
            #
            ar_iface, _ = ar.connectionsTo( neighbor )[0]
            ar_bw = 252
            ar_ppms = 21
            queue_size = calculate_queue_size( ar_ppms, delay_ms, factor=0.2 )
            #ar_iface.config( bw=252, max_queue_size=queue_size )

    info( "Dumping host connections\n" )
    dumpNodeConnections( net.hosts )

    info( "Dumping net connections\n" )
    dumpNetConnections( net )

    # Get rid of initial delay in network.
    net.pingAll()

    # Restart tcp_probe.
    print "Restarting tcp_probe"
    subprocess.call( 'modprobe -r tcp_probe', shell=True )
    subprocess.call( 'modprobe tcp_probe full=1', shell=True )

    read_tcp_probe_command = 'dd if=/proc/net/tcpprobe of=%s' % results_path
    subprocess.call( '%s &' % read_tcp_probe_command, shell=True )

    # Run one iperf stream between r1 and s1 and another between r2 and s2.
    print "Running iperf tests"
    print "Sender 1 duration: %d" % duration_sec
    print "Sender 2 duration: %d" % (duration_sec - delay_sec)
    print "Sender 2 delay: %d" % delay_sec

    net["r1"].sendCmd( 'iperf -s -p 5001 &> r1-output.txt' )
    net["r2"].sendCmd( 'iperf -s -p 5002 &> r2-output.txt' )

    net["s1"].sendCmd( 'iperf -c %s -p 5001 -i 1 -w 16m -t %d -Z %s &> s1-output.txt' %
        (net["r1"].IP(), duration_sec, cc_alg) )

    # Delay the second sender by a certain amount and then start it.
    time.sleep( delay_sec )
    net["s2"].sendCmd( 'iperf -c %s -p 5002 -i 1 -w 16m -t %d -Z %s &> s2-output.txt' %
        (net["r2"].IP(), duration_sec - delay_sec, cc_alg) )

    # Wait for all iperfs to close. On server side, we need to send sentinel to output for
    # waitOutput to return.
    net["s2"].waitOutput()
    net["s1"].waitOutput()

    net["r2"].sendInt()
    net["r2"].waitOutput()

    net["r1"].sendInt()
    net["r1"].waitOutput()
    print "Completed iperf tests"

    # Stop tcp_probe.
    print "Stopping tcp_probe"
    subprocess.call( 'pkill -f "%s"' % read_tcp_probe_command, shell=True )
    subprocess.call( 'modprobe -r tcp_probe', shell=True )

    net.stop()

if __name__ == "__main__":
    duration_sec = 1000
    delay_sec = 250
    #duration_sec = 100
    #delay_sec = 25
    #delays = [21, 81, 162]
    #cc_algs = ["reno", "cubic", "dctcp", "cdg"]
    delays = [21]
    cc_algs = ["reno"]

    for delay_ms, cc_alg in product( delays, cc_algs ):
        print "Running simulation for delay=%sms, CC algorithm=%s" % (delay_ms, cc_alg)

        # NOTE: sys.path[0] is defined to be the directory containing the script used to
        # invoke the Python interpreter, i.e., this script's directory.
        results_path = os.path.join( sys.path[0],
            "tcp-probe-results-%s-%s.txt" % (delay_ms, cc_alg) )
        setLogLevel( 'info' )
        main( duration_sec, delay_sec, delay_ms, cc_alg, results_path )
        cleanup()
