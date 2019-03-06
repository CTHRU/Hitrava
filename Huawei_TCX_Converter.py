# Huawei_TCX_Converter

# Imports
import xml.etree.cElementTree as ET
import math, operator, sys, tempfile, urllib.request
from datetime import datetime as dt
try:
    import xmlschema
    xmlschema_found = True
except ModuleNotFoundError:
    xmlschema_found = False

def parse_arguments():
    # parse command line arguments
    print('\n')
    filter = False
    validate = False
    input_file = ''
    for argument in sys.argv[1:]:
        if argument == '-f':
            filter = True
        elif argument == '-v':
            validate = True
        elif argument[0] == '-':
            print('Error: invalid input argument \''+argument+'\'')
            exit()
        elif argument[:2] == '.\\':
            if input_file:
                print('Error: unexpected argument \''+argument+'\'')
                exit()
            else:
                input_file = argument[2:]
        else:
            if input_file:
                print('Error: unexpected argument \''+argument+'\'')
                exit()
            else:
                input_file = argument

    return input_file, {'filter': filter, 'validate': validate}

def read_file(input_file):
    print('---- Input File ----')
    print('reading: ', end='')
    try:
        gps_data = []
        hr_data = []
        first_gps = True
        first_hr = True
        with open(input_file) as f:
            #    lbs   |   p-m   |   b-p-m   |   h-r   |   rs
            # --------------------------------------------------
            # location |  pace   |     ?     |  pulse  | speed
            for line in f:
                # Loop over file line by line
                if line[0:6] == 'tp=lbs':
                    # Get location data
                    holding_list = []
                    for x in [6,3,4,0,0]: #time, lat, long, [dist], [hr]
                        if x == 0:
                            holding_list.append('') # Fill in blanks with blank
                        else:
                            holding_list.append(float(line.split('=')[x].split(';')[0]))
                    if first_gps:
                            # normalise time order of magnitude to unix timestamp
                            oom = int(math.log10(holding_list[0]))
                            if oom > 9:
                                divisor = 10**(oom-9)
                            elif oom < 9:
                                divisor = 0.1**(9-oom)
                            else:
                                divisor = 1
                    holding_list[0] = holding_list[0]/divisor
                    gps_data.append(holding_list)

                if line[0:6] == 'tp=h-r':
                    # Get heart-rate data
                    holding_list = []
                    for x in [2,0,0,0,3]: #time, [lat], [long], [dist], hr
                        if x == 0:
                            holding_list.append('') # Fill in blanks with blank
                        elif x == 2:
                            holding_list.append(int(float(line.split('=')[x].split(';')[0])))
                        else:
                            holding_list.append(int(line.split('=')[x].split(';')[0]))
                    if first_hr:
                            # normalise time order of magnitude to unix timestamp
                            oom = int(math.log10(holding_list[0]))
                            if oom > 9:
                                divisor = 10**(oom-9)
                            elif oom < 9:
                                divisor = 0.1**(9-oom)
                            else:
                                divisor = 1
                    holding_list[0] = holding_list[0]/divisor
                    hr_data.append(holding_list)
    except:
        print('FAILED')
        exit()

    print('OKAY')
    return gps_data, hr_data

def filter_data(data):
    print('filtering: ', end='')
    original_data = data
    try:
        # filters data before processing to remove aberrations
        for line in data:
            # filter lines where GPS was lost (defaults to (90, -80))
            #time, lat, long, [dist], [hr]
            if line[1] == 90.0 and line[2] == -80.0:
                data.remove(line)
        print('OKAY')

    except:
        print('FAILED')
        return original_data

    return data

