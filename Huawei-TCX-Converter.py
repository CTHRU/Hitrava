# Huawei-TCX-Converter.py
# Ari Cooper-Davis, 2019 - github.com/aricooperdavis/Huawei-TCX-Converter

# Import resources from Standard Library
import xml.etree.cElementTree as ET # TCX (type of XML) construction
import math, operator, sys # Distance calcs, sorting by timestamp, arguments
from datetime import datetime as dt # Time formatting
# Import external resources
try:
    import xmlschema # Validation
    import tempfile, urllib.request # Downloading and storing validation schema
    xmlschema_found = True
except ModuleNotFoundError:
    xmlschema_found = False

def parse_arguments() -> tuple:
    """
    Parses command line arguments for filename and options

    Parameters
    ----------
    sys.argv

    Returns
    -------
    input_file : string
        HiTrack filename
    options: dict of boolean/string
        {'filter': boolean, 'validate': boolean, 'sport': string}
    """

    print('\n')
    options = {'filter': False, 'validate': False, 'sport': 'Running'}
    input_file = ''
    for argument in sys.argv[1:]:
        if argument == '-f':
            options['filter'] = True
        elif argument == '-v':
            options['validate'] = True
        elif argument == '-b':
            options['sport'] = 'Biking'
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

    if not input_file:
        print('Error: no file given')
        exit()

    return input_file, options

def read_file(input_file: str) -> dict:
    """
    Read the file and extract relevant data

    Parameters
    ----------
    input_file : string
        HiTrack filename

    Returns
    -------
    data: dict of lists of lists
        {'gps': list of lists, 'alti': list of lists, 'hr': list of lists, 'cad': list of lists}
    """

    def _normalize_timestamp(timestamp: float) -> float:
        """ Normalize the timestamp

        Timestamps taken from different devices can have different values. Most common are seconds
        (i.e. t=1.543646826E9) or microseconds (i.e. t=1.55173212E12).
        This method implements a generic normalization function that transform all values to valid
        unix timestamps (integer with 10 digits).
        """
        oom = int(math.log10(timestamp))
        if oom == 9:
            return timestamp

        divisor = 10 ** (oom - 9) if oom > 9 else 0.1 ** (9 - oom)
        return timestamp / divisor

    print('---- Input File ----')
    print('reading: ', end='')
    try:
        data = {'gps': [], 'alti': [], 'hr': [], 'cad': []}
        with open(input_file) as f:
            for line in f:
                # Loop over file line by line
                holding_list = []

                if line[0:6] == 'tp=lbs': # Location lines
                    for x in [6,3,4,0,0,0,0]: # time, lat, long, [alti], [dist], [hr], [cad]
                        if x == 0:
                            holding_list.append('') # Fill in blanks with blank
                        else:
                            holding_list.append(float(line.split('=')[x].split(';')[0]))
                    holding_list[0] = _normalize_timestamp(holding_list[0])
                    data['gps'].append(holding_list)

                elif line[0:6] == 'tp=h-r': # Heart-rate lines
                    for x in [2,0,0,0,0,3,0]: #time, [lat], [long], [alti], [dist], hr, [cad]
                        if x == 0:
                            holding_list.append('')
                        elif x == 2:
                            holding_list.append(int(float(line.split('=')[x].split(';')[0])))
                        else:
                            holding_list.append(int(line.split('=')[x].split(';')[0]))
                    holding_list[0] = _normalize_timestamp(holding_list[0])
                    data['hr'].append(holding_list)

                elif line[0:6] == 'tp=s-r': # Cadence lines
                    for x in [2,0,0,0,0,0,3]: #time, [lat], [long], [alti], [dist], [hr], cad
                        if x == 0:
                            holding_list.append('')
                        elif x == 2:
                            holding_list.append(int(float(line.split('=')[x].split(';')[0])))
                        else:
                            holding_list.append(int(line.split('=')[x].split(';')[0]))
                    holding_list[0] = _normalize_timestamp(holding_list[0])
                    data['cad'].append(holding_list)

                elif line[0:7] == 'tp=alti': # Altitude lines
                    for x in [2,0,0,3,0,0,0]: #time, [lat], [long], alti, [dist], [hr], [cad]
                        if x == 0:
                            holding_list.append('')
                        elif x == 2:
                            holding_list.append(int(float(line.split('=')[x].split(';')[0])))
                        else:
                            holding_list.append(float(line.split('=')[x].split(';')[0]))
                    holding_list[0] = _normalize_timestamp(holding_list[0])
                    data['alti'].append(holding_list)

        # Sort GPS data by date for distance computation
        data['gps'] = sorted(data['gps'], key=lambda x : x[0])

    except:
        print('FAILED')
        exit()

    print('OKAY')
    return data

