# Huawei-TCX-Converter.py
# Ari Cooper-Davis / Christoph Vanthuyne , 2019 - github.com/aricooperdavis/Huawei-TCX-Converter

import argparse
import csv
import datetime
import logging
import math
import operator
import os
import sys
import tarfile
import tempfile

import urllib.request as url_req
import xml.etree.cElementTree as xml_et
from datetime import datetime as dts
from datetime import timedelta as dts_delta

# External libraries that require installation
try:
    import xmlschema  # (only) needed to validate the generated TCX XML.
except:
    print('Info - External library xmlschema could not be imported.\n' +
          'It is required when using the --validate option.\n' +
          'It can be installed using: pip install xmlschema')

# Global Constants
PROGRAM_NAME = 'Huawei-TCX-Converter'
PROGRAM_MAJOR_VERSION = '2'
PROGRAM_MINOR_VERSION = '0'
PROGRAM_MAJOR_BUILD = '1908'
PROGRAM_MINOR_BUILD = '2201'

OUTPUT_DIR = './output'


class HiActivity:
    """" This class represents all the data contained in a HiTrack file."""

    TYPE_WALK = 'Walk'
    TYPE_RUN = 'Run'
    TYPE_CYCLE = 'Cycle'
    TYPE_SWIM = 'Swim'
    TYPE_UNKNOWN = '?'

    _ACTIVITY_TYPE_LIST = (TYPE_WALK, TYPE_RUN, TYPE_CYCLE, TYPE_SWIM)

    def __init__(self, activity_id: str, activity_type: str = TYPE_UNKNOWN):
        logging.debug('New HiTrack activity to process <%s>', activity_id)
        self.activity_id = activity_id

        if activity_type == self.TYPE_UNKNOWN:
            self.activity_type = self.TYPE_UNKNOWN
        else:
            self.set_activity_type(activity_type)  # validate and set activity type of the activity

        self.pool_length = -1

        self.start = None
        self.stop = None

        # Create an empty segment and segment list
        self._current_segment = None
        self.segment_list = []

        # Create an empty detail data dictionary. key = timestamp, value = dict{t, lat, lon, alt, hr)
        self.data_dict = {}

    def set_activity_type(self, activity_type: str):
        if activity_type in self._ACTIVITY_TYPE_LIST:
            logging.info('Setting activity type of activity %s to %s', self.activity_id, activity_type)
            self.activity_type = activity_type
        else:
            logging.error('Invalid activity type <%s>', activity_type)
            raise Exception('Invalid activity type <%s>', activity_type)

    def set_pool_length(self, pool_length: int):
        logging.info('Setting pool length of activity %s to %d', self.activity_id, pool_length)
        self.pool_length = pool_length
        if not self.activity_type == self.TYPE_SWIM:
            logging.warning('Pool length for activity %s of type %s will not be used. It is not a swimming activity',
                            self.activity_id, self.activity_type)

    def _add_segment_start(self, segment_start: datetime):
        if self._current_segment:
            logging.error('Request to start segment when there is already a current segment active')
            return

        logging.debug('Adding segment start at %s', segment_start)

        # No current segment, create one
        self._current_segment = {'start': segment_start, 'stop': None}
        if not self.start:
            # Set activity start
            self.start = segment_start

    def _add_segment_stop(self, segment_stop: datetime):
        logging.debug('Adding segment stop at %s', segment_stop)
        if not self._current_segment:
            logging.error('Request to stop segment when there is no current segment active')
            return

        # Set stop of current segment, add it to the segment list and clear the current segment
        self._current_segment['stop'] = segment_stop
        self._current_segment['duration'] = int((segment_stop - self._current_segment['start']).total_seconds())
        if not self.activity_type == self.TYPE_SWIM:
            # Calculate distance based on distance data directly for non-swimming activities
            self._current_segment['distance'] = self.data_dict[segment_stop]['distance'] - \
                                                self.data_dict[self._current_segment['start']]['distance']
        self.segment_list.append(self._current_segment)
        self._current_segment = None

        # Update activity stop
        self.stop = segment_stop

    # TODO Verify if something useful can be done with the (optional) altitude data in the tp=lbs records
    def add_location_data(self, data: []):
        """"Add location data from a tp=lbs record in the HiTrack file.
        Information:
        - When tracking an activity with a mobile phone only, the HiTrack files seem to contain altitude
          information in the alt data tag (in ft). This seems not to be the case when an activity is started from a
          tracking device.
        - When tracking an activity with a mobile phone only, the HiTrack files seem to contain stop records (see below)
          with a valid timestamp. This is not the case when a tracking device is used, where the timestamp of these
          records = 0
        - When tracking an activity with a tracking the device, the records in the HiTrack file seem to be ordered by
          record type. This seems not to be the case when using a mobile phone only, where records seem to be added in
          order of the timestamp they occurred.
        Assumption: proper activity stop and/or activity segment stop relies on the presence of the records
        tp=lbs;lat=90;lon=-80;alt=0.
        """

        logging.debug('Adding location data %s', data)

        try:
            # Create a dictionary from the key value pairs
            location_data = dict(data)

            # All raw values are floats (timestamp will be converted later)
            for keys in location_data:
                location_data[keys] = float(location_data[keys])

            # Detect pause or stop records (lat = 90, long = -80, alt = 0) and handle segment data creation
            if location_data['lat'] == 90 and location_data['lon'] == -80:
                self._add_segment_stop(sorted(self.data_dict.keys())[-1])  # Use timestamp of last (location) record
                return
        except Exception as e:
            logging.error('One or more required data fields (t, lat, lon) missing or invalid in location data %s\n%s',
                          data,
                          e)
            raise Exception('One or more required data fields (t, lat, lon) missing or invalid in location data %s',
                            data)

        # Regular location record.
        # Convert the timestamp to a datetime
        location_data['t'] = _convert_hitrack_timestamp(location_data['t'])
        # Calculate distance from last location and add cumulative distance to record (required for export)
        if self.data_dict:  # First location has no distance
            # Get the last location record that was added
            #last_location = self.data_dict[sorted(self.data_dict.keys())[-1]]
            last_location = self._get_last_location()
            location_data['distance'] = self._vincenty((last_location['lat'], last_location['lon']),
                                                       (location_data['lat'], location_data['lon'])) + \
                                        last_location['distance']
        else:
            location_data['distance'] = 0

        # If we don't have a segment, create one.
        if not self._current_segment:
            self._add_segment_start(location_data['t'])
        # Add location data
        self._add_data_detail(location_data)

    def _get_last_location(self) -> dict:
        """ Returns the last location record in the data dictionary """
        if self.data_dict:
            reverse_sorted_data = sorted(self.data_dict.items(), key=operator.itemgetter(0), reverse=True)
            for t, data in reverse_sorted_data:
                if 'lat' in data:
                    return data
        # Empty data dictionary or no last location found in dictionary
        return None

    def _vincenty(self, point1: tuple, point2: tuple) -> float:
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
            logging.error('Failed to calculate distance between %s and %s', point1, point2)
            raise Exception('Failed to calculate distance between %s and %s', point1, point2)

        uSq = cosSqAlpha * (a ** 2 - b ** 2) / (b ** 2)
        A = 1 + uSq / 16384 * (4096 + uSq * (-768 + uSq * (320 - 175 * uSq)))
        B = uSq / 1024 * (256 + uSq * (-128 + uSq * (74 - 47 * uSq)))
        deltaSigma = B * sinSigma * (cos2SigmaM + B / 4 * (cosSigma *
                                                           (-1 + 2 * cos2SigmaM ** 2) - B / 6 * cos2SigmaM *
                                                           (-3 + 4 * sinSigma ** 2) * (-3 + 4 * cos2SigmaM ** 2)))
        s = b * A * (sigma - deltaSigma)

        return round(s, 6)

    def add_heart_rate_data(self, data: []):
        """Add heart rate data from a tp=h-r record in the HiTrack file
        """
        # Create a dictionary from the key value pairs
        logging.debug('Adding heart rate data %s', data)

        try:
            hr_data = dict(data)
            # Use unique keys. Update keys k -> t and v -> hr
            hr_data['t'] = _convert_hitrack_timestamp(float(hr_data.pop('k')))
            hr_data['hr'] = int(hr_data.pop('v'))

            # Ignore invalid heart rate data (for export)
            if hr_data['hr'] < 1 or hr_data['hr'] > 254:
                logging.warning('Invalid heart rate data detected and ignored in data %s', data)
        except Exception as e:
            logging.error('One or more required data fields (k, v) missing or invalid in heart rate data %s\n%s',
                          data,
                          e)
            raise Exception('One or more required data fields (k, v) missing or invalid in heart rate data %s\n%s',
                            data)

        # Add heart rate data
        self._add_data_detail(hr_data)

    def add_altitude_data(self, data: []):
        """Add altitude data from a tp=alti record in a HiTrack file"""
        # Create a dictionary from the key value pairs
        logging.debug('Adding altitude data %s', data)

        try:
            alti_data = dict(data)
            # Use unique keys. Update keys k -> t and v -> hr
            alti_data['t'] = _convert_hitrack_timestamp(float(alti_data.pop('k')))
            alti_data['alti'] = int(alti_data.pop('v'))

            # Ignore invalid heart rate data (for export)
            if alti_data['alti'] < -1000 or alti_data['alti'] > 10000:
                logging.warning('Invalid altitude data detected and ignored in data %s', data)
                return
        except Exception as e:
            logging.error('One or more required data fields (k, v) missing or invalid in altitude data %s\n%s',
                          data,
                          e)
            raise Exception('One or more required data fields (k, v) missing or invalid in altitude data %s\n%s', data)

        # Add altitude data
        self._add_data_detail(alti_data)

    # TODO Further verification of assumptions and testing required related to auto activity type detection
    # TODO For activities that were tracked using a phone only without a fitness device, there are no s-r records. Hence, in these cases auto detection should use a 'fallback mode' e.g. by using the p-m records (and assume that swimming activities with phone only won't occur)
    def add_step_frequency_data(self, data: []):
        """Add step frequency data from a tp=s-r record in a HiTrack file.
        The unit of measure of the step frequency is steps/minute.
         Assumptions:
         - Cycling activities have s-r records with value = 0 (and Huawei/Honor doesn't seem to sell cadence meters)
         - Swimming activities have s-r records but no lbs records. The s-r records have negative values
           (indicating the stroke type). It seems that s-r records are used to indicate
           the start of a new segments for swimming.
         """

        logging.debug('Adding step frequency data or detect cycling or swimming activities %s', data)

        try:
            # Create a dictionary from the key value pairs
            step_freq_data = dict(data)
            # Use unique keys. Update keys k -> t and v -> s_r
            step_freq_data['t'] = _convert_hitrack_timestamp(float(step_freq_data.pop('k')))
            step_freq_data['s-r'] = int(step_freq_data.pop('v'))

            # Try to auto detect the activity type (only if not already detected)
            if step_freq_data['s-r'] == 0 and self.activity_type == self.TYPE_UNKNOWN:
                # Cycling can be detected by (all) step frequency records with value = 0.
                # Found at least one cycling activity that had a v=10 value for the last tp=s-r record (stop?).
                # To prevent auto detection of walking/running based on this last record, do not process tp=s-r records
                # any further after the first v=0 record.
                # TODO Cycling activities registered without a fitness device (phone only) don't have any s-r records and hence auto activity type detection for these activities does not work
                # TODO Needs verification if v=0 records could be generated for walking/running activities e.g when standing still for a while right after the start of a new activity
                # TODO Required? Add better detection of cycling by checking if tp=lbs records were processed?
                if not self.activity_type == self.TYPE_CYCLE:
                    self.set_activity_type(self.TYPE_CYCLE)
                else:
                    logging.warning("Activity type Cycle auto detected earlier. This step frequency record is ignored.")
                return  # Do not process the zero (cycle) records any further
            elif step_freq_data['s-r'] < 0 or self.activity_type == self.TYPE_SWIM:
                # Swimming can be detected by step frequency records with value < 0.
                # The last record has a positive value and should not be processed.
                # Hence, this record will be ignored if a swimming activity was already detected.
                # Timestamps of these records don't seem to have any relation to the activity as it seems they are
                # all about a minute apart. No clue to the meaning of the value except for the activity type indication.
                # The only plausible relation is the number of laps that were swum.
                if not self.activity_type == self.TYPE_SWIM:
                    self.set_activity_type(self.TYPE_SWIM)
                    # Explicitly set the start time of the activity on the first s-r record (all other timestamps in the
                    # file are relative to this timestamp)
                    self.start = step_freq_data['t']
                return
            else:
                # tp=s-r record with v > 0. Not swimming nor cycling, but walking or running. Add step frequency data.
                if self.activity_type == self.TYPE_UNKNOWN:
                    # TODO add distinction between walking and running here?
                    self.set_activity_type(self.TYPE_WALK)
                self._add_data_detail(step_freq_data)
        except Exception as e:
                logging.error('One or more required data fields (k, v) missing or invalid in step frequency data %s\n%s',
                              data,
                              e)
                raise Exception('One or more required data fields (k, v) missing or invalid in step frequency data %s\n%s',
                                data)

    def add_swolf_data(self, data: []):
        """ Add SWOLF (swimming) data from a tp=s-r record in a HiTrack file
        SWOLF value = time to swim one pool length + number of strokes
        """

        logging.debug('Adding SWOLF swim data %s', data)

        try:
            # Create a dictionary from the key value pairs
            swolf_data = dict(data)
            # Use unique keys. Update keys k -> t and v -> swf
            # Time of SWOLF swimming data is relative to activity start.
            # The first record with k=0 is the value registered after 5 seconds of activity.
            swolf_data['t'] = self.start + dts_delta(seconds=int(swolf_data.pop('k')) + 5)
            swolf_data['swf'] = int(swolf_data.pop('v'))

            # If there is no last swf record or the last added swf record had a different swf value, then this record
            # belongs to a new lap (segment)
            # TODO There is a chance that checking on SWOLF only might miss a lap in case two consecutive laps have the same SWOLF (but then again, chances are that stroke and speed data are also identical)
            # TODO Since SWOLF value contains both time and strokes, add extra check to not process consecutive same time laps beyond the SWOLF value.
            if not self._current_segment:
                # First record of first lap. Start new segment (lap)
                self._add_segment_start(swolf_data['t'] - dts_delta(seconds=5))
                # Add the current segment directly to the segment list here. Because there's no 'last record' indication
                # like with the tp=lbs records, the last segment will have no stop date. This will be dealt with when
                # the swim data is requested via the _get_sim_data() function.
                self.segment_list.append(self._current_segment)
            else:
                last_swolf = self.data_dict[sorted(self.data_dict.keys())[-1]]
                if last_swolf['swf'] != swolf_data['swf']:
                    # New lap detected.
                    # Close segment of previous lap. Since the current lap starts at the exact same time
                    self._current_segment['stop'] = last_swolf['t']
                    self._current_segment = None
                    # Open new segment for this lap. End of previous lap is start of current lap.
                    # Add 1 microsecond to split the lap data correctly.
                    self._add_segment_start(last_swolf['t'] + dts_delta(microseconds=1))
                    # Add the current segment directly to the segment list here. Because there's no 'last record'
                    # indication like with the tp=lbs records, the last segment will have no stop date. This will be
                    # dealt with when the swim data is requested via the _get_sim_data() function.
                    self.segment_list.append(self._current_segment)

        except Exception as e:
            logging.error('One or more required data fields (k, v) missing or invalid in SWOLF data %s\n%s',
                          data,
                          e)
            raise Exception('One or more required data fields (k, v) missing or invalid in SWOLF data %s\n%s',
                            data)

        # Add SWOLF data
        self._add_data_detail(swolf_data)

    def add_stroke_frequency_data(self, data: []):
        """ Add stroke frequency (swimming) data (in strokes/minute) from a tp=p-f record in a HiTrack file """

        logging.debug('Adding stroke frequency swim data %s', data)

        try:
            # Create a dictionary from the key value pairs
            stroke_freq_data = dict(data)
            # Use unique keys. Update keys k -> t and v -> p-f
            # Time of stroke frequency swimming data is relative to activity start.
            # The first record with k=0 is the value registered after 5 seconds of activity.
            stroke_freq_data['t'] = self.start + dts_delta(seconds=int(stroke_freq_data.pop('k')) + 5)
            stroke_freq_data['p-f'] = int(stroke_freq_data.pop('v'))
        except Exception as e:
            logging.error('One or more required data fields (k, v) missing or invalid in stroke frequency data %s\n%s',
                          data,
                          e)
            raise Exception('One or more required data fields (k, v) missing or invalid in stroke frequency data %s\n%s',
                            data)

        # Add stroke frequency data
        self._add_data_detail(stroke_freq_data)

    # TODO Do distance calculation for walking/running/cycling activities based on the speed records when GPS signal is lost for a longer time period or there is no GPS data at all
    def add_speed_data(self, data: []):
        """ Add speed data (in decimeter/second) from a tp=rs record in a HiTrack file """

        logging.debug('Adding speed data %s', data)

        try:
            # Create a dictionary from the key value pairs
            speed_data = dict(data)
            # Use unique keys. Update keys k -> t and v -> p-f
            # Time of speed data is relative to activity start.
            # The first record with k=0 is the value registered after 5 seconds of activity.
            speed_data['t'] = self.start + dts_delta(seconds=int(speed_data.pop('k')) + 5)
            speed_data['rs'] = int(speed_data.pop('v'))
        except Exception as e:
            logging.error('One or more required data fields (k, v) missing or invalid in speed data %s\n%s',
                          data,
                          e)
            raise Exception('One or more required data fields (k, v) missing or invalid in speed data %s\n%s',
                            data)

        # Add speed data
        self._add_data_detail(speed_data)

    def _add_data_detail(self, data: dict):
        # Add the data to the data dictionary.
        if data['t'] not in self.data_dict:
            # No data for timestamp. Add it.
            self.data_dict[data['t']] = data
        else:
            #
            self.data_dict[data['t']].update(data)

    def get_segment_data(self, segment: dict) -> list:
        """" Returns a filtered and sorted data set containing all raw parsed data from the requested segment """
        # Filter data
        if segment['stop']:
            segment_data_dict = {k: v for k, v in self.data_dict.items()
                                 if segment['start'] <= k <= segment['stop']}
        else:
            # E.g for swimming activities, the last segment is not closed due to no stop record nor valid record that
            # indicates the end of the activity. Return all remaining data starting from the start timestamp
            segment_data_dict = {k: v for k, v in self.data_dict.items()
                                 if segment['start'] <= k}

        # Sort data by timestamp (sort on key in data dictionary)
        segment_data = [value for (key, value) in sorted(segment_data_dict.items())]
        return segment_data

    def get_swim_data(self) -> list:
        """" Calculates the real swim (lap) data based on the raw parsed swim data
        The following calculation steps on the raw parsed data is applied.
        1. Starting point is the raw parsed data per lap (segment). The data consists of multiple data records
           with a 5 second time interval containing the same SWOLF and stroke frequency (in strokes/minute) values.
        2. Calculate the number of strokes in the lap.
           Number of strokes = stroke frequency x (last - first lqp timestamp) / 60
        3. Calculate the lap time: lap time = SWOLF - number of strokes

        :return
        A list of lap data dictionaries containing the following data:
           'lap' : lap number in the activity
           'start' : Start timestamp of the lap
           'stop' : Stop timestamp of the lap
           'duration' : lap duration in seconds
           'swolf' : lap SWOLF value (duration + number of strokes in lap)
           'strokes' : number of strokes in lap
           'speed' : estimated average speed during the lap in m/s.
                     Note: this is an approximate value as the minimum resolution of the raw speed data is 1 dm/s
           'distance' : estimated distance based on the average speed and the lap duration.
                        Note: this is an approximate value as the minimum resolution of the raw speed data is 1 dm/s
        """
        logging.info('Calculating swim data for activity %s', self.activity_id)

        swim_data = []

        for n, segment in enumerate(self.segment_list):
            segment_data = self.get_segment_data(segment)
            first_lap_record = segment_data[0]
            last_lap_record = segment_data[-1]

            # First record is after 5 s in lap
            raw_data_duration = (last_lap_record['t'] - first_lap_record['t']).total_seconds() + 5

            lap_data = {}
            lap_data['lap'] = n + 1
            lap_data['swolf'] = first_lap_record['swf']
            lap_data['strokes'] = round(first_lap_record['p-f'] * raw_data_duration / 60)  # Convert strokes/min -> strokes/lap
            lap_data['duration'] = lap_data['swolf'] - lap_data['strokes']  # Derive lap time from SWOLF - strokes
            if self.pool_length < 1:
                # Pool length not set. Derive estimated distance from raw speed data
                lap_data['speed'] = first_lap_record['rs'] / 10  # estimation in m/s
                lap_data['distance'] = lap_data['speed'] * lap_data['duration']
            else:
                lap_data['distance'] = self.pool_length
                lap_data['speed'] = self.pool_length / lap_data['duration']

            # Start timestamp of lap
            if not swim_data:
                lap_data['start'] = self.start
            else:
                # Start of this lap is stop of previous lap
                lap_data['start'] = swim_data[-1]['stop']
            # Stop timestamp of lap
            lap_data['stop'] = lap_data['start'] + dts_delta(seconds=lap_data['duration'])

            logging.debug('Calculated swim data for lap %d : %s', n + 1, lap_data)

            swim_data.append(lap_data)

        return swim_data

    def __repr__(self):
        to_string = self.__class__.__name__ + ' : ' + self.activity_id + ' type ' + self.activity_type
        return to_string


