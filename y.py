from machine import UART, Pin
#import ubinascii
import math
import time

uart0 = UART(0, baudrate=19200, tx=Pin(0), rx=Pin(1))

RelayK1 = Pin(3, Pin.OUT)            # Power to FLARM-display (both 3 and 12 volts)
RelayK2 = Pin(5, Pin.OUT)            # Latch to keep the FLARM on
WatchDogOUT = Pin(12, Pin.OUT)       # Ouput to the hardware watchdog
WatchDogIN = Pin(13, Pin.OUT)        # Input of watchdog signal, only used when the signal watchdog out shall be inverted
TestPin = Pin(6, Pin.IN, Pin.PULL_UP)


char = b''
xhar_ascii = ""
NMEAin = ""
NMEAline = ""
NMEAleftover = ""

x = ""
x_old = ""
sentence = ""
WD = False
AntiLoop = 0
AntiLoopTimeout = 12000


def subCheckSum(sentence):
    strCalculated = ""
    #print("A: " + sentence)
    # Saving the incoming checksum for reference
    strOriginal = sentence[-4:]
    #print("A: " + strOriginal)
    # Remove \n\r
    strOriginal = strOriginal[:-2]
    #print("B: " + strOriginal)
    # Remove checksum
    sentence = sentence[:-5]
    #print("C: " + sentence)
    # Remove $
    if sentence[:1] == "$":
        sentence = sentence[1:]
    #print("D: " + sentence)
    chksum = ""
    calc_cksum = 0
    #print("Scrutinized string: " + sentence)
    # Calculating checksum
    for s in sentence:
        #print ("s: " + str(s))
        calc_cksum ^= ord(s)     #calc_cksum ^= ord(s)
        strCalculated = hex(calc_cksum).upper()
    # Removing the  "0X" from the hex value
    try:
        strCalculated = strCalculated[2:]
        # If the checksum is a single digit, adding a zero in front of the digit
        if len(strCalculated) == 1:
            strCalculated = "0" + strCalculated
        #print("chksum: " + strCalculated + " " + " sentence: " + sentence)
    except:
        whatever = True
    # Returning the provided checksum (from the original message) and the calculated 
    return strCalculated

def subWatchDog(wd_in):
    # Altering the watchdog output
    if not TestPin():
        exit()
    else:
        if wd_in:
            wd_out = False
            WatchDogOUT.value(0)
        else:
            wd_out = True
            WatchDogOUT.value(1)
        return wd_out

class clPFLAAMessage(object):

    def __init__(self, sentance):

        # See http://www.ediatec.ch/pdf/FLARM%20Data%20Port%20Specification%20v7.00.pdf for more information

        # Example $PFLAA,0,-1234,1234,220,2,DD8F12,180,,30,-1.4,,1*60

		#PFLAA,<AlarmLevel>,<RelativeNorth>,<RelativeEast>,<RelativeVertical>,<IDType>,<ID>,<Track>,<TurnRate>,<GroundSpeed>,<ClimbRate>,<AcftType>

		# 0			AlarmLevel, 0 = no alarm, 1 = alarm: 13-18 seconds to impact, 2 = alarm: 9-12 seconds to impact, 3 = alarm: 0-8 seconds to impact
		# -1234		RelativeNorth, relative position in meters true north from own position.
		# 12345		RelativeEast, relative position in meters true east from own position. 
		# 220		RelativeVertical, relative vertical separation in meters above own position
		# 2			IDType, 1 = official ICAO 24-bit aircraft address, 2 = stable FLARM ID (chosen by FLARM), 3 = anonymous ID, used if stealth mode is activated either on the target or own aircraft
		# DD8F12	ID
		# 180		Track, the target’s true ground track in degrees. T
		# Null		TurnRate, currently this field is empty
		# 30		GroundSpeed, the target’s ground speed in m/s, 0 (zero) if not moving
		# -1		ClimbRate, The target’s climb rate in m/s
		# 4			AcftType:
					# 0 = unknown
					# 1 = glider / motor glider
					# 2 = tow / tug plane
					# 3 = helicopter / rotorcraft
					# 4 = skydiver
					# 5 = drop plane for skydivers
					# 6 = hang glider (hard)
					# 7 = paraglider (soft)
					# 8 = aircraft with reciprocating engine(s)
					# 9 = aircraft with jet/turboprop engine(s)
					# A = unknown
					# B = balloon
					# C = airship
					# D = unmanned aerial vehicle (UAV)
					# E = unknown
					# F = static object
		# *60		CRC

        (self.PFLAA,
		 self.AlarmLevel,
		 self.RelativeNorth,
		 self.RelativeEast,
		 self.RelativeVertical,
		 self.IDType,
		 self.ID,
		 self.Track,
		 self.TurnRate,
		 self.GroundSpeed,
		 self.ClimbRate,
		 self.AcftType,
         self.CRC
        ) = sentance.replace("\r\n","").replace(":",",").split(",")


