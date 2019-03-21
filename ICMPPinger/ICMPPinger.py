from socket import *
import collections
import os
import sys
import struct
import time
import select
import binascii  

ICMP_ECHO_REQUEST = 8

is_py2 = sys.version_info[0] < 3

class IPHeader( object ):
	@classmethod
	def from_datagram( cls, buffer ):
		# Read in the fixed portion of the IP header, which is the first 20 bytes. Field named based
		# on the IP header fields listed at https://en.wikipedia.org/wiki/IPv4.
		base_header_format = "!BBHHHBBHLL"
		base_header_size = struct.calcsize( base_header_format )
		(version_ihl,
		dscp_ecn,
		total_length,
		identification,
		flags_fragment_offset,
		time_to_live,
		protocol,
		header_checksum,
		source_address,
		destination_address) = struct.unpack( base_header_format, buffer[:base_header_size] )

		# The lower four bits of the first byte in the header say how many 32-bit words are in the
		# header in total, including the options portion of the header. The upper four bits are the
		# IP version field.
		version = (version_ihl & 0xf0) >> 4
		header_length = 4 * (version_ihl & 0x0f)

		# Next byte specifies Designated Services Code Point (DSCP; upper 6 bits) and Explicit
		# Congestion Notificatio (ECN; lower 2 bits).
		dscp = (dscp_ecn & 0xfc) >> 2
		ecn = dscp_ecn & 0x3

		# Seventh and eighth bytes contain flags (upper three bits) and the fragment offset (lower
		# 13 bits).
		flags = (flags_fragment_offset & 0xe000) >> 13
		fragment_offset = flags_fragment_offset & 0x1fff

		options_length = header_length - base_header_size
		options = buffer[base_header_size:(base_header_size + options_length)] if options_length > 0 else []

		return cls( version, header_length, dscp, ecn, total_length, identification, flags,
			fragment_offset, time_to_live, protocol, header_checksum, source_address,
			destination_address, options )

	def __init__( self, version, length, dscp, ecn, packet_size, identification, flags,
		fragment_offset, time_to_live, protocol, checksum, source_address, destination_address,
		options ):
		self.version = version
		self.length = length
		self.dscp = dscp
		self.ecn = ecn
		self.packet_size = packet_size
		self.identification = identification
		self.flags = flags
		self.fragment_offset = fragment_offset
		self.time_to_live = time_to_live
		self.protocol = protocol
		self.checksum = checksum
		self.source_address = source_address
		self.destination_address = destination_address
		self.options = options

class ICMPMessage( object ):
	@staticmethod
	def from_bytes( buffer ):
		# Read in the header, which is composed of three fixed fields followed by a 32-bit field of
		# header data that varies with ICMP message type.
		header_format = "!bbHL"
		header_size = struct.calcsize( header_format )
		(message_type,
		code,
		checksum,
		header_data) = struct.unpack( header_format, buffer[:header_size] )
		payload = buffer[header_size:]

		# Swizzle some bytes.
		checksum = ntohs( checksum )

		if message_type == 0:
			if code == 0:
				identifier = ntohs( (header_data & 0xffff0000) >> 16 )
				sequence_number = ntohs( header_data & 0xffff )
				return EchoResponse( message_type, code, checksum, identifier, sequence_number, payload )

	def __init__( self, message_type, code, checksum, payload ):
		super().__init__()
		self.message_type = message_type
		self.code = code
		self.checksum = checksum
		self.payload = payload

class EchoResponse( ICMPMessage ):
	def __init__( self, message_type, code, checksum, identifier, sequence_number, payload ):
		super().__init__( message_type, code, checksum, payload )
		self.identifier = identifier
		self.sequence_number = sequence_number

def safe_bytes( buffer ):
	return str( buffer ) if is_py2 else buffer

def safe_ord( value ):
	return ord( value ) if is_py2 else value