class HiTrackFile:
    """The HiTrackFile class represents a single HiTrack file. It contains all file handling and parsing methods."""

    def __init__(self, hitrack_filename: str):
        # Validate the file parameter and (try to) open the file for reading
        if not hitrack_filename:
            logging.error('Parameter HiTrack filename is missing')

        try:
            self.hitrack_file = open(hitrack_filename, 'r')
        except Exception as e:
            logging.error('Error opening HiTrack file <%s>\n%s', hitrack_filename, e)
            raise Exception('Error opening HiTrack file <%s>', hitrack_filename)

        self.activity = None

        # Try to parse activity start and stop datetime from the filename.
        # Original HiTrack filename is: HiTrack_<12 digit start datetime><12 digit stop datetime><5 digit unknown>
        try:
            # Get start timestamp from file in seconds (10 digits)
            self.start = _convert_hitrack_timestamp(float(os.path.basename(self.hitrack_file.name)[8:18]))
        except:
            self.start = None

        try:
            # Get stop timestamp from file in seconds (10 digits)
            self.stop = _convert_hitrack_timestamp(float(os.path.basename(self.hitrack_file.name)[20:30]))
        except:
            self.stop = None

    def parse(self) -> HiActivity:
        """
        Parses the HiTrack file and returns the parsed data in a HiActivity object
        """

        if self.activity:
            return self.activity  # No need to parse a second time if the file was already parsed

        logging.info('Parsing file <%s>', self.hitrack_file.name)

        self.activity = HiActivity(
            os.path.basename(self.hitrack_file.name))  # Create a new activity object for the file
        data_list = []
        line_number = 0
        line = ''

        try:
            csv_reader = csv.reader(self.hitrack_file, delimiter=';')
            for line_number, line in enumerate(csv_reader, start=1):
                data_list.clear()
                if line[0] == 'tp=lbs':  # Location line format: tp=lbs;k=_;lat=_;lon=_;alt=_;t=_
                    for data_index in [5, 2, 3]:  # Parse parameters t, lat, long parameters (alt not parsed)
                        # data_list.append(line[data_index].split('=')[1])   # Parse values after the '=' character
                        data_list.append(line[data_index].split('='))  # Parse key value pairs
                    self.activity.add_location_data(data_list)
                elif line[0] == 'tp=h-r':  # Heart rate line format: tp=h-r;k=_;v=_
                    for data_index in [1, 2]:  # Parse parameters k (timestamp) and v (heart rate)
                        data_list.append(line[data_index].split('='))  # Parse values after the '=' character
                    self.activity.add_heart_rate_data(data_list)
                elif line[0] == 'tp=alti':  # Altitude line format: tp=alti;k=_;v=_
                    for data_index in [1, 2]:  # Parse parameters k (timestamp) and v (heart rate)
                        data_list.append(line[data_index].split('='))  # Parse values after the '=' character
                    self.activity.add_altitude_data(data_list)
                elif line[0] == 'tp=s-r':  # Step frequency (steps/minute) format: tp=s-r;k=_;v=_
                    for data_index in [1, 2]:  # Parse parameters k (timestamp) and v (step frequency)
                        data_list.append(line[data_index].split('='))  # Parse values after the '=' character
                    self.activity.add_step_frequency_data(data_list)
                elif line[0] == 'tp=swf':  # SWOLF format: tp=swf;k=_;v=_
                    for data_index in [1, 2]:  # Parse parameters k (timestamp) and v (step frequency)
                        data_list.append(line[data_index].split('='))  # Parse values after the '=' character
                    self.activity.add_swolf_data(data_list)
                elif line[0] == 'tp=p-f':  # Stroke frequency (strokes/minute) format: tp=p-f;k=_;v=_
                    for data_index in [1, 2]:  # Parse parameters k (timestamp) and v (step frequency)
                        data_list.append(line[data_index].split('='))  # Parse values after the '=' character
                    self.activity.add_stroke_frequency_data(data_list)
                elif line[0] == 'tp=rs':  # Speed (decimeter/second) format: tp=p-f;k=_;v=_
                    for data_index in [1, 2]:  # Parse parameters k (timestamp) and v (step frequency)
                        data_list.append(line[data_index].split('='))  # Parse values after the '=' character
                    self.activity.add_speed_data(data_list)
        except Exception as e:
            logging.error('Error parsing file <%s> at line <%d>\nCSV data: %s\n%s',
                          self.hitrack_file.name, line_number, line, e)
            raise Exception('Error parsing file <%s> at line <%d>\n%s', self.hitrack_file.name, line_number)

        finally:
            self._close_file()

        return self.activity

    def _close_file(self):
        try:
            if self.hitrack_file and not self.hitrack_file.closed:
                self.hitrack_file.close()
                logging.debug('HiTrack file <%s> closed', self.hitrack_file.name)
        except Exception as e:
            logging.error('Error closing HiTrack file <%s>\n', self.hitrack_file.name, e)

    def __del__(self):
        self._close_file()