def vincenty(point1, point2):
    # WGS 84
    a = 6378137
    f = 1 / 298.257223563
    b = 6356752.314245
    MAX_ITERATIONS = 200
    CONVERGENCE_THRESHOLD = 1e-12
    if point1[0] == point2[0] and point1[1] == point2[1]:
        return 0.0
    U1 = math.atan((1 - f) * math.tan(math.radians(point1[0])))
    U2 = math.atan((1 - f) * math.tan(math.radians(point2[0])))
    L = math.radians(point2[1] - point1[1])
    Lambda = L
    sinU1 = math.sin(U1)
    cosU1 = math.cos(U1)
    sinU2 = math.sin(U2)
    cosU2 = math.cos(U2)
    for iteration in range(MAX_ITERATIONS):
        sinLambda = math.sin(Lambda)
        cosLambda = math.cos(Lambda)
        sinSigma = math.sqrt((cosU2 * sinLambda) ** 2 +
                             (cosU1 * sinU2 - sinU1 * cosU2 * cosLambda) ** 2)
        if sinSigma == 0:
            return 0.0
        cosSigma = sinU1 * sinU2 + cosU1 * cosU2 * cosLambda
        sigma = math.atan2(sinSigma, cosSigma)
        sinAlpha = cosU1 * cosU2 * sinLambda / sinSigma
        cosSqAlpha = 1 - sinAlpha ** 2
        try:
            cos2SigmaM = cosSigma - 2 * sinU1 * sinU2 / cosSqAlpha
        except ZeroDivisionError:
            cos2SigmaM = 0
        C = f / 16 * cosSqAlpha * (4 + f * (4 - 3 * cosSqAlpha))
        LambdaPrev = Lambda
        Lambda = L + (1 - C) * f * sinAlpha * (sigma + C * sinSigma *
                                               (cos2SigmaM + C * cosSigma *
                                                (-1 + 2 * cos2SigmaM ** 2)))
        if abs(Lambda - LambdaPrev) < CONVERGENCE_THRESHOLD:
            break
    else:
        print('Error: unable to calculate distance between GPS points')
        return None  # TODO: Improve handling of convergence failure
    uSq = cosSqAlpha * (a ** 2 - b ** 2) / (b ** 2)
    A = 1 + uSq / 16384 * (4096 + uSq * (-768 + uSq * (320 - 175 * uSq)))
    B = uSq / 1024 * (256 + uSq * (-128 + uSq * (74 - 47 * uSq)))
    deltaSigma = B * sinSigma * (cos2SigmaM + B / 4 * (cosSigma *
                 (-1 + 2 * cos2SigmaM ** 2) - B / 6 * cos2SigmaM *
                 (-3 + 4 * sinSigma ** 2) * (-3 + 4 * cos2SigmaM ** 2)))
    s = b * A * (sigma - deltaSigma)

    return round(s, 6)

def process_gps(data):
    print('processing gps: ', end='')
    try:
        # Loop through data line by line
        for n, entry in enumerate(data):
            # Calculate distances between points based on vincenty distances
            # TODO: Improve point-to-point distance calculation
            if n == 0:
                #time, lat, long, [dist], [hr]
                entry[3] = 0
            else:
                entry[3] = (vincenty((float(entry[1]),float(entry[2])),
                    (float(data[n-1][1]),float(data[n-1][2])))+data[n-1][3])

    except:
        print('FAILED')
        exit()

    print('OKAY')

    return data

def merge_data(gps_data, hr_data):
    print('processing heart-rate: ', end='')
    # Sort data array chronologically
    try:
        data = gps_data+hr_data #time, lat, long, dist, hr
        gettime = operator.itemgetter(0)
        data = sorted(data, key=gettime)

        # Merge duplicated timestamps
        for n, entry in enumerate(data):
            if n == 0:
                pass
            else:
                if entry[0] == data[n-1][0]: #if timestamp is same as previous entry
                    if entry[4]: #and there is heart-rate data
                        data[n-1][4] = entry[4] #copy heart-rate to previous entry
                        data.remove(entry) #and delete this one
                    else: #but if there is no heart rate data here
                        data[n-1][1] = entry[1] #copy lat to previous
                        data[n-1][2] = entry[2] #long to previous
                        data[n-1][3] = entry[3] #dist to previous
                        data.remove(entry) #and delete this one
    except:
        print('FAILED')
        exit()

    print('OKAY')
    return data

