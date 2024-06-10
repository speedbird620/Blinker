# Program bespoke to the FLARM blinker
# Raspberry PI Pico
#
# avionics@skyracer.net
# 0.1 - First version
# 0.2 - Added automatic baudcheck
#
# https://github.com/speedbird620/Blinker
#
#-----------------------------------------------------------


from machine import UART, Pin
#import ubinascii
import math
import time

uart0 = UART(0, baudrate=19200, tx=Pin(0), rx=Pin(1))

RelayK1 = Pin(3, Pin.OUT)            # Power to FLARM-display (both 3 and 12 volts)
RelayK2 = Pin(5, Pin.OUT)            # Latch to keep the FLARM on
WatchDogOUT = Pin(12, Pin.OUT)       # Ouput to the hardware watchdog
WatchDogIN = Pin(13, Pin.OUT)        # Input of watchdog signal, only used when the signal watchdog out shall be inverted

GP6 = Pin(6, Pin.IN, Pin.PULL_UP)    # Pin for identifying mode
GP7 = Pin(7, Pin.IN, Pin.PULL_UP)    # Pin for identifying mode
GP8 = Pin(8, Pin.IN, Pin.PULL_UP)    # Pin for identifying mode
GP9 = Pin(9, Pin.IN, Pin.PULL_UP)    # Pin for identifying mode
GP10 = Pin(10, Pin.IN, Pin.PULL_UP)  # Pin for identifying mode

char = b''
xhar_ascii = ""
NMEAin = ""
NMEAline = ""
NMEAleftover = ""
TimeStampOn = 0
TimeOut = 4
TestMode = -1
TestMode_Old = 0
x = ""
x_old = ""
sentence = ""
WD = False
FindComSpeed = True
c = 0
ComSpeed = 0
TryComSpeed = 0
TestComSpeed = [38400, 9600, 19200, 28800, 4800, 56000, 56000]


def subCheckMode():			# Check the mode
    if not GP6.value():     
        mode = 1			# Set relay if GPS-signal is valid
    elif not GP7.value():
        mode = 2			# Set relay if ...
    elif not GP8.value():
        mode = 3			# Set relay if ...
    elif not GP9.value():
        mode = 4			# Force relay on
    elif not GP10.value():
        mode = 5			# Force relay off
    else:
        mode = 0
    return mode

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
    if wd_in:
        wd_out = False
        WatchDogOUT.value(0)
    else:
        wd_out = True
        WatchDogOUT.value(1)
    return wd_out

def subVerifyCheckSum(calcCheckSum,extractedCheckSum):

    #print ("A :" + extractedCheckSum)
    extractedCheckSum = extractedCheckSum[len(extractedCheckSum)-2:]	# Lets shorten the checksum down to two chars
    #print ("B :" + extractedCheckSum)

    if (calcCheckSum != extractedCheckSum):		# Comparing the values
        return False
    else:
        return True
        
def setRelay(input):
    if input:
        if RelayK1.value() == 0:
            print ("Relay on")
        RelayK1.value(1)
        #RelayK2.value(1)
        return time.time()
    else:
        if RelayK1.value():
            print ("Relay off")
        RelayK1.value(0)
        #RelayK2.value(0)
        return 0

class clPFLAAMessage(object):

    def __init__(self, sentance):

        # See http://www.ediatec.ch/pdf/FLARM%20Data%20Port%20Specification%20v7.00.pdf for more information
        # $PFLAA,<AlarmLevel>,<RelativeNorth>,<RelativeEast>,<RelativeVertical>,<IDType>,<ID>    ,<Track>,<TurnRate>,<GroundSpeed>,<ClimbRate>,<AcftType>
        # $PFLAA,0           ,-19            ,6             ,-14               ,2       ,DDE602  ,159    ,          ,0            ,0.0        ,1*2C
        # $PFLAA,0           ,25             ,-43           ,-22               ,2       ,DDE602  ,190    ,          ,4            ,-0.3       ,1*38
         
        # $PFLAA,0, 25,-43,-22,2,DDE602,190,,4,-0.3,1*38
        # $PFLAA,0,-19,  6,-14,2,DDE602,159,,0, 0.0,1*2C
          
        # 0         AlarmLevel, 0 = no alarm, 1 = alarm: 13-18 seconds to impact, 2 = alarm: 9-12 seconds to impact, 3 = alarm: 0-8 seconds to impact
        # -1234     RelativeNorth, relative position in meters true north from own position.
        # 12345     RelativeEast, relative position in meters true east from own position. 
        # 220       RelativeVertical, relative vertical separation in meters above own position
        # 2         IDType, 1 = official ICAO 24-bit aircraft address, 2 = stable FLARM ID (chosen by FLARM), 3 = anonymous ID, used if stealth mode is activated either on the target or own aircraft
        # DD8F12    ID
        # 180       Track, the target’s true ground track in degrees. T
        # Null      TurnRate, currently this field is empty
        # 30        GroundSpeed, the target’s ground speed in m/s, 0 (zero) if not moving
        # -1        ClimbRate, The target’s climb rate in m/s
        # 4         AcftType:
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
        # *60       CRC

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
         #self.AcftType,
         self.CRC
        ) = sentance.replace("\r\n","").replace(":",",").split(",")