class HiTarBall:
    _TAR_HITRACK_DIR = 'com.huawei.health/files'
    _HITRACK_FILE_START = 'HiTrack_'

    def __init__(self, tarball_filename: str, extract_dir: str = OUTPUT_DIR):
        # Validate the tarball file parameter
        if not tarball_filename:
            logging.error('Parameter HiHealth tarball filename is missing')

        try:
            self.tarball = tarfile.open(tarball_filename, 'r')
        except Exception as e:
            logging.error('Error opening tarball file <%s>\n%s', tarball_filename, e)
            raise Exception('Error opening tarball file <%s>', tarball_filename)

        self.extract_dir = extract_dir
        self.hi_activity_list = []

    def parse(self, from_date: dts = None) -> list:
        try:
            # Look for HiTrack files in directory com.huawei.health/files in tarball
            tar_info: tarfile.TarInfo
            for tar_info in self.tarball.getmembers():
                if tar_info.path.startswith(self._TAR_HITRACK_DIR) \
                        and os.path.basename(tar_info.path).startswith(self._HITRACK_FILE_START):
                    hitrack_filename = os.path.basename(tar_info.path)
                    logging.info('Found HiTrack file <%s> in tarball <%s>', hitrack_filename, self.tarball.name)
                    if from_date:
                        # Is file from or later than start date parameter?
                        hitrack_file_date = _convert_hitrack_timestamp(
                            float(hitrack_filename[len(self._HITRACK_FILE_START):len(self._HITRACK_FILE_START) + 10]))
                        if hitrack_file_date >= from_date:
                            # Parse Hitrack file from tar ball
                            self._extract_and_parse_hitrack_file(tar_info)
                        else:
                            logging.info(
                                'Skipped parsing HiTrack file <%s> being an activity from %s before %s (YYYYMMDD).',
                                hitrack_filename, hitrack_file_date.isoformat(), from_date.isoformat())
                    else:
                        # Parse HiTrack file from tar ball
                        self._extract_and_parse_hitrack_file(tar_info)
            return self.hi_activity_list
        except Exception as e:
            logging.error('Error parsing tarball <%s>\n%s', self.tarball.name, e)
            raise Exception('Error parsing tarball <%s>', self.tarball.name)

    def _extract_and_parse_hitrack_file(self, tar_info):
        try:
            # Flatten directory structure in the TarInfo object to extract the file directly in the extraction directory
            tar_info.name = os.path.basename(tar_info.name)
            self.tarball.extract(tar_info, self.extract_dir)
            hitrack_file = HiTrackFile(self.extract_dir + '/' + tar_info.path)
            hi_activity = hitrack_file.parse()
            self.hi_activity_list.append(hi_activity)
        except Exception as e:
            logging.error('Error parsing HiTrack file <%s> in tarball <%s>', tar_info.path, self.tarball.name, e)

    def _close_tarball(self):
        try:
            if self.tarball and not self.tarball.closed:
                self.tarball.close()
                logging.debug('Tarball <%s> closed', self.tarball.name)
        except Exception as e:
            logging.error('Error closing tarball <%s>\n', self.tarball.name, e)

    def __del__(self):
        self._close_tarball()