def file_details(data):
    # Get stats from data
    start_time = data[0][0]
    duration = data[-1][0]-data[0][0]
    if data[-1][3]: distance = data[-1][3] #distance is zero if no gps data
    else: distance = 0
    stats = {'start_time': start_time, 'duration': duration, 'distance': distance}

    print('\n---- Details ----')
    print('start: '+str(dt.utcfromtimestamp(stats['start_time'])))
    print('duration: '+str(dt.utcfromtimestamp(stats['duration']).strftime('%H:%M:%S')))
    print('distance: '+str(int(stats['distance'])), end='m\n')

    # Format stats for saving
    stats['start_time'] = dt.utcfromtimestamp(stats['start_time']).isoformat()+'.000Z'
    stats['duration'] = str(stats['duration'])
    stats['distance'] = str(int(stats['distance']))

    return stats


def generate_xml(data, stats):
    print('\n---- XML file ----')
    print('generating: ', end='')

    try:
        # TrainingCenterDatabase
        TrainingCenterDatabase = ET.Element('TrainingCenterDatabase')
        TrainingCenterDatabase.set('xsi:schemaLocation','http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2 http://www.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd')
        TrainingCenterDatabase.set('xmlns', 'http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2')
        TrainingCenterDatabase.set('xmlns:xsd', 'http://www.w3.org/2001/XMLSchema')
        TrainingCenterDatabase.set('xmlns:xsi', 'http://www.w3.org/2001/XMLSchema-instance')
        #TrainingCenterDatabase.set('xmlns:tc2', 'http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2')
        ## Activities
        Activities = ET.SubElement(TrainingCenterDatabase,'Activities')

        ### Activity
        Activity = ET.SubElement(Activities,'Activity')
        Activity.set('Sport','Running') # TODO: Make an option to change sports?
        Id = ET.SubElement(Activity,'Id')
        Id.text = stats['start_time'] # The StartTime timestamp

        #### Lap
        # TODO: Work out how to split exercises up into laps (by distance?)
        Lap = ET.SubElement(Activity,'Lap')
        Lap.set('StartTime',stats['start_time'])
        TotalTimeSeconds = ET.SubElement(Lap,'TotalTimeSeconds')
        TotalTimeSeconds.text = str(stats['duration'])
        DistanceMeters = ET.SubElement(Lap,'DistanceMeters')
        DistanceMeters.text = stats['distance']
        Calories = ET.SubElement(Lap,'Calories')
        Calories.text = '0' # TODO: Can we nullify or get rid of this?
                            # Or is this present in data from some devices?
        Intensity = ET.SubElement(Lap,'Intensity')
        Intensity.text = 'Active' # TODO: Can we nullify or get rid of this?
        TriggerMethod = ET.SubElement(Lap,'TriggerMethod')
        TriggerMethod.text = 'Manual' # TODO: How are Laps (or Tracks?) split?
        Track = ET.SubElement(Lap,'Track')

        ##### Track
        distance_holder = 0
        for line in data:
            # format data for saving
            line[0] = dt.utcfromtimestamp(line[0]).isoformat()+'.000Z' #time
            line[1] = str(line[1]) #lat
            line[2] = str(line[2]) #long
            line[3] = str(line[3]) #distance
            line[4] = str(line[4]) #heart-rate

            Trackpoint = ET.SubElement(Track,'Trackpoint')
            Time = ET.SubElement(Trackpoint,'Time')
            Time.text = str(line[0])
            if line[1]:
                Position = ET.SubElement(Trackpoint,'Position')
                LatitudeDegrees = ET.SubElement(Position,'LatitudeDegrees')
                LatitudeDegrees.text = line[1]
                LongitudeDegrees = ET.SubElement(Position,'LongitudeDegrees')
                LongitudeDegrees.text = line[2]
                AltitudeMeters = ET.SubElement(Trackpoint,'AltitudeMeters')
                AltitudeMeters.text = '0.0'
                # TODO: Some (all?) Huawei devices don't collect Altitude data,
                # but in that case can we call on some open API to estimate it?
                DistanceMeters = ET.SubElement(Trackpoint,'DistanceMeters')
                DistanceMeters.text = line[3]
                # TODO: Do any Huawei devices collect this?

            if line[4]:
                HeartRateBpm = ET.SubElement(Trackpoint,'HeartRateBpm')
                HeartRateBpm.set('xsi:type','HeartRateInBeatsPerMinute_t')
                Value = ET.SubElement(HeartRateBpm, 'Value')
                Value.text = str(line[4])

        #### Creator
        # TODO: See if we can scrape this data from other files in the .tar
        Creator = ET.SubElement(Activity,'Creator')
        Creator.set('xsi:type','Device_t')
        Name = ET.SubElement(Creator,'Name')
        Name.text = 'Huawei Fitness Tracking Device'
        UnitId = ET.SubElement(Creator,'UnitId')
        UnitId.text = '0000000000'
        ProductID = ET.SubElement(Creator,'ProductID')
        ProductID.text = '0000'
        Version = ET.SubElement(Creator,'Version')
        VersionMajor = ET.SubElement(Version,'VersionMajor')
        VersionMajor.text = '0'
        VersionMinor = ET.SubElement(Version,'VersionMinor')
        VersionMinor.text = '0'
        BuildMajor = ET.SubElement(Version,'BuildMajor')
        BuildMajor.text = '0'
        BuildMinor = ET.SubElement(Version,'BuildMinor')
        BuildMinor.text = '0'

        ## Author
        Author = ET.SubElement(TrainingCenterDatabase,'Author')
        Author.set('xsi:type','Application_t') # TODO: Check this is right
        Name = ET.SubElement(Author,'Name')
        Name.text = 'Huawei_TCX_Converter'
        Build = ET.SubElement(Author,'Build')
        Version = ET.SubElement(Build,'Version')
        VersionMajor = ET.SubElement(Version,'VersionMajor')
        VersionMajor.text = '1'
        VersionMinor = ET.SubElement(Version,'VersionMinor')
        VersionMinor.text = '0'
        BuildMajor = ET.SubElement(Version,'BuildMajor')
        BuildMajor.text = '1'
        BuildMinor = ET.SubElement(Version,'BuildMinor')
        BuildMinor.text = '0'
        LangID = ET.SubElement(Author,'LangID')
        LangID.text = 'en' # TODO: Translations? Probably not...
        PartNumber = ET.SubElement(Author,'PartNumber')
        PartNumber.text = '000-00000-00'

        print('OKAY')
    except:
        print('FAILED')

    return TrainingCenterDatabase

