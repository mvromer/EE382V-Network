from itertools import izip
import time

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.link import TCLink
from mininet.util import dumpNodeConnections, dumpNetConnections
from mininet.log import setLogLevel, info

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
        delay_str = "%dms" % delay_ms
        queue_size = delay_ms * bb_bw
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
        self.addLink( s1, ar1, bw=host_bw )
        self.addLink( s2, ar1, bw=host_bw )
        self.addLink( ar1, bb1, bw=bb_bw )
        self.addLink( r1, ar2, bw=host_bw )
        self.addLink( r2, ar2, bw=host_bw )
        self.addLink( ar2, bb2, bw=bb_bw )

def main( delay_ms, cc_alg ):
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
            queue_size = int(0.2 * 252 * delay_ms)
            ar_iface.config( bw=252, max_queue_size=queue_size )

    info( "Dumping host connections\n" )
    dumpNodeConnections( net.hosts )

    info( "Dumping net connections\n" )
    dumpNetConnections( net )

    # Get rid of initial delay in network.
    net.pingAll()

    # Set up tcp_probe on the senders.
    #info( '%s\n' % net["s1"].cmd( 'modprobe tcp_probe port=5001' ) )
    #info( '%s\n' % net["s2"].cmd( 'modprobe tcp_probe port=5001' ) )

    # Run one iperf stream between r1 and s1 and another between r2 and s2.
    duration_sec = 10
    delay_sec = 2
    net["r1"].sendCmd( 'iperf -s -p 5001' )
    net["r2"].sendCmd( 'iperf -s -p 5001' )

    #net["s1"].cmd( 'cat /proc/net/tcpprobe > ~/s1-probe.out &' )
    net["s1"].sendCmd( 'iperf -c %s -p 5001 -i 1 -t %s -Z %s -w 16m' %
        (net["r1"].IP(), duration_sec, cc_alg) )

    # Delay the second sender by a certain amount and then start it.
    time.sleep( delay_sec )
    #net["s2"].cmd( 'cat /proc/net/tcpprobe > ~/s2-probe.out &' )
    net["s2"].sendCmd( 'iperf -c %s -p 5001 -i 1 -t %s -Z %s -w 16m' %
        (net["r2"].IP(), duration_sec - delay_sec, cc_alg) )

    # Wait for all iperfs to close. On server side, we need to send sentinel to output for
    # waitOutput to return.
    net["s1"].waitOutput( verbose=True )
    net["s2"].waitOutput( verbose=True )
    #net["s1"].cmd( 'kill %cat' )
    #net["s2"].cmd( 'kill %cat' )

    net["r1"].sendInt()
    net["r1"].waitOutput( verbose=True )

    net["r2"].sendInt()
    net["r2"].waitOutput( verbose=True )

    net.stop()

if __name__ == "__main__":
    delay_ms = 21
    cc_alg = "reno"
    setLogLevel( 'info' )
    main( delay_ms, cc_alg )