class TcxActivity:
    # Strava accepts following sports: walking, running, biking, swimming.
    # Note: TCX XSD only accepts Running, Biking, Other
    # TODO According to Strava documentation (https://developers.strava.com/docs/uploads/), Strava uses a custom set of sport types? These don't seem to work for the manual uplaod action? To be checked if thsi works with API in future functionality. If so, the XSD schema in the _validate_xml() function needs to be customized too.
    _SPORT_WALKING = 'Running'  # TODO Strava 'walking'
    _SPORT_RUNNING = 'Running'  # TODO Strava 'running'
    _SPORT_BIKING = 'Biking'    # TODO Strava 'biking'
    _SPORT_SWIMMING = 'Other'   # TODO Strava 'swimming'
    _SPORT_OTHER = 'Other'

    _SPORT_TYPES = [(HiActivity.TYPE_WALK, _SPORT_WALKING),
                    (HiActivity.TYPE_RUN, _SPORT_RUNNING),
                    (HiActivity.TYPE_CYCLE, _SPORT_BIKING),
                    (HiActivity.TYPE_SWIM, _SPORT_SWIMMING),
                    (HiActivity.TYPE_UNKNOWN, _SPORT_OTHER)]

    def __init__(self, hi_activity: HiActivity, tcx_xml_schema: xmlschema = None, save_dir: str = OUTPUT_DIR):
        if not hi_activity:
            logging.error("No valid HiTrack activity specified to construct TCX activity.")
            raise Exception("No valid HiTrack activity specified to construct TCX activity.")
        self.hi_activity = hi_activity
        self.training_center_database = None
        self.tcx_xml_schema: xmlschema = tcx_xml_schema
        self.save_dir = save_dir

    def generate_xml(self) -> xml_et.Element:
        """"Generates the TCX XML content."""
        try:
            # * TrainingCenterDatabase
            training_center_database = xml_et.Element('TrainingCenterDatabase')
            training_center_database.set('xsi:schemaLocation',
                                         'http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2 http://www.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd')
            training_center_database.set('xmlns', 'http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2')
            training_center_database.set('xmlns:xsd', 'http://www.w3.org/2001/XMLSchema')
            training_center_database.set('xmlns:xsi', 'http://www.w3.org/2001/XMLSchema-instance')
            training_center_database.set('xmlns:ns3', 'http://www.garmin.com/xmlschemas/ActivityExtension/v2')

            # ** Activities
            el_activities = xml_et.SubElement(training_center_database, 'Activities')

            # *** Activity
            el_activity = xml_et.SubElement(el_activities, 'Activity')
            try:
                sport = [item[1] for item in self._SPORT_TYPES if item[0] == self.hi_activity.activity_type][0]
            finally:
                if not sport:
                    logging.warning('Activity <%s> has an undetermined/unknown sport type.',
                                    self.hi_activity.activity_id)
                    sport = self._SPORT_OTHER

            el_activity.set('Sport', sport)
            # Strange enough, according to TCX XSD the Id should be a date.
            # TODO verify if this is the case for Strava too or if something more meaningful can be passed.
            el_id = xml_et.SubElement(el_activity, 'Id')
            el_id.text = self.hi_activity.start.isoformat('T', 'seconds') + '.000Z'

            # Generate the activity xml content based on the type of activity
            if self.hi_activity.activity_type in [HiActivity.TYPE_WALK,
                                                HiActivity.TYPE_RUN,
                                                HiActivity.TYPE_CYCLE,
                                                HiActivity.TYPE_UNKNOWN]:
                self._generate_walk_run_cycle_xml_data(el_activity)
            elif self.hi_activity.activity_type == HiActivity.TYPE_SWIM:
                self._generate_swim_xml_data(el_activity)

            # *** Creator
            # TODO: verify if information is available in tar file
            el_creator = xml_et.SubElement(el_activity, 'Creator')
            el_creator.set('xsi:type', 'Device_t')
            el_name = xml_et.SubElement(el_creator, 'Name')
            el_name.text = 'Huawei Fitness Tracking Device'
            el_unit_id = xml_et.SubElement(el_creator, 'UnitId')
            el_unit_id.text = '0000000000'
            el_product_id = xml_et.SubElement(el_creator, 'ProductID')
            el_product_id.text = '0000'
            el_version = xml_et.SubElement(el_creator, 'Version')
            el_version_major = xml_et.SubElement(el_version, 'VersionMajor')
            el_version_major.text = '0'
            el_version_minor = xml_et.SubElement(el_version, 'VersionMinor')
            el_version_minor.text = '0'
            el_build_major = xml_et.SubElement(el_version, 'BuildMajor')
            el_build_major.text = '0'
            el_build_minor = xml_et.SubElement(el_version, 'BuildMinor')
            el_build_minor.text = '0'

            # * Author
            el_author = xml_et.SubElement(training_center_database, 'Author')
            el_author.set('xsi:type', 'Application_t')  # TODO verify if required/correct
            el_name = xml_et.SubElement(el_author, 'Name')
            el_name.text = PROGRAM_NAME
            el_build = xml_et.SubElement(el_author, 'Build')
            el_version = xml_et.SubElement(el_build, 'Version')
            el_version_major = xml_et.SubElement(el_version, 'VersionMajor')
            el_version_major.text = PROGRAM_MAJOR_VERSION
            el_version_minor = xml_et.SubElement(el_version, 'VersionMinor')
            el_version_minor.text = PROGRAM_MINOR_VERSION
            el_build_major = xml_et.SubElement(el_version, 'BuildMajor')
            el_build_major.text = PROGRAM_MAJOR_BUILD
            el_build_minor = xml_et.SubElement(el_version, 'BuildMinor')
            el_build_minor.text = PROGRAM_MINOR_BUILD
            el_lang_id = xml_et.SubElement(el_author, 'LangID')  # TODO verify if required/correct
            el_lang_id.text = 'en'
            el_part_number = xml_et.SubElement(el_author, 'PartNumber')  # TODO verify if required/correct
            el_part_number.text = '000-00000-00'

        except Exception as e:
            logging.error('Error generating TCX XML content for activity <%s>\n%s', self.hi_activity.activity_id, e)
            raise Exception('Error generating TCX XML content for activity <%s>\n%s', self.hi_activity.activity_id, e)

        self.training_center_database = training_center_database
        return training_center_database

    def _generate_walk_run_cycle_xml_data(self, el_activity):
        # **** Lap (a lap in the TCX XML corresponds to a segment in the HiActivity)
        for n, segment in enumerate(self.hi_activity.segment_list):
            el_lap = xml_et.SubElement(el_activity, 'Lap')
            el_lap.set('StartTime', segment['start'].isoformat('T', 'seconds') + '.000Z')
            el_total_time_seconds = xml_et.SubElement(el_lap, 'TotalTimeSeconds')
            el_total_time_seconds.text = str(segment['duration'])
            el_distance_meters = xml_et.SubElement(el_lap, 'DistanceMeters')
            el_distance_meters.text = str(segment['distance'])
            el_calories = xml_et.SubElement(el_lap, 'Calories')  # TODO verify if required/correct
            el_calories.text = '0'
            el_intensity = xml_et.SubElement(el_lap, 'Intensity')  # TODO verify if required/correct
            el_intensity.text = 'Active'
            el_trigger_method = xml_et.SubElement(el_lap, 'TriggerMethod')  # TODO verify if required/correct
            el_trigger_method.text = 'Manual'
            el_track = xml_et.SubElement(el_lap, 'Track')

            # ***** Track
            segment_data = self.hi_activity.get_segment_data(segment)
            for data in segment_data:
                el_trackpoint = xml_et.SubElement(el_track, 'Trackpoint')
                el_time = xml_et.SubElement(el_trackpoint, 'Time')
                el_time.text = data['t'].isoformat('T', 'seconds') + '.000Z'

                if 'lat' in data:
                    el_position = xml_et.SubElement(el_trackpoint, 'Position')
                    el_latitude_degrees = xml_et.SubElement(el_position, 'LatitudeDegrees')
                    el_latitude_degrees.text = str(data['lat'])
                    el_longitude_degrees = xml_et.SubElement(el_position, 'LongitudeDegrees')
                    el_longitude_degrees.text = str(data['lon'])

                if 'alti' in data:
                    el_altitude_meters = xml_et.SubElement(el_trackpoint, 'AltitudeMeters')
                    el_altitude_meters.text = str(data['alti'])

                if 'distance' in data:
                    el_distance_meters = xml_et.SubElement(el_trackpoint, 'DistanceMeters')
                    el_distance_meters.text = str(data['distance'])

                if 'hr' in data:
                    el_heart_rate_bpm = xml_et.SubElement(el_trackpoint, 'HeartRateBpm')
                    el_heart_rate_bpm.set('xsi:type', 'HeartRateInBeatsPerMinute_t')
                    value = xml_et.SubElement(el_heart_rate_bpm, 'Value')
                    value.text = str(data['hr'])

                if 's-r' in data:  # Step frequency (for walking and running)
                    if self.hi_activity.activity_type in (HiActivity.TYPE_WALK, HiActivity.TYPE_RUN):
                        el_extensions = xml_et.SubElement(el_trackpoint, 'Extensions')
                        el_tpx = xml_et.SubElement(el_extensions, 'TPX')
                        el_tpx.set('xmlns', 'http://www.garmin.com/xmlschemas/ActivityExtension/v2')
                        el_run_cadence = xml_et.SubElement(el_tpx, 'RunCadence')
                        # [Verified] Strava / TCX expects strides/minute (Strava displays steps/minute
                        # in activity overview). The HiTrack information is in steps/minute. Divide by 2 to have
                        # strides/minute in TCX.
                        el_run_cadence.text = str(int(data['s-r'] / 2))

    def _generate_swim_xml_data(self, el_activity):
        """ Generates the TCX XML content for POOL swimming activities """
        cumulative_distance = 0
        for n, lap in enumerate(self.hi_activity.get_swim_data()):
            el_lap = xml_et.SubElement(el_activity, 'Lap')
            el_lap.set('StartTime', lap['start'].isoformat('T', 'seconds') + '.000Z')
            el_total_time_seconds = xml_et.SubElement(el_lap, 'TotalTimeSeconds')
            el_total_time_seconds.text = str(lap['duration'])
            el_distance_meters = xml_et.SubElement(el_lap, 'DistanceMeters')
            el_distance_meters.text = str(lap['distance'])
            el_calories = xml_et.SubElement(el_lap, 'Calories')  # TODO verify if required/correct
            el_calories.text = '0'
            el_intensity = xml_et.SubElement(el_lap, 'Intensity')  # TODO verify if required/correct
            el_intensity.text = 'Active'
            el_trigger_method = xml_et.SubElement(el_lap, 'TriggerMethod')  # TODO verify if required/correct
            el_trigger_method.text = 'Manual'
            el_track = xml_et.SubElement(el_lap, 'Track')

            # Add first TrackPoint for start of lap
            el_trackpoint = xml_et.SubElement(el_track, 'Trackpoint')
            el_time = xml_et.SubElement(el_trackpoint, 'Time')
            el_time.text = lap['start'].isoformat('T', 'seconds') + '.000Z'
            el_distance_meters = xml_et.SubElement(el_trackpoint, 'DistanceMeters')
            el_distance_meters.text = str(cumulative_distance)

            # Add second TrackPoint for stop of lap
            cumulative_distance += lap['distance']

            el_trackpoint = xml_et.SubElement(el_track, 'Trackpoint')
            el_time = xml_et.SubElement(el_trackpoint, 'Time')
            el_time.text = lap['stop'].isoformat('T', 'seconds') + '.000Z'
            el_distance_meters = xml_et.SubElement(el_trackpoint, 'DistanceMeters')
            el_distance_meters.text = str(cumulative_distance)
        return

    def save(self, tcx_filename: str = None):
        if not self.training_center_database:
            # Call generation of TCX XML date if not already done
            self.generate_xml()

        # Format and save the TCX XML file
        if not tcx_filename:
            tcx_filename = self.save_dir + '/' + self.hi_activity.activity_id + '.tcx'
        try:
            logging.info('Saving TCX file <%s> for HiTrack activity <%s>', tcx_filename, self.hi_activity.activity_id)
            self._format_xml(self.training_center_database)
            xml_element_tree = xml_et.ElementTree(self.training_center_database)
            # If output directory doesn't exist, make it.
            if not os.path.exists(self.save_dir):
                os.makedirs(self.save_dir)
            # Save the TCX file
            with open(tcx_filename, 'wb') as tcx_file:
                tcx_file.write('<?xml version="1.0" encoding="UTF-8"?>'.encode('utf8'))
                xml_element_tree.write(tcx_file, 'utf-8')
        except Exception as e:
            logging.error('Error saving TCX file <%s> for HiTrack activity <%s> to file <%s>\n%s',
                          tcx_filename, self.hi_activity.activity_id, e)
            return
        finally:
            try:
                if tcx_file and not tcx_file.closed:
                    tcx_file.close()
                    logging.debug('TCX file <%s> closed', tcx_file.name)
            except Exception as e:
                logging.error('Error closing TCX file <%s>\n', tcx_file.name, e)

        # Validate the TCX XML file if option enabled
        if self.tcx_xml_schema:
            self._validate_xml(tcx_filename)

    def _format_xml(self, element: xml_et.Element, level: int = 0):
        """ Formats XML data by separating lines and adding whitespaces related to level for the XML element """
        indent_prefix = "\n" + level * "  "
        if len(element):
            if not element.text or not element.text.strip():
                element.text = indent_prefix + "  "
            if not element.tail or not element.tail.strip():
                element.tail = indent_prefix
            for element in element:
                self._format_xml(element, level + 1)
            if not element.tail or not element.tail.strip():
                element.tail = indent_prefix
        else:
            if level and (not element.tail or not element.tail.strip()):
                element.tail = indent_prefix

    def _validate_xml(self, tcx_xml_filename: str):
        """ Validates the generated TCX XML file against the Garmin TrainingCenterDatabase version 2 XSD """
        logging.info("Validating generated TCX XML file <%s> for activity <%s>", tcx_xml_filename,
                     self.hi_activity.activity_id)

        try:
            self.tcx_xml_schema.validate(tcx_xml_filename)
        except Exception as e:
            logging.error('Error validating TCX XML for activity <%s>\n%s', self.hi_activity.activity_id, e)
            raise Exception('Error validating TCX XML for activity <%s>\n%s', self.hi_activity.activity_id, e)