class clPFLAUMessage(object):

    def __init__(self, sentance):

        # See http://www.ediatec.ch/pdf/FLARM%20Data%20Port%20Specification%20v7.00.pdf for more information

        # $PFLAU,<RX>,<TX>,<GPS>,<Power>,<AlarmLevel>,<RelativeBearing>,<AlarmType>,<RelativeVertical>,<RelativeDistance>,<ID>
        # $PFLAU,2   ,1   ,2    ,1      ,1           ,-45              ,2          ,50                ,75                ,1A304C  *60
        # $PFLAU,1   ,1   ,1    ,1      ,0           ,                 ,0          ,                  ,                  ,        *4E
        # $PFLAU,0   ,1   ,1    ,1      ,0           ,                 ,0          ,                  ,                           *63


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
         self.RelDistance,
         #self.ID,
         self.CRC
        ) = sentance.replace("\r\n","").replace(":",",").split(",")


class clPFLAUMessage2(object):

    def __init__(self, sentance):

        # See http://www.ediatec.ch/pdf/FLARM%20Data%20Port%20Specification%20v7.00.pdf for more information

        # $PFLAU,<RX>,<TX>,<GPS>,<Power>,<AlarmLevel>,<RelativeBearing>,<AlarmType>,<RelativeVertical>,<RelativeDistance>,<ID>
        # $PFLAU,2   ,1   ,2    ,1      ,1           ,-45              ,2          ,50                ,75                ,1A304C  *60
        # $PFLAU,1   ,1   ,1    ,1      ,0           ,                 ,0          ,                  ,                  ,        *4E
        # $PFLAU,0   ,1   ,1    ,1      ,0           ,                 ,0          ,                  ,                           *63


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
        #         $GPRMC,073523.00,A,5911.23020,N,01739.41778,E,0.310,280.90,090624,,,A*68
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
        #         $GPGGA,073523.00,5911.23020,N,01739.41778,E,1,07,3.14,36.8,M,24.1,M,,*69
        #         $GPGGA,105457.00,5911.23170,N,01739.42539,E,1,07,1.38,23.9,M,24.1,M,,*62
        
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
    #time.sleep(0.2)
    
    TestMode = subCheckMode()
    if (TestMode != TestMode_Old):
        print ("Mode: " + str(TestMode))

    TestMode_Old = TestMode
    
    while TestMode == 4:
        setRelay(True)
        TimeStampOn = 1
        WD = subWatchDog(WD)
        TestMode = subCheckMode()
        

    while TestMode == 5:
        setRelay(False)
        TimeStampOn = 1
        WD = subWatchDog(WD)
        TestMode = subCheckMode()
   
    WD = subWatchDog(WD)

    if (TimeStampOn > 0):								# The relay shall time out after x seconds
        #print (str(time.time() - TimeStampOn))
        if (time.time() > (TimeStampOn + TimeOut)):		# The time is up
            TimeStampOn = setRelay(False)				# Switching off the relay

    if FindComSpeed:							# The com speed has not yet been determined
        if time.time() > TryComSpeed + 2:		# Time to test a new speed
            TryComSpeed = time.time()			# Time of the last try
            c = c + 1							# Incrementing the counter
            if c > 6: c = 1						# Resetting the counter
            print("Testing " + str(TestComSpeed[c]) + " baud")
            uart0 = UART(0, baudrate=TestComSpeed[c], tx=Pin(0), rx=Pin(1))		# Set a new baud rate to test
    
    

    # Resetting the variables
    data_old = ""
    NMEAin = ""

    time.sleep(0.1)
    while uart0.any() > 0:
        #rxData += uart0.read(1)
        char = uart0.readline()
        #print(char)
        try:
            char_ascii = (char.decode("utf-8","ignore"))
        except:
            char_ascii = ""
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

                    CheckSumCalculated = subCheckSum(NMEAline)
                    
                    # Lets do somethig with the information
                    if NMEAline.find("GPRMC") == 1:		# The sentence is GPRMC: NMEA minimum recommended GPS navigation data
                        
                        try:
                            NMMEAsplit = clGPRMCMessage(NMEAline)		# Splitting the sentence into its variables
                        except:
                            print ("Failed NMEAline: " +(NMEAline))

                        if not subVerifyCheckSum(CheckSumCalculated,NMMEAsplit.CRC):		# Scrutinizing the checksum
                            print ("CRC fail: " + NMMEAsplit.CRC + " " + CheckSumCalculated + " " + NMEAline)		# Bad checksum
                        else:		# Good checksum
                            #print (NMEAline)
                            #print (NMMEAsplit.Valid)
                            if NMMEAsplit.Valid == "A" and TestMode == 1:		# Testmode: det relay if GPS has a valid signal
                                TimeStampOn = setRelay(True)					# Activating the relay

                    if NMEAline.find("GPGGA") == 1:		# The sentence is GPRMC: NMEA minimum recommended GPS navigation data

                        try:
                            NMMEAsplit = clGPGGAMessage(NMEAline)		# Splitting the sentence into its variables
                        except:
                            print ("Failed NMEAline: " +(NMEAline))

                        if not subVerifyCheckSum(CheckSumCalculated,NMMEAsplit.CRC):		# Scrutinizing the checksum
                            print ("CRC fail: " + NMMEAsplit.CRC + " " + CheckSumCalculated + " " + NMEAline)		# Bad checksum

                    if NMEAline.find("PFLAA") == 1:		# The sentence is PFLAA: Data on other proximate aircraft

                        try:
                            NMMEAsplit = clPFLAAMessage(NMEAline)		# Splitting the sentence into its variables
                        except:
                            print ("Failed NMEAline: " +(NMEAline))

                        if subVerifyCheckSum(CheckSumCalculated,NMMEAsplit.CRC):	# Scrutinizing the checksum
                            if NMMEAsplit.AlarmLevel != 0:							# Alarm is active 
                                TimeStampOn = setRelay(True)						# Activating the relay
                        else:
                            print ("CRC fail: " + NMMEAsplit.CRC + " " + CheckSumCalculated + " " + NMEAline)		# Bad checksum

                    if NMEAline.find("PFLAU") == 1:		# The sentence is PFLAU: Operating status, priority intruder and obstacle warnings

                        try:
                            try:											# Mitigating a bug in the FLARM RedBox
                                NMMEAsplit = clPFLAUMessage(NMEAline)		# Splitting the sentence into its variables
                            except:
                                NMMEAsplit = clPFLAUMessage2(NMEAline)		# Splitting the sentence into its variables
                        except:
                            print ("Failed NMEAline: " +(NMEAline))

                        if subVerifyCheckSum(CheckSumCalculated,NMMEAsplit.CRC):	# Scrutinizing the checksum
                            if NMMEAsplit.AlarmLevel != 0:							# Alarm is active and testmode is zero
                                TimeStampOn = setRelay(True)						# Activating the relay
                        else:
                            print ("CRC fail: " + NMMEAsplit.CRC + " " + CheckSumCalculated + " " + NMEAline)		# Bad checksum

                    if subVerifyCheckSum(CheckSumCalculated,NMMEAsplit.CRC):	# Scrutinizing the checksum
                        if FindComSpeed:										# Valid NMEA-sentence is found, baud rate is correct
                            print("Disco, baud rate is found to be " + str(TestComSpeed[c]) + " baud")
                            FindComSpeed = False								# I still havent found what Im looking for ... not

 
                # Increment counters and saxe the previous value
                i = i + 1
                j = j + 1
                x_old = x


            KeepLooking = False		# The entrie string has been scrutinized, no more complete NMEA sentences are left. Lets stop looking and get new UART information

            NMEAin = NMEAin[FoundNewLine:]	# Extracting the NMEA-string from the UART information

            NMEAleftover = NMEAin	# Saving the leftovers from the scrutinized string
            #print ("Left: " + NMEAleftover)
            #print ("P")    
                
                    