class clPFLAUMessage(object):

    def __init__(self, sentance):

        # See http://www.ediatec.ch/pdf/FLARM%20Data%20Port%20Specification%20v7.00.pdf for more information

        # Example $PFLAU,2,1,2,1,1,-45,2,50,75,1A304C*60
        #          PFLAU,0,1,1,1,0,   ,0,  ,*63


		# PFLAU,<RX>,<TX>,<GPS>,<Power>,<AlarmLevel>,<RelativeBearing>,<AlarmType>,<RelativeVertical>,<RelativeDistance>,<ID>
        
        # 2			Number of devices with unique IDs currently received regardless of the horizontal or vertical separation.

        # 1			Transmission status: 1 for OK and 0 for no transmission.
        # 2			GPS status: 0 = no GPS reception, 1 = 3d-fix on ground (i.e. not airborne), 2 = 3d-fix when airborne
        # 1			Power status: 1 for OK and 0 for under- or overvoltage
        # 1			AlarmLevel, 0 = no alarm, 1 = alarm: 13-18 seconds to impact, 2 = alarm: 9-12 seconds to impact, 3 = alarm: 0-8 seconds to impact
        # -45		Relative bearing in degrees from true ground track to the intruder’s position
        # 2			Type of alarm as assessed by FLARM, 0 = no aircraft within range or no-alarm traffic, information, 2 = aircraft alarm, 3 = obstacle/Alert Zone alarm
        # 50		Relative vertical separation in meters above own position
        # 75		Relative horizontal distance in meters to the target or obstacle
        # 1A304C	ID of intruder
        # *60		CRC

        (self.PFLAU,
		 self.RX,
		 self.TX,
		 self.GPS,
		 self.Power,
		 self.AlarmLevel,
		 self.RelBearing,
		 self.AlarmType,
		 self.RelVertical,
		 #self.RelDistance,
		 #self.ID,
         self.CRC
        ) = sentance.replace("\r\n","").replace(":",",").split(",")

class clGPRMCMessage(object):

    def __init__(self, sentance):

        # See https://aprs.gids.nl/nmea/#rmc for more information

        # Example $GPRMC,150242.00,A,5911.22585,N,01739.40910,E,0.201,294.43,280821,,,A*60

        # 150242.00     Time Stamp
        # A             Validity - A-ok, V-invalid
        # 5911.22585    Current Latitude
        # N             North/South
        # 01739.40910   Current Longitude
        # W             East/West
        # 0.201         Speed in knots
        # 294.43        True course
        # 280821        Date Stamp
        #               Variation
        #               Var dir
        # A             Mode ind
        # *60           checksum

        (self.GPGGA,
         self.Time,
         self.Valid,
         self.Lat,
         self.N_or_S,
         self.Long,
         self.E_or_W,
         self.Speed,
         self.TCourse,
         self.Date,
         self.VarDir,
         self.MagVar,
         self.CRC
        ) = sentance.replace("\r\n","").replace(":",",").split(",")


class clGPGGAMessage(object):

    def __init__(self, sentance):

        # See https://aprs.gids.nl/nmea/#gga for more information

        # Example $GPGGA,091358.00,5911.23442,N,01739.42496,E,1,06,1.40,30.3,M,24.1,M,,*60
              
        # 091358.00		= UTC of Position
        # 5911.23442	= Latitude
        # N				= N or S
        # 01739.42496	= Longitude
        # E 			= E or W
        # 1				= GPS quality indicator (0=invalid; 1=GPS fix; 2=Diff. GPS fix)
        # 06			= Number of satellites in use [not those in view]
        # 1.40			= Horizontal dilution of position
        # 30.3			= Antenna altitude above/below mean sea level (geoid)
        # M				= Meters  (Antenna height unit)
        # 24.1			= Geoidal separation (Diff. between WGS-84 earth ellipsoid and mean sea level.  -=geoid is below WGS-84 ellipsoid)
        # M				= Meters  (Units of geoidal separation)
        # = Diff. reference station ID#
        #= Checksum

        (self.GPGGA,
         self.Time,
         self.Lat,
         self.N_or_S,
         self.Long,
         self.E_or_W,
         self.GPS,
         self.NoOfSat,
         self.Dilution,
         self.AntAlt,
         self.UnitsAnt,
         self.GeoDiff,
         self.UnitsGeo,
         self.DiffRef,
         self.CRC
        ) = sentance.replace("\r\n","").replace(":",",").split(",")