def checksum(string): 
	csum = 0
	countTo = (len(string) // 2) * 2
	count = 0
	while count < countTo:
		thisVal = safe_ord(string[count+1]) * 256 + safe_ord(string[count]) 
		csum = csum + thisVal 
		csum = csum & 0xffffffff  
		count = count + 2
	
	if countTo < len(string):
		csum = csum + safe_ord(string[len(string) - 1])
		csum = csum & 0xffffffff 
	
	csum = (csum >> 16) + (csum & 0xffff)
	csum = csum + (csum >> 16)
	answer = ~csum 
	answer = answer & 0xffff 
	answer = answer >> 8 | (answer << 8 & 0xff00)
	return answer
	
def receiveOnePing(mySocket, ID, timeout, destAddr):
	timeLeft = timeout
	
	while 1: 
		startedSelect = time.time()
		whatReady = select.select([mySocket], [], [], timeLeft)
		howLongInSelect = (time.time() - startedSelect)
		if whatReady[0] == []: # Timeout
			return "Request timed out."
	
		timeReceived = time.time() 
		recPacket, addr = mySocket.recvfrom(1024)
	       
	       #Fill in start
        
        	#Fetch the ICMP header from the IP packet
		ip_header = IPHeader.from_datagram( recPacket )
		print( "Header length: %s" % ip_header.length )
		print( "Packet size: %s" % ip_header.packet_size )
		print( "Version: %s" % ip_header.version )

		icmp_message_length = ip_header.packet_size - ip_header.length
		icmp_message = ICMPMessage.from_bytes( recPacket[ip_header.length:(ip_header.length + icmp_message_length)] )

		if isinstance( icmp_message, EchoResponse ):
			print( "Expected identifier: %s" % ID )
			print( "ICMP checksum: %x" % icmp_message.checksum )
			print( "ICMP identifier: %s" % icmp_message.identifier )
			print( "ICMP sequence number: %s" % icmp_message.sequence_number )

		# base_icmp_header_format = "!bbH"
		# base_icmp_header_size = struct.calcsize( base_icmp_header_format )
		# (icmp_type, icmp_code, icmp_checksum) = struct.unpack_from( base_icmp_header_format,
		# 	recPacket[internet_header_length:(internet_header_length + base_icmp_header_size)] )

		# print( f"Type: {icmp_type}  Code: {icmp_code}   Checksum: {icmp_checksum}" )

		# print( f"Byte 0: {version_ihl}" )
		# print( f"IHL: {internet_header_length}" )
        
       	#Fill in end
		timeLeft = timeLeft - howLongInSelect
		if timeLeft <= 0:
			return "Request timed out."
	
def sendOnePing(mySocket, destAddr, ID):
	# Header is type (8), code (8), checksum (16), id (16), sequence (16)
	
	myChecksum = 0
	# Make a dummy header with a 0 checksum
	# struct -- Interpret strings as packed binary data
	header = struct.pack("bbHHh", ICMP_ECHO_REQUEST, 0, myChecksum, ID, 1)
	data = struct.pack("d", time.time())
	# Calculate the checksum on the data and the dummy header.
	myChecksum = checksum(safe_bytes(header + data))
	
	# Get the right checksum, and put in the header
	if sys.platform == 'darwin':
		# Convert 16-bit integers from host to network  byte order
		myChecksum = htons(myChecksum) & 0xffff		
	else:
		myChecksum = htons(myChecksum)
		
	header = struct.pack("bbHHh", ICMP_ECHO_REQUEST, 0, myChecksum, ID, 1)
	packet = header + data
	
	mySocket.sendto(packet, (destAddr, 1)) # AF_INET address must be tuple, not str
	# Both LISTS and TUPLES consist of a number of objects
	# which can be referenced by their position number within the object.
	
def doOnePing(destAddr, timeout): 
	icmp = getprotobyname("icmp")
	# SOCK_RAW is a powerful socket type. For more details:   
#    http://sock-raw.org/papers/sock_raw

	mySocket = socket(AF_INET, SOCK_RAW, icmp)
	
	myID = os.getpid() & 0xFFFF  # Return the current process i
	sendOnePing(mySocket, destAddr, myID)
	delay = receiveOnePing(mySocket, myID, timeout, destAddr)
	
	mySocket.close()
	return delay
	
def ping(host, timeout=1):
	# timeout=1 means: If one second goes by without a reply from the server,
	# the client assumes that either the client's ping or the server's pong is lost
	dest = gethostbyname(host)
	print("Pinging " + dest + " using Python:")
	print("")
	# Send ping requests to a server separated by approximately one second
	while 1 :
		delay = doOnePing(dest, timeout)
		print(delay)
		time.sleep(1)# one second
	return delay
	
ping("127.0.0.1")