def _init_tcx_xml_schema() -> xmlschema:
    """ Retrieves the TCX XML XSD schema for validation of files from the intenet """

    _TCX_XSD_FILE = 'TrainingCenterDatabasev2.xsd'

    # Hold TCX XML schema in temporary directory
    with tempfile.TemporaryDirectory(PROGRAM_NAME) as tempdir:
        # Download and import schema to check against
        try:
            logging.info("Retrieving TCX XSD from the internet. Please wait.")
            url = 'https://www8.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd'
            url_req.urlretrieve(url, tempdir + '/' + _TCX_XSD_FILE)
        except:
            logging.warning('Unable to retrieve TCX XML XSD schema from the web. Validation will not be performed.')
            return None

        try:
            tcx_xml_schema = xmlschema.XMLSchema(tempdir + '/' + _TCX_XSD_FILE)
            return tcx_xml_schema
        except:
            logging.warning('Unable to initialize XSD xchema for TCX XML. Validation will not be performed.\n' +
                            'Is library xmlschema installed?')
            return None


def _convert_hitrack_timestamp(hitrack_timestamp: float) -> datetime:
    """ Converts the different timestamp formats appearing in HiTrack files to a Python datetime.

    Known formats are seconds (e.g. 1516273200 or 1.5162732E9) or microseconds (e.g. 1516273200000 or 1.5162732E12)
    """
    timestamp_digits = int(math.log10(hitrack_timestamp))
    if timestamp_digits == 9:
        return dts.utcfromtimestamp(int(hitrack_timestamp))

    divisor = 10 ** (timestamp_digits - 9) if timestamp_digits > 9 else 0.1 ** (9 - timestamp_digits)
    return dts.utcfromtimestamp(int(hitrack_timestamp / divisor))