def filter_data(data: dict) ->  dict:
    """
    Remove unwanted/aberrant lines from data

    Parameters
    ----------
    data : dictionary of lists of lists
        {'gps': list of lists, 'alti': list of lists, 'hr': list of lists, 'cad': list of lists}

    Returns
    -------
    data : dictionary of lists
        {'gps': list of lists, 'alti': list of lists, 'hr': list of lists, 'cad': list of lists}
    """

    print('filtering: ', end='')
    original_data = data # Back-up data pre-filtering in case of failure

    try:
        for line in data['gps']:
            # GPS is lost (defaults to (90, -80))
            if line[1] == 90.0 and line[2] == -80.0:
                data['gps'].remove(line)

        for line in data['hr']:
            # Heart-rate is too low/high (type is xsd:unsignedbyte)
            if line[5] < 1 or line[5] > 254:
                data['hr'].remove(line)

        for line in data['cad']:
            # Cadence is too low/high (type is xsd:unsignedbyte)
            if line[6] < 0 or line[6] > 254:
                data['cad'].remove(line)

        for line in data['alti']:
            # Altitude is too low/high (dead sea/everest)
            if line[3] < -1000 or line[3] > 10000:
                data['alti'].remove(line)

        print('OKAY')

    except:
        print('FAILED')
        return original_data

    return data

def process_gps(data: dict) -> dict:
    """
    Add distance information to all gps tagged data points

    Parameters
    ----------
    data : dictionary of lists of lists
        {'gps': list of lists, 'alti': list of lists, 'hr': list of lists, 'cad': list of lists}

    Returns
    -------
    data : dictionary of lists of lists
        {'gps': list of lists, 'alti': list of lists, 'hr': list of lists, 'cad': list of lists}
    """

    def _vincenty(point1: list, point2: list) -> float:
        """
        Determine distance between two coordinates

        Parameters
        ----------
        point1 : Tuple
            [Latitude of first point, Longitude of first point]
        point2: Tuple
            [Latitude of second point, Longitude of second point]

        Returns
        -------
        s : float
            distance in m between point1 and point2

        """

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

    print('processing gps: ', end='')
    try:
        # Loop through data line by line
        for n, entry in enumerate(data['gps']):
            # Calculate distances between points based on vincenty distances
            if n == 0: # first gps-point has no distance
                #time, lat, long, [alti], [dist], [hr], [cad]
                entry[4] = 0
            else:
                # TODO: Try other point-to-point distance calculations
                entry[4] = (_vincenty((float(entry[1]),float(entry[2])),
                    (float(data['gps'][n-1][1]),float(data['gps'][n-1][2])))+data['gps'][n-1][4])

    except:
        print('FAILED')
        exit()

    print('OKAY')

    return data

def file_details(data: dict, options: dict) -> tuple:
    """
    Determine metadata, print to command-line, and format for saving

    Parameters
    ----------
    data : dictionary of lists of lists
        {'gps': list of lists, 'alti': list of lists, 'hr': list of lists, 'cad': list of lists}
    options: dictionary of boolean/string
        {'filter': boolean, 'validate': boolean, 'sport': string}

    Returns
    -------
    data : dictionary of lists of lists
        {'gps': list of lists, 'alti': list of lists, 'hr': list of lists, 'cad': list of lists}
    stats : dictionary of strings
        {'start_time': string, 'duration': string, 'distance': string}
    """
    # time, lat, long, [alti], [dist], [hr], [cad]
    try:
        if data['gps']:
            distance = data['gps'][-1][4] #distance is zero if no gps data
        else:
            distance = 0

        data = merge_data(data)

        # time, lat, long, [alti], [dist], [hr], [cad]
        start_time = data[0][0]
        duration = data[-1][0]-start_time

        stats = {'start_time': start_time, 'duration': duration, 'distance': distance}

        print('\n---- Details ----')
        print('sport: '+str(options['sport']))
        print('start: '+str(dt.utcfromtimestamp(stats['start_time'])))
        print('duration: '+str(dt.utcfromtimestamp(stats['duration']).strftime('%H:%M:%S')))
        print('distance: '+str(int(stats['distance'])), end='m\n')

        # Format stats for saving
        stats['start_time'] = dt.utcfromtimestamp(stats['start_time']).isoformat()+'.000Z'
        stats['duration'] = str(stats['duration'])
        stats['distance'] = str(int(stats['distance']))

    except:
        print('Something went wrong :-(')
        exit()

    return data, stats

def merge_data(data: dict) -> list:
    """
    Merge different data types into one list

    Parameters
    ----------
    data : dictionary of lists of lists
        {'gps': list of lists, 'alti': list of lists, 'hr': list of lists, 'cad': list of lists}

    Returns
    -------
    data : list of lists
        [[time, lat, long, alti, dist, hr, cad],[...]]
    """

    print('processing heart-rate/cadence: ', end='')
    # Sort data array chronologically
    try:
        data = data['gps']+data['alti']+data['hr']+data['cad'] #time, lat, long, alti, dist, hr, cad
        gettime = operator.itemgetter(0)
        data = sorted(data, key=gettime)

        # Merge duplicated timestamps
        for n, entry in enumerate(data):
            if n == 0:
                pass
            else:
                if entry[0] == data[n-1][0]: #if timestamp is same as previous
                    for x in range(1,7):
                        if entry[x]:
                            data[n-1][x] = entry[x] #copy all data back to previous
                    data.remove(entry) #and delete current

    except:
        print('FAILED')
        exit()

    print('OKAY')
    return data