def indent(elem, level=0):
    i = "\n" + level*"  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            indent(elem, level+1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

def save_xml(TrainingCenterDatabase, input_file):
    print('saving: ', end='')
    try:
        tree = ET.ElementTree(TrainingCenterDatabase)
        indent(TrainingCenterDatabase)
        new_filename = input_file+'.tcx'
        with open(new_filename, 'wb') as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>'.encode('utf8'))
            tree.write(f, 'utf-8')
        print('OKAY')
    except:
        print('FAILED')

    return new_filename

def validate_xml(filename, xmlschema_found):
    print('validating: ', end='')
    if xmlschema_found:
        try:
            # Make temporary directory
            with tempfile.TemporaryDirectory() as tempdir:
                # Download and import schema to check against
                url = 'https://www8.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd'
                urllib.request.urlretrieve(url, tempdir+'/TrainingCenterDatabasev2.xsd')
                schema = xmlschema.XMLSchema(tempdir+'/TrainingCenterDatabasev2.xsd')
                # Validate
                schema.validate(filename)
                print('OKAY')
        except:
            print('FAILED')
    else:
        print('FAILED: xmlschema not found')

        return

input_file, options = parse_arguments()
gps_data, hr_data = read_file(input_file)
if options['filter']: gps_data = filter_data(gps_data)
gps_data = process_gps(gps_data)
data = merge_data(gps_data, hr_data)
stats = file_details(data)
TrainingCenterDatabase = generate_xml(data, stats)
filename = save_xml(TrainingCenterDatabase, input_file)
if options['validate']: validate_xml(filename, xmlschema_found)
print('\n')