def _init_logging(level: str = 'INFO'):
    """"
    Initializes the Python logging

    Parameters:
    level (int): Optional - The level to which the logger will be initialized.
        Use any of the available logging.LEVEL values.
        If not specified, the default level will be set to logging.INFO

    """

    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(funcName)s - %(message)s',
                        level=level)


def _init_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    file_group = parser.add_argument_group('FILE options')
    file_group.add_argument('-f', '--file', help='The filename of a single HiTrack file to convert.')
    file_group.add_argument('-s', '--sport', help='Force sport in the converted TCX XML file.', type=str,
                            choices=[HiActivity.TYPE_WALK,
                                     HiActivity.TYPE_RUN,
                                     HiActivity.TYPE_CYCLE,
                                     HiActivity.TYPE_SWIM])
    tar_group = parser.add_argument_group('TAR options')
    tar_group.add_argument('-t', '--tar', help='The filename of an (unencrypted) tarball with HiTrack files to \
                                                convert.')

    swim_group = parser.add_argument_group('SWIM options')
    def pool_length_type(arg):
        l = int(arg)
        if l < 1:
            raise argparse.ArgumentTypeError("Pool length must be an positive integer value.")
        if l == 1013:
            print('Congrats on your sim in the Alfonso del Mar.')
        return l
    swim_group.add_argument('--pool_length', help='The pool length in meters to use for swimming activities. \
                                                  If the option is not set, the estimated pool length derived from \
                                                  the available speed data in the HiTrack file will be used. Note \
                                                  that the available speed data has a minimum resolution of 1 dm/s.',
                            type=pool_length_type)

    def from_date_type(arg):
        try:
            return dts.strptime(arg, "%Y-%m-%d")
        except ValueError:
            msg = "Invalid date or date format (expected YYYY-MM-DD): '{0}'.".format(arg)
            raise argparse.ArgumentTypeError(msg)
    tar_group.add_argument('--from_date', help='Only convert HiTrack files in the tarball if the activity started on \
                                                FROM_DATE or later. Format YYYY-MM-DD',
                           type=from_date_type)
    parser.add_argument('--output_dir', help='The path to the directory to store the output files. The default \
                                             directory is ' + OUTPUT_DIR + '.',
                        default=OUTPUT_DIR)
    parser.add_argument('--validate_xml', help='Validate generated TCX XML file(s). NOTE: requires xmlschema library \
                                                and an internet connection to retrieve the TCX XSD.',
                        action='store_true')
    parser.add_argument('--log_level', help='Set the logging level.', type=str, choices=['INFO', 'DEBUG'],
                        default='INFO')

    return parser


