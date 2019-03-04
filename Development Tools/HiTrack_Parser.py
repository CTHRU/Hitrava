# HiTrack Parser

# Imports
import math, sys
from datetime import datetime as dt

# Utility function definitions

def vincenty(point1, point2):
    # WGS 84
    a = 6378137  # meters
    f = 1 / 298.257223563
    b = 6356752.314245  # meters; b = (1 - f)a
    MILES_PER_KILOMETER = 0.621371
    MAX_ITERATIONS = 200
    CONVERGENCE_THRESHOLD = 1e-12  # .000,000,000,001
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
            return 0.0  # coincident points
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
            break  # successful convergence
    else:
        return None  # failure to converge
    uSq = cosSqAlpha * (a ** 2 - b ** 2) / (b ** 2)
    A = 1 + uSq / 16384 * (4096 + uSq * (-768 + uSq * (320 - 175 * uSq)))
    B = uSq / 1024 * (256 + uSq * (-128 + uSq * (74 - 47 * uSq)))
    deltaSigma = B * sinSigma * (cos2SigmaM + B / 4 * (cosSigma *
                 (-1 + 2 * cos2SigmaM ** 2) - B / 6 * cos2SigmaM *
                 (-3 + 4 * sinSigma ** 2) * (-3 + 4 * cos2SigmaM ** 2)))
    s = b * A * (sigma - deltaSigma)
    # meters to kilometers
    return round(s, 6)

# Filename processing
# filename: HiTrack_1551547691000155155114800030001
input_file = sys.argv[1]
# Filename appears to always be prefixed by HiTrack_
assert input_file[0:8] == 'HiTrack_'
# Then there are two unix timestamps in milliseconds, presumably start/end times
# TODO: This seems to be hit and miss - it's worked for me most of the time...
assert len(input_file[8:]) == 31
StartTime = input_file[8:18]
EndTime = input_file[21:31]
duration = str(int(EndTime)-int(StartTime))
# Convert to human-readable timestamps for error checking
print('---- Information extracted from filename ----')
print('start: ', end='')
print(dt.utcfromtimestamp(int(StartTime)).strftime('%Y-%m-%d %H:%M:%S'), end=' UTC\n')
print('end: ', end='')
print(dt.utcfromtimestamp(int(EndTime)).strftime('%Y-%m-%d %H:%M:%S'), end=' UTC\n')
print('duration: ', end='')
print(dt.utcfromtimestamp(int(duration)).strftime('%H:%M:%S'))
# Then 30001 - don't know what this means, timezone, exercise type? Unimportant
assert input_file[34:] == '30001'

# Extract useful information from file
# File is made up of 5 sections, but for the moment we're only interested in the
# sections that have associated location data (tp=lbs). We can interpolate heart
# rate, speed, pace etc at these points in the future if we care enough.
#
#    lbs   |   p-m   |   b-p-m   |   h-r   |   rs
# --------------------------------------------------
# location |  pace   |     ?     |  pulse  | speed
#

data = []
with open(input_file) as f:
   for line in f:
       if line[0:6] == 'tp=lbs':
           holding_list = []
           for x in [3,4,6]:
               holding_list.append(line.split('=')[x].split(';')[0])
           data.append(holding_list)

total_distance = 0
for n, entry in enumerate(data):
    # Calculate distances between points based on vincenty distances
    if n == 0:
        entry.append(0)
    else:
        entry.append(vincenty((float(entry[0]),float(entry[1])),
            (float(data[n-1][0]),float(data[n-1][1]))))
    total_distance += entry[-1]
    # Convert timestamps into 2002-05-30T09:30:10Z format
    time = float(entry[2][:-3].replace('.',''))
    entry[2] = dt.utcfromtimestamp(int(time)).isoformat()+'.000Z'

print('---- Information extracted from file ----')
print('location data points: ', end='')
print(len(data))
print('distance (approx): ', end='')
print(int(total_distance), end=' m\n')