def generate_xml(data: list, stats: dict, options: dict) -> ET.Element:
    """
    Generate xml file from extracted data and user options

    Parameters
    ----------
    data : list of lists
        [[time, lat, long, alti, dist, hr, cad],[...]]
    stats : dictionary of strings
        {'start_time': string, 'duration': string, 'distance': string, 'altitude': string}
    options: dictionary of boolean/string
        {'filter': boolean, 'validate': boolean, 'sport': string}

    Returns
    -------
    TrainingCenterDatabase : ET.Element
    """

    print('\n---- XML file ----')
    print('generating: ', end='')

    try:
        # TrainingCenterDatabase
        TrainingCenterDatabase = ET.Element('TrainingCenterDatabase')
        TrainingCenterDatabase.set('xsi:schemaLocation','http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2 http://www.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd')
        TrainingCenterDatabase.set('xmlns', 'http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2')
        TrainingCenterDatabase.set('xmlns:xsd', 'http://www.w3.org/2001/XMLSchema')
        TrainingCenterDatabase.set('xmlns:xsi', 'http://www.w3.org/2001/XMLSchema-instance')
        TrainingCenterDatabase.set('xmlns:ns3', 'http://www.garmin.com/xmlschemas/ActivityExtension/v2')
        ## Activities
        Activities = ET.SubElement(TrainingCenterDatabase,'Activities')

        ### Activity
        Activity = ET.SubElement(Activities,'Activity')
        Activity.set('Sport',options['sport'])
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
            line[3] = str(line[3]) #alti
            line[4] = str(line[4]) #distance
            line[5] = str(line[5]) #heart-rate
            line[6] = str(line[6]) #cadence

            Trackpoint = ET.SubElement(Track,'Trackpoint')
            Time = ET.SubElement(Trackpoint,'Time')
            Time.text = line[0]

            if line[1]:
                Position = ET.SubElement(Trackpoint,'Position')
                LatitudeDegrees = ET.SubElement(Position,'LatitudeDegrees')
                LatitudeDegrees.text = line[1]
                LongitudeDegrees = ET.SubElement(Position,'LongitudeDegrees')
                LongitudeDegrees.text = line[2]

            if line[3]:
                AltitudeMeters = ET.SubElement(Trackpoint,'AltitudeMeters')
                AltitudeMeters.text = line[3]
                # TODO: Some (all?) Huawei devices don't collect Altitude data,
                # but in that case can we call on some open API to estimate it?

            if line[1]:
                DistanceMeters = ET.SubElement(Trackpoint,'DistanceMeters')
                DistanceMeters.text = line[4]
                # TODO: Do any Huawei devices collect this?

            if line[5]:
                HeartRateBpm = ET.SubElement(Trackpoint,'HeartRateBpm')
                HeartRateBpm.set('xsi:type','HeartRateInBeatsPerMinute_t')
                Value = ET.SubElement(HeartRateBpm, 'Value')
                Value.text = line[5]

            if line[6]:
                if options['sport'] == 'Biking':
                    Cadence = ET.SubElement(Trackpoint, 'Cadence')
                    Cadence.text = line[6]
                elif options['sport'] == 'Running':
                    Extensions = ET.SubElement(Trackpoint, 'Extensions')
                    TPX = ET.SubElement(Extensions, 'TPX')
                    TPX.set('xmlns','http://www.garmin.com/xmlschemas/ActivityExtension/v2')
                    RunCadence = ET.SubElement(TPX, 'RunCadence')
                    RunCadence.text = line[6]

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

def indent(elem: ET.Element, level: int = 0):
    """
    Adds whitespace to xml files to improve readability

    Parameters
    ----------
    elem : ET.Element or ET.SubElement
        Text information to indent

    level : int
        Indentation level desired

    Returns
    -------
    None
        Changes are made in place
    """

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

def save_xml(TrainingCenterDatabase: ET.Element, input_file: str) -> str:
    """
    Saves TCX file as XML

    Parameters
    ----------
    TrainingCenterDatabase : ET.Element
        XML data structure to save

    input_file : string
        Input file name

    Returns
    -------
    new_filename : string
        Final filename
    """

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

def validate_xml(filename: str, xmlschema_found: bool):
    """
    Validates saved TCX (XML) file

    Parameters
    ----------
    filename : string
        Name of TCX file to validate

    xmlschema_found : boolean
        Describes whether or not the XMLSchema library has been imported

    Returns
    -------
    None
        Prints result to command-line
    """

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

def main():
    # Call all functions (considering user options)
    input_file, options = parse_arguments()
    data = read_file(input_file)
    if options['filter']: data = filter_data(data)
    data = process_gps(data)
    data, stats = file_details(data, options)
    TrainingCenterDatabase = generate_xml(data, stats, options)
    filename = save_xml(TrainingCenterDatabase, input_file)
    if options['validate']: validate_xml(filename, xmlschema_found)

    # Whitespace improves formatting
    print('\n')

if __name__ == '__main__':
    main()