def main():
    parser = _init_argument_parser()
    args = parser.parse_args()
    if args.log_level:
        _init_logging(args.log_level)
    else:
        _init_logging()

    logging.debug("%s version %s.%s (%s.%s) started with arguments %s", PROGRAM_NAME, PROGRAM_MAJOR_VERSION,
                  PROGRAM_MINOR_VERSION, PROGRAM_MAJOR_BUILD, PROGRAM_MINOR_BUILD, str(sys.argv[1:]))

    tcx_xml_schema = None if not args.validate_xml else _init_tcx_xml_schema()

    if args.file:
        hi_file = HiTrackFile(args.file)
        hi_activity = hi_file.parse()
        if args.sport:
            hi_activity.set_activity_type(args.sport)
        if args.pool_length and hi_activity.activity_type == HiActivity.TYPE_SWIM:
            hi_activity.set_pool_length(args.pool_length)
        tcx_activity = TcxActivity(hi_activity, tcx_xml_schema, args.output_dir)
        tcx_activity.save()
    elif args.tar:
        hi_tarball = HiTarBall(args.tar)
        if args.from_date:
            hi_activity_list = hi_tarball.parse(args.from_date)
        else:
            hi_activity_list = hi_tarball.parse()
        for hi_activity in hi_activity_list:
            if args.pool_length and hi_activity.activity_type == HiActivity.TYPE_SWIM:
                hi_activity.set_pool_length(args.pool_length)
            tcx_activity = TcxActivity(hi_activity, tcx_xml_schema, args.output_dir)
            tcx_activity.save()


if __name__ == '__main__':
    main()