while True:
    #time.sleep(0.1)
    WD = subWatchDog(WD)

    now = time.time()
    if now > (AntiLoop + AntiLoopTimeout):
        RelayK1.value(0)
        RelayK2.value(0)

    data_old = ""
    NMEAin = ""

    time.sleep(0.5)
    while uart0.any() > 0:
        #rxData += uart0.read(1)
        char = uart0.readline()
        #print(char)
        char_ascii = (char.decode("utf-8","ignore"))
        #print("A")
        #print(data)
        NMEAin += char_ascii
        #print(NMEAin)

        #sentence = sentence + data
    
    i = 1
    j = 1
    

    if len(NMEAin) > 1:	    # Something has been recieved on the UART, lets check it out
        
        # Adding the leftovers from the last evaluation
        NMEAin = NMEAleftover + NMEAin
        #print ("NMEAin: " + NMEAin)

        # Setting the scene    
        KeepLooking = True
        FoundDollar = -1
        FoundNewLine = -1
        i = 1
        j = 1
        
        # Objective: find any NMEA sentences 
        while KeepLooking:		# Lets go looking
            
            for x in NMEAin:	# Incrementing through each character in the information from the UART
            
                #print ("X")
                if x == "$":	# We found a $, the first char in a NMEA-string
                    
                    FoundDollar = i		# Saving the position of the $ within the string
                    #print ("Y" + str(i))
                    
                if x == "\n" and x_old == "\r":		# We found an EOL (end of line), the last characters in a NMEA sentence. Note two chars in a row

                    FoundNewLine = j	# Saving the position of the EOL within the string
                    #print ("Z" + str(j))
                    
                if  FoundNewLine > 0 and FoundDollar > 0 and FoundDollar < FoundNewLine:	# We have found the beginning and the end of a NMEA sentence within the information from the UART, lets do something with it. Note: the end shall be after the beginning.

                    #print ("W")
                    #print ("NMEAin: " + NMEAin)
                    
                    NMEAline = NMEAin[FoundDollar-1:FoundNewLine]	# Extracting the NMEA sentence from the information from the UART
                    
                    #print ("i : " + str(FoundDollar) + " j : " + str(FoundNewLine) + " NMEA: " + NMEAline)	# Printing the start and end point for trouble shooting purpose

                    print (NMEAline)
                    
                    # Lets do somethig with the information
                    if NMEAline.find("GPRMC") == 1:		# The sentence is GPRMC: NMEA minimum recommended GPS navigation data


                        NMMEAsplit = clGPRMCMessage(NMEAline)		# Splitting the sentence into its variables

                        CheckSumCalculated = subCheckSum(NMEAline)

                        #print (NMMEAsplit.CRC[2:] + " " + CheckSumCalculated)

                        if (NMMEAsplit.CRC[2:] != CheckSumCalculated):
                            print ("Fail: " + NMMEAsplit.CRC[2:] + " " + CheckSumCalculated + " " + NMEAline)


                    if NMEAline.find("GPGGA") == 1:		# The sentence is GPRMC: NMEA minimum recommended GPS navigation data


                        NMMEAsplit = clGPGGAMessage(NMEAline)		# Splitting the sentence into its variables

                        CheckSumCalculated = subCheckSum(NMEAline)

                        #print (NMMEAsplit.CRC[1:] + " " + CheckSumCalculated)

                        if (NMMEAsplit.CRC[1:] != CheckSumCalculated):
                            print ("Fail: " + NMMEAsplit.CRC[2:] + " " + CheckSumCalculated + " " + NMEAline)
                            
                        #print ("GPS: " + NMMEAsplit.GPS)


                    if NMEAline.find("PFLAA") == 1:		# The sentence is PFLAA: Data on other proximate aircraft

                        NMMEAsplit = clPFLAAMessage(NMEAline)		# Splitting the sentence into its variables
                    
                        CheckSumCalculated = subCheckSum(NMEAline)
                    
                        #print (NMMEAsplit.CRC[2:] + " " + CheckSumCalculated)
                        
                        if (NMMEAsplit.CRC[2:] != CheckSumCalculated):
                            print ("Fail: " + NMMEAsplit.CRC[2:] + " " + CheckSumCalculated + " " + NMEAline)


                    if NMEAline.find("PFLAU") == 1:		# The sentence is PFLAU: Operating status, priority intruder and obstacle warnings

                        NMMEAsplit = clPFLAUMessage(NMEAline)		# Splitting the sentence into its variables
                    
                        CheckSumCalculated = subCheckSum(NMEAline)

                        #print (NMMEAsplit.CRC[1:] + " " + CheckSumCalculated)

                        if (NMMEAsplit.CRC[1:] != CheckSumCalculated):
                            print ("Fail: " + NMMEAsplit.CRC[2:] + " " + CheckSumCalculated + " " + NMEAline)


                # Increment counters and saxe the previous value
                i = i + 1
                j = j + 1
                x_old = x


            KeepLooking = False		# The entrie string has been scrutinized, no more complete NMEA sentences are left. Lets stop looking and get new UART information

            NMEAin = NMEAin[FoundNewLine:]	# Extracting the NMEA-string from the UART information

            NMEAleftover = NMEAin	# Saving the leftovers from the scrutinized string
            #print ("NMEAleftover: " + NMEAleftover)
            #print ("P")    
                
                
                    

