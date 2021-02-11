#!/usr/bin/env python3

# Hitrava.py
# Original Work Copyright (c) 2019 Ari Cooper-Davis / Christoph Vanthuyne - github.com/aricooperdavis/Huawei-TCX-Converter
# Modified Work Copyright (c) 2019-2020 Christoph Vanthuyne - https://github.com/CTHRU/Hitrava
# Released under the Non-Profit Open Software License version 3.0


import argparse
import collections
import csv
import datetime
import json
import logging
import math
import operator
import os
import platform
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile

import urllib.request as url_req
import xml.etree.cElementTree as xml_et
from datetime import datetime as dts
from datetime import timedelta as dts_delta
from datetime import timezone as tz
from zipfile import ZipFile as ZipFile

# External libraries that require installation
from typing import Optional

try:
    import xmlschema  # (only) needed to validate the generated TCX XML.
except:
    sys.stderr.write('Info - External library xmlschema could not be imported.\n' +
                     'It is required when using the --validate_xml argument.\n' +
                     'It can be installed using: pip install xmlschema\n')

if sys.version_info < (3, 5, 1):
    sys.stderr.write('You need Python 3.5.1 or later (you are using Python %s.%s.%s).\n' %
                     (sys.version_info.major,
                      sys.version_info.minor,
                      sys.version_info.micro))
    sys.exit(1)

# Global Constants
PROGRAM_NAME = 'Hitrava'
PROGRAM_MAJOR_VERSION = '4'
PROGRAM_MINOR_VERSION = '2'
PROGRAM_PATCH_VERSION = '0'
PROGRAM_MAJOR_BUILD = '2101'
PROGRAM_MINOR_BUILD = '1801'
PROGRAM_DAN67_BUILD = '20210211_work'

OUTPUT_DIR = './output'
GPS_TIMEOUT = dts_delta(seconds=10)


class HiActivity:
    """" This class represents all the data contained in a HiTrack file."""

    TYPE_WALK = 'Walk'
    TYPE_RUN = 'Run'
    TYPE_CYCLE = 'Cycle'
    TYPE_POOL_SWIM = 'Swim_Pool'
    TYPE_OPEN_WATER_SWIM = 'Swim_Open_Water'
    TYPE_HIKE = 'Hike'
    TYPE_MOUNTAIN_HIKE = 'Mountain_Hike'
    TYPE_INDOOR_RUN = 'Indoor_Run'
    TYPE_INDOOR_CYCLE = 'Indoor_Cycle'
    TYPE_CROSS_TRAINER = 'Cross_Trainer'
    TYPE_OTHER = 'Other'
    TYPE_CROSSFIT = 'CrossFit',
    TYPE_CROSS_COUNTRY_RUN = 'Cross_Country_Run'
    TYPE_UNKNOWN = '?'

    _ACTIVITY_TYPE_LIST = (TYPE_WALK, TYPE_RUN, TYPE_CYCLE, TYPE_POOL_SWIM, TYPE_OPEN_WATER_SWIM, TYPE_HIKE,
                           TYPE_MOUNTAIN_HIKE, TYPE_INDOOR_RUN, TYPE_INDOOR_CYCLE, TYPE_CROSS_TRAINER, TYPE_OTHER,
                           TYPE_CROSSFIT, TYPE_CROSS_COUNTRY_RUN)

    def __init__(self, activity_id: str, activity_type: str = TYPE_UNKNOWN):
        logging.getLogger(PROGRAM_NAME).debug('New HiTrack activity to process <%s>', activity_id)
        self.activity_id = activity_id

        if activity_type == self.TYPE_UNKNOWN:
            self._activity_type = self.TYPE_UNKNOWN
        else:
            self.set_activity_type(activity_type)  # validate and set activity type of the activity

        # Will hold a set of parameters to auto-determine activity type
        self.activity_params = {}

        self.pool_length = -1

        # All date and timestamp variables are stored as time zone unaware because there is no time zone information
        # available in the raw HiTrack files. However, time zone information is available from the JSON data and can be
        # stored as an attribute of the HiActivity (see below). Please take care to properly format any display/output
        # dates and times using this time zone information.
        self.start = None
        self.stop = None
        self.time_zone = None
        # Huawei Health provided distance or in absence the calculated distance derived from GPS data.
        self.distance = -1
        # Calculated distance derived from GPS data may differ from Huawei Health recorded distance
        self.calculated_distance = -1
        self.calories = -1

        # Create an empty segment and segment list
        self._current_segment = None
        self._segment_list = None

        # Create an empty detail data dictionary. key = timestamp, value = dict{t, lat, lon, alt, hr)
        self.data_dict = {}

        # Create an empty list for the (pool) swim data
        self.swim_data = []

        # Private variable to temporarily hold the last parsed SWOLF data during parsing of swimming activities
        self.last_swolf_data = None

    @classmethod
    def from_json_pool_swim_data(cls, activity_id: str, start: datetime, json_pool_swim_dict):
        """Create a HiActivity from the swim data in the JSON file.
        Uses the data in the mSwimSegments section of the JSON file (lap distance, duration, swolf)
        """
        if json_pool_swim_dict is None or len(json_pool_swim_dict) == 0:
            logging.getLogger(PROGRAM_NAME).warning('Swimming activity %s is empty (no segment data) and can not be ' +
                                                    'instantiated.', activity_id)
            return

        swim_activity = cls(activity_id, HiActivity.TYPE_POOL_SWIM)
        swim_activity.start = start

        # Parse lap data
        swim_activity.calculated_distance = 0
        lap_start = start
        for swim_segment in json_pool_swim_dict:
            # Create lap
            lap_distance = int(swim_segment['mDistance'])
            lap_duration = int(swim_segment['mDuration'])
            lap_stop = lap_start + dts_delta(seconds=lap_duration)
            lap_data = {'lap': int(swim_segment['mSegmentIndex']),
                        'start': lap_start,
                        'stop': lap_stop,
                        'duration': lap_duration,
                        'distance': lap_distance,
                        'swolf': int(swim_segment['mSwolf']),
                        'strokes': int(swim_segment['mPullTimes'])}

            swim_activity.swim_data.append(lap_data)
            swim_activity._add_segment_start(lap_start)
            swim_activity._add_segment_stop(lap_stop, lap_distance)
            swim_activity.calculated_distance += lap_distance
            swim_activity.stop = lap_stop
            lap_start = lap_stop

        return swim_activity

    def get_activity_type(self) -> str:
        if self._activity_type == self.TYPE_UNKNOWN:
            # Perform activity type detection only once.
            self._activity_type = self._detect_activity_type()
        return self._activity_type

    def set_activity_type(self, activity_type: str):
        if activity_type in self._ACTIVITY_TYPE_LIST:
            logging.getLogger(PROGRAM_NAME).info('Setting activity type of activity %s to %s',
                                                 self.activity_id, activity_type)
            self._activity_type = activity_type
        else:
            logging.getLogger(PROGRAM_NAME).error('Invalid activity type <%s>', activity_type)
            raise Exception('Invalid activity type <%s>', activity_type)

    def set_pool_length(self, pool_length: int):
        logging.getLogger(PROGRAM_NAME).info('Setting pool length of activity %s to %d', self.activity_id, pool_length)
        self.pool_length = pool_length
        if not self.get_activity_type() == self.TYPE_POOL_SWIM:
            logging.getLogger(PROGRAM_NAME).warning(
                'Pool length for activity %s of type %s will not be used. It is not a pool swimming activity',
                self.activity_id, self._activity_type)

    def _add_segment_start(self, segment_start: datetime):
        if self._current_segment:
            logging.getLogger(PROGRAM_NAME).error(
                'Request to start segment at %s when there is already a current segment active', segment_start)
            return

        logging.getLogger(PROGRAM_NAME).debug('Adding segment start at %s', segment_start)

        # No current segment, create one
        self._current_segment = {'start': segment_start, 'stop': None}
        # Add it to the segment list (note: if no explicit stop record is found, the segment will exist and stay 'open')
        if not self._segment_list:
            self._segment_list = []
        self._segment_list.append(self._current_segment)
        if not self.start:
            # Set activity start
            self.start = segment_start

    def _add_segment_stop(self, segment_stop: datetime, segment_distance: int = -1):
        logging.getLogger(PROGRAM_NAME).debug('Adding segment stop at %s', segment_stop)
        if not self._current_segment:
            logging.getLogger(PROGRAM_NAME).error(
                'Request to stop segment at %s when there is no current segment active', segment_stop)
            return

        # Set stop of current segment, add it to the segment list and clear the current segment
        self._current_segment['stop'] = segment_stop
        self._current_segment['duration'] = int((segment_stop - self._current_segment['start']).total_seconds())
        if not segment_distance == -1:
            self._current_segment['distance'] = segment_distance
        else:
            self._current_segment['distance'] = 0

        self._current_segment = None

    #  Verify if something useful can be done with the (optional) altitude data in the tp=lbs records
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
        - Location records are NOT ordered by timestamp when the activity contains loops of the same track.
        - Pause and stop records are identified by tp=lbs;lat=90;lon=-80;alt=0;t=<valid epoch time value or zero>
        """

        logging.getLogger(PROGRAM_NAME).debug('Adding location data %s', data)

        try:
            # Create a dictionary from the key value pairs
            location_data = dict(data)

            # All raw values are floats (timestamp will be converted later)
            for keys in location_data:
                location_data[keys] = float(location_data[keys])
        except Exception as e:
            logging.getLogger(PROGRAM_NAME).error(
                'One or more required data fields (t, lat, lon) missing or invalid in location data %s\n%s', data, e)
            raise Exception('One or more required data fields (t, lat, lon) missing or invalid in location data %s',
                            data)

        if location_data['t'] == 0 and location_data['lat'] == 90 and location_data['lon'] == -80:
            # Pause/stop record without a valid epoch timestamp. Set it to the last timestamp recorded
            location_data['t'] = self.stop
        else:
            # Regular location record or pause/stop record with valid epoch timestamp.
            # Convert the timestamp to a datetime
            location_data['t'] = _convert_hitrack_timestamp(location_data['t'])

            self.activity_params['gps'] = True

        # Only add location data with a valid timestamp (ignore GPS loss or pause records at start of the location data)
        if location_data['t']:
            self._add_data_detail(location_data)

    def _get_last_location(self) -> Optional[dict]:
        """ Returns the last location record in the data dictionary """
        if self.data_dict:
            reverse_sorted_data = sorted(self.data_dict.items(), key=operator.itemgetter(0), reverse=True)
            for t, data in reverse_sorted_data:
                if 'lat' in data:
                    return data
        # Empty data dictionary or no last location found in dictionary
        return None

    # TODO - Discovered on 18 Feb 2020 that this method is a 1:1 copy of the code in the vincenty 0.1.4 package on pypi.org (https://pypi.org/project/vincenty/)
    # TODO - Evaluate to either keep this method (facilitates easier install) versus import the vincenty 0.1.4 package
    def _vincenty(self, point1: tuple, point2: tuple) -> float:
        """
        Update 2020-02-18 - Discovered that this method is a 1:1 copy of the code in the vincenty 0.1.4 package
        on pypi.org (https://pypi.org/project/vincenty/) released under the Public Domain Unlicense license.

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
            logging.getLogger(PROGRAM_NAME).error('Failed to calculate distance between %s and %s', point1, point2)
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
        logging.getLogger(PROGRAM_NAME).debug('Adding heart rate data %s', data)

        try:
            hr_data = dict(data)
            # Use unique keys. Update keys k -> t and v -> hr
            hr_data['t'] = _convert_hitrack_timestamp(float(hr_data.pop('k')))
            hr_data['hr'] = int(hr_data.pop('v'))

            # Ignore invalid heart rate data (for export)
            if hr_data['hr'] < 1 or hr_data['hr'] > 254:
                logging.getLogger(PROGRAM_NAME).warning('Invalid heart rate data detected and ignored in data %s', data)
        except Exception as e:
            logging.getLogger(PROGRAM_NAME).error(
                'One or more required data fields (k, v) missing or invalid in heart rate data %s\n%s', data, e)
            raise Exception('One or more required data fields (k, v) missing or invalid in heart rate data %s\n%s',
                            data)

        # Add heart rate data
        self._add_data_detail(hr_data)

    def add_altitude_data(self, data: []):
        """Add altitude data from a tp=alti record in a HiTrack file"""
        # Create a dictionary from the key value pairs
        logging.getLogger(PROGRAM_NAME).debug('Adding altitude data %s', data)

        try:
            alti_data = dict(data)
            # Use unique keys. Update keys k -> t and v -> hr
            alti_data['t'] = _convert_hitrack_timestamp(float(alti_data.pop('k')))
            alti_data['alti'] = float(alti_data.pop('v'))

            # Ignore invalid altitude data
            if alti_data['alti'] < -1000 or alti_data['alti'] > 10000:
                logging.getLogger(PROGRAM_NAME).warning('Invalid altitude data detected and ignored in data %s', data)
                return

        except Exception as e:
            logging.getLogger(PROGRAM_NAME).error(
                'One or more required data fields (k, v) missing or invalid in altitude data %s\n%s', data, e)
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

        logging.getLogger(PROGRAM_NAME).debug(
            'Adding step frequency data or detecting cycling or swimming activities %s',
            data)

        try:
            # Create a dictionary from the key value pairs
            step_freq_data = dict(data)
            # Use unique keys. Update keys k -> t and v -> s_r
            step_freq_data['t'] = _convert_hitrack_timestamp(float(step_freq_data.pop('k')))
            step_freq_data['s-r'] = int(step_freq_data.pop('v'))
        except Exception as e:
            logging.getLogger(PROGRAM_NAME).error(
                'One or more required data fields (k, v) missing or invalid in step frequency data %s\n%s', data, e)
            raise Exception('One or more required data fields (k, v) missing or invalid in step frequency data %s\n%s',
                            data)

        # Keep track of minimum, maximum and average step frequency data for activity type auto-detection.
        # Ignore negative values since these belong to swimming activities and are not important to recognize the
        # swimming activity.
        if step_freq_data['s-r'] >= 0:
            if 'step frequency min' not in self.activity_params:
                self.activity_params['step frequency min'] = step_freq_data['s-r']
                self.activity_params['step frequency max'] = step_freq_data['s-r']
                self.activity_params['step frequency data'] = []
            elif step_freq_data['s-r'] < self.activity_params['step frequency min']:
                self.activity_params['step frequency min'] = step_freq_data['s-r']
            elif step_freq_data['s-r'] > self.activity_params['step frequency max']:
                self.activity_params['step frequency max'] = step_freq_data['s-r']

            # Add step frequency data detail to activity parameters for later average step frequency calculation.
            self.activity_params['step frequency data'].append(step_freq_data['s-r'])

        # Add step frequency data.
        self._add_data_detail(step_freq_data)

    def add_swolf_data(self, data: []):
        """ Add SWOLF (swimming) data from a tp=swf record in a HiTrack file
        SWOLF value = time to swim one pool length + number of strokes
        """

        logging.getLogger(PROGRAM_NAME).debug('Adding SWOLF swim data %s', data)

        try:
            # Create a dictionary from the key value pairs
            swolf_data = dict(data)

            # Ignore records (with relative timestamp) before at least 1 record with an absolute timestamp is processed.
            if not self.start:
                logging.getLogger(PROGRAM_NAME).warning('Ignored SWOLF record at relative time <%s> before first ' +
                                                        'record with absolute time.', swolf_data.pop('k'))
                return

            # Use unique keys. Update keys k -> t and v -> swf
            # Time of SWOLF swimming data is relative to activity start.
            # The first record with k=0 is the value registered after 5 seconds of activity.
            swolf_data['t'] = self.start + dts_delta(seconds=int(swolf_data.pop('k')) + 5)
            swolf_data['swf'] = int(swolf_data.pop('v'))

            self.activity_params['swim'] = True

            # If there is no last swf record or the last added swf record had a different swf value, then this record
            # belongs to a new lap (segment)
            # TODO There is a chance that checking on SWOLF only might miss a lap in case two consecutive laps have the same SWOLF (but then again, chances are that stroke and speed data are also identical)
            # TODO Since SWOLF value contains both time and strokes, add extra check to not process consecutive same time laps beyond the SWOLF value.
            if not self._current_segment:
                # First record of first lap. Start new segment (lap)
                self._add_segment_start(swolf_data['t'] - dts_delta(seconds=5))
            else:
                if self.last_swolf_data['swf'] != swolf_data['swf']:
                    # New lap detected.
                    # Close segment of previous lap. Since the current lap starts at the exact same time
                    self._current_segment['stop'] = self.last_swolf_data['t']
                    self._current_segment = None
                    # Open new segment for this lap. End of previous lap is start of current lap.
                    # Add 1 microsecond to split the lap data correctly.
                    self._add_segment_start(swolf_data['t'] + dts_delta(microseconds=1))

            # Remember this SWOLF data as last parsed SWOLF data.
            self.last_swolf_data = swolf_data
        except Exception as e:
            logging.getLogger(PROGRAM_NAME).error(
                'One or more required data fields (k, v) missing or invalid in SWOLF data %s\n%s', data, e)
            raise Exception('One or more required data fields (k, v) missing or invalid in SWOLF data %s\n%s', data)

        # Add SWOLF data
        self._add_data_detail(swolf_data)

    def add_stroke_frequency_data(self, data: []):
        """ Add stroke frequency (swimming) data (in strokes/minute) from a tp=p-f record in a HiTrack file """

        logging.getLogger(PROGRAM_NAME).debug('Adding stroke frequency swim data %s', data)

        try:
            # Create a dictionary from the key value pairs
            stroke_freq_data = dict(data)

            # Ignore records (with relative timestamp) before at least 1 record with an absolute timestamp is processed.
            if not self.start:
                logging.getLogger(PROGRAM_NAME).warning('Ignored stroke frequency record at relative time <%s> ' +
                                                        'before first record with absolute time.',
                                                        stroke_freq_data.pop('k'))
                return

            # Use unique keys. Update keys k -> t and v -> p-f
            # Time of stroke frequency swimming data is relative to activity start.
            # The first record with k=0 is the value registered after 5 seconds of activity.
            stroke_freq_data['t'] = self.start + dts_delta(seconds=int(stroke_freq_data.pop('k')) + 5)
            stroke_freq_data['p-f'] = int(stroke_freq_data.pop('v'))
        except Exception as e:
            logging.getLogger(PROGRAM_NAME).error(
                'One or more required data fields (k, v) missing or invalid in stroke frequency data %s\n%s', data, e)
            raise Exception(
                'One or more required data fields (k, v) missing or invalid in stroke frequency data %s\n%s', data)

        # Add stroke frequency data
        self._add_data_detail(stroke_freq_data)

    def add_speed_data(self, data: []):
        """ Add speed data (in decimeter/second) from a tp=rs record in a HiTrack file """

        logging.getLogger(PROGRAM_NAME).debug('Adding speed data %s', data)

        try:
            # Create a dictionary from the key value pairs
            speed_data = dict(data)

            # Ignore records (with relative timestamp) before at least 1 record with an absolute timestamp is processed.
            if not self.start:
                logging.getLogger(PROGRAM_NAME).warning('Ignored speed record at relative time <%s> before ' +
                                                        'first record with absolute time.', speed_data.pop('k'))
                return

            # Use unique keys. Update keys k -> t and v -> p-f
            # Time of speed data is relative to activity start.
            # The first record with k=0 is the value registered after 5 seconds of activity.
            speed_data['t'] = self.start + dts_delta(seconds=int(speed_data.pop('k')) + 5)
            speed_data['rs'] = float(speed_data.pop('v'))

            # Ignore invalid speed data records (negative speed value, e.g. for indoor (cycling) activities)
            if speed_data['rs'] < 0:
                return
        except Exception as e:
            logging.getLogger(PROGRAM_NAME).error(
                'One or more required data fields (k, v) missing or invalid in speed data %s\n%s', data, e)
            raise Exception('One or more required data fields (k, v) missing or invalid in speed data %s\n%s', data)

        # Add speed data
        self._add_data_detail(speed_data)

    def _add_data_detail(self, data: dict):
        # Add the data to the data dictionary.
        if data['t'] not in self.data_dict:
            # No data for timestamp. Create a new record for it.
            self.data_dict[data['t']] = data
        else:
            # Existing data for timestamp. Add the new data to the existing record.
            self.data_dict[data['t']].update(data)

        # Records are NOT necessarily in chronological order.
        # Update start of the activity when a record with an earlier timestamp is added.
        if not self.start or self.start > data['t']:
            self.start = data['t']
        # Update stop of the activity when a record with a later timestamp is added.
        if not self.stop or self.stop < data['t']:
            self.stop = data['t']

    def get_segments(self) -> list:
        """" Returns the segment list.
            - For swimming activities, the segments were identified during parsing of the SWOLF data.
            - For walking, running and cycling activities, the segments must be calculated once based on the parsed
              location data. Because the location data is not (always) in chronological order (e.g. loops in the track),
              for these activities
        """
        # Make sure calculation of segments is done.
        self._calc_segments_and_distances()
        return self._segment_list

    def _reset_segments(self):
        self._segment_list = None
        self._current_segment = None

    def _detect_activity_type(self) -> str:
        """"Auto-detection of the activity type. Only valid when called after all data has been parsed."""
        logging.getLogger(PROGRAM_NAME).debug('Detecting activity type for activity %s with parameters %s',
                                              self.activity_id, self.activity_params)

        # Filter out swimming
        if 'swim' in self.activity_params:
            # Swimming detected
            if 'gps' not in self.activity_params:
                self._activity_type = self.TYPE_POOL_SWIM
            else:
                self._activity_type = self.TYPE_OPEN_WATER_SWIM
            logging.getLogger(PROGRAM_NAME).debug('Activity type %s detected for activity %s',
                                                  self._activity_type, self.activity_id)
            return self._activity_type

        # Walk / Run / Cycle
        if 'step frequency min' in self.activity_params:
            # Walk / Run / Cycle - Step frequency data available
            # For walking and running, the assumption is that step frequency data is available regardless whether
            # a fitness tracking device is used or not.

            # Calculate average step frequency
            step_freq_sum = 0
            for n, step_freq in enumerate(self.activity_params['step frequency data']):
                step_freq_sum += step_freq

            step_freq_avg = step_freq_sum / (n + 1)
            logging.getLogger(PROGRAM_NAME).debug('Activity %s has a calculated average step frequency of %d',
                                                  self.activity_id, step_freq_avg)

            if self.activity_params['step frequency min'] == 0 and self.activity_params['step frequency max'] == 0:
                # Specific check for cycling - all step frequency records being zero
                self._activity_type = self.TYPE_CYCLE
            elif self.activity_params['step frequency min'] == 0 and step_freq_avg < 70:
                # TODO This condition will have to be confirmed in practice whether a long pause during walking would cause it to be detected as cycling

                # Some walking on foot during cycling activity - detect it as cycling
                # See https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5435734/ - Figure 2 extrapolated theoretical stride
                # frequency of 35 at speed 0.
                self._activity_type = self.TYPE_CYCLE
            elif self.activity_params['step frequency max'] < 135:
                # See https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5435734/ - Walk-to-run stride frequency of 70.6 +- 3.2
                self._activity_type = self.TYPE_WALK
            else:
                self._activity_type = self.TYPE_RUN

            logging.getLogger(PROGRAM_NAME).debug('Activity type %s detected using step frequency data for activity %s',
                                                  self._activity_type, self.activity_id)
            return self._activity_type
        else:
            # Walk / Run / Cycle - no step frequency data available (e.g. activities registered using phone only).
            # See above, since it is assumed that walking or running activities will always have step frequency records
            # regardless whether a fitness tracking device was used or not, this must be a cycling activity.
            self._activity_type = self.TYPE_CYCLE
            logging.getLogger(PROGRAM_NAME).debug('Activity type %s detected using step frequency data for activity %s',
                                                  self._activity_type, self.activity_id)
            return self._activity_type

    def _calc_segments_and_distances(self):
        """" Perform the following detailed data calculations for walk, run, or cycle activities:
        - segment list
        - segment start, stop, duration and cumulative distance
        - detailed track point cumulative distances
        - total distance

        Calculations change/add the following class attributes in place:
        - _segment_list
        - data_dict : sorted by timestamp and distances added
        - distance
        """

        # Calculate only once
        if self._segment_list:
            return

        logging.getLogger(PROGRAM_NAME).debug('Calculating segment and distance data for activity %s', self.activity_id)

        # Sort the data dictionary by timestamp
        self.data_dict = collections.OrderedDict(sorted(self.data_dict.items()))

        # Do calculations
        last_location = None
        paused = False
        segment_start_distance = 0

        # Start first segment at earliest data found while adding the data
        self._add_segment_start(self.start)

        for key, data in self.data_dict.items():
            if 'lat' in data:  # This is a location record
                if last_location:
                    if data['lat'] == 90 and data['lon'] == -80:
                        # Pause or stop records (lat = 90, long = -80, alt = 0) and handle segment data creation
                        # Use timestamp and distance of last (location) record
                        logging.getLogger(PROGRAM_NAME).debug('Start pause at %s in %s', data['t'], self.activity_id)
                        paused = True
                        self._add_segment_stop(last_location['t'], last_location['distance'] - segment_start_distance)
                    elif 'lat' not in last_location:
                        # GPS was lost and is now back. Set distance to last known distance and use this record as the
                        # last known location.
                        if paused:
                            logging.getLogger(PROGRAM_NAME).debug('Stop pause at %s in %s', data['t'], self.activity_id)
                            paused = False
                        logging.getLogger(PROGRAM_NAME).debug(
                            'GPS signal available at %s in %s. Calculating distance using location data.',
                            data['t'], self.activity_id)
                        data['distance'] = last_location['distance']
                        # If no current segment, create one
                        if not self._current_segment:
                            self._add_segment_start(data['t'])
                            segment_start_distance = last_location['distance']
                        last_location = data
                    else:
                        # Regular location record. If no current segment, create one
                        if not self._current_segment:
                            self._add_segment_start(data['t'])
                            segment_start_distance = last_location['distance']
                        if paused:
                            logging.getLogger(PROGRAM_NAME).debug('Stop pause at %s in %s', data['t'], self.activity_id)
                            paused = False
                        # Calculate and set the accumulative distance of the location record
                        data['distance'] = self._vincenty((last_location['lat'], last_location['lon']),
                                                          (data['lat'], data['lon'])) + last_location['distance']
                        last_location = data
                else:
                    # First location. Set distance 0
                    data['distance'] = 0
                    segment_start_distance = 0
                    last_location = data
            elif 'rs' in data:
                if last_location:
                    time_delta = data['t'] - last_location['t']
                    if not paused and ('lat' not in last_location or time_delta > GPS_TIMEOUT):
                        # GPS signal lost for more than the GPS timeout period. Calculate distance based on speed records
                        logging.getLogger(PROGRAM_NAME).debug(
                            'No GPS signal between %s and %s in %s. Calculating distance using speed data (%s dm/s)',
                            last_location['t'], data['t'], self.activity_id, data['rs'])
                        # If no current segment, create one
                        if not self._current_segment:
                            self._add_segment_start(data['t'])
                            segment_start_distance = last_location['distance']
                        data['distance'] = last_location['distance'] + (data['rs'] * time_delta.seconds / 10)
                        last_location = data
                else:
                    # No location records processed and speed record available = start without GPS or no GPS at all.
                    # Set distance 0
                    data['distance'] = 0
                    segment_start_distance = 0
                    last_location = data
            elif 'alti' in data:
                # Retain first altitude as start altitude parameter.
                # Only used in conjunction with --tcx_insert_altitude_data to insert altitude information in every record.
                if 'altitude start' not in self.activity_params:
                    self.activity_params['altitude start'] = data['alti']


        # Close last segment if it is still open
        if self._current_segment:
            # If the segment is open (no stop record for end of activity):
            # - Outdoor activities -> calculated distance data is available, use timestamp and distance of last location record.
            # - Indoor activities -> no calculated distance data available, use stop timestamp and total distance from the header information.
            if last_location:
                # Outdoor
                self._add_segment_stop(last_location['t'], last_location['distance'] - segment_start_distance)
            else:
                # Indoor
                self._add_segment_stop(self.stop, self.distance)

        # Set the total distance of the activity
        if last_location:
            # Outdoor
            self.calculated_distance = int(last_location['distance'])
        else:
            # Indoor
            self.calculated_distance = self.distance

        if self.distance < 0:
            if self.calculated_distance < 0:
                self.calculated_distance = 0
            self.distance = self.calculated_distance

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

    def get_swim_data(self) -> Optional[list]:
        if self.get_activity_type() == self.TYPE_POOL_SWIM:
            if self.swim_data:
                return self.swim_data
            else:
                return self._calc_pool_swim_data()
        elif self.get_activity_type() == self.TYPE_OPEN_WATER_SWIM:
            return self._get_open_water_swim_data()
        else:
            return None

    def _calc_pool_swim_data(self) -> list:
        """" Calculates the real swim (lap) data based on the raw parsed pool swim data
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
        logging.getLogger(PROGRAM_NAME).info('Calculating swim data for activity %s', self.activity_id)

        swim_data = []

        # Sort the data dictionary by timestamp
        self.data_dict = collections.OrderedDict(sorted(self.data_dict.items()))

        total_distance = 0

        for n, segment in enumerate(self._segment_list):
            segment_data = self.get_segment_data(segment)
            first_swf_index = 0
            while 'swf' not in segment_data[first_swf_index]:
                first_swf_index += 1
            first_lap_record = segment_data[first_swf_index]
            last_lap_record = segment_data[-1]

            # First record is after 5 s in lap
            raw_data_duration = (last_lap_record['t'] - first_lap_record['t']).total_seconds() + 5

            lap_data = {}
            lap_data['lap'] = n + 1
            lap_data['swolf'] = first_lap_record['swf']
            lap_data['strokes'] = round(
                first_lap_record['p-f'] * raw_data_duration / 60)  # Convert strokes/min -> strokes/lap
            lap_data['duration'] = lap_data['swolf'] - lap_data['strokes']  # Derive lap time from SWOLF - strokes
            if self.pool_length < 1:
                # Pool length not set. Derive estimated distance from raw speed data
                lap_data['speed'] = first_lap_record['rs'] / 10  # estimation in m/s
                lap_data['distance'] = lap_data['speed'] * lap_data['duration']
            else:
                lap_data['distance'] = self.pool_length
                lap_data['speed'] = self.pool_length / lap_data['duration']

            total_distance += lap_data['distance']

            # Start timestamp of lap
            if not swim_data:
                lap_data['start'] = self.start
            else:
                # Start of this lap is stop of previous lap
                lap_data['start'] = swim_data[-1]['stop']
            # Stop timestamp of lap
            lap_data['stop'] = lap_data['start'] + dts_delta(seconds=lap_data['duration'])

            logging.getLogger(PROGRAM_NAME).debug('Calculated swim data for lap %d : %s', n + 1, lap_data)

            swim_data.append(lap_data)

        # Update activity distance
        self.calculated_distance = total_distance
        if self.distance < 0:
            self.distance = self.calculated_distance

        return swim_data

    def _get_open_water_swim_data(self) -> list:
        """" Calculates the real swim (lap) data based on the raw parsed open water swim data"""
        logging.getLogger(PROGRAM_NAME).info('Calculating swim data for activity %s', self.activity_id)

        swim_data = []

        # Sort the data dictionary by timestamp
        self.data_dict = collections.OrderedDict(sorted(self.data_dict.items()))

        # The generated segment list based on the SWOLF data is unusable for open water swim activities.
        # Reset it and recalculate segments and distances based on the GPS location data.
        self._reset_segments()
        self._calc_segments_and_distances()

        # Create 1 large lap
        lap_data = {'lap': 1, 'start': self.start, 'stop': self.stop, 'duration': (self.stop - self.start).seconds,
                    'distance': self.distance}
        swim_data.append(lap_data)

        return swim_data

    def __repr__(self):
        # TODO verify timezone (un)aware display date / time
        to_string = self.__class__.__name__ + \
                    '\nID       : ' + self.activity_id + \
                    '\nType     : ' + self._activity_type + \
                    '\nDate     : ' + self.start.date().isoformat() + ' (YYYY-MM-DD)' + \
                    '\nDuration : ' + str(self.stop - self.start) + ' (H:MM:SS)' \
                                                                    '\nDistance : ' + str(
            self.calculated_distance) + 'm (Huawei: ' + str(self.distance) + ' m)'
        return to_string


class HiTrackFile:
    """The HiTrackFile class represents a single HiTrack file. It contains all file handling and parsing methods."""

    def __init__(self, hitrack_filename: str, activity_type: str = HiActivity.TYPE_UNKNOWN):
        # Validate the file parameter and (try to) open the file for reading
        if not hitrack_filename:
            logging.getLogger(PROGRAM_NAME).error('Parameter HiTrack filename is missing')

        try:
            self.hitrack_file = open(hitrack_filename, 'r')
        except Exception as e:
            logging.getLogger(PROGRAM_NAME).error('Error opening HiTrack file <%s>\n%s', hitrack_filename, e)
            raise Exception('Error opening HiTrack file <%s>', hitrack_filename)

        self.activity = None
        self.activity_type = activity_type

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

        logging.getLogger(PROGRAM_NAME).info('Parsing file <%s>', self.hitrack_file.name)

        # Create a new activity object for the file
        self.activity = HiActivity(os.path.basename(self.hitrack_file.name), self.activity_type)

        data_list = []
        line_number = 0
        line = ''

        try:
            csv_reader = csv.reader(self.hitrack_file, delimiter=';')
            for line_number, line in enumerate(csv_reader, start=1):
                data_list.clear()
                if line[0] == 'tp=lbs':  # Location line format: tp=lbs;k=_;lat=_;lon=_;alt=_;t=_
                    for data_index in [5, 2, 3]:  # Parse parameters t, lat, lon parameters (alt not parsed)
                        data_list.append(line[data_index].split('='))  # Parse values after the '=' character
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
            logging.getLogger(PROGRAM_NAME).error('Error parsing file <%s> at line <%d>\nCSV data: %s\n%s',
                                                  self.hitrack_file.name, line_number, line, e)
            raise Exception('Error parsing file <%s> at line <%d>\n%s', self.hitrack_file.name, line_number)

        finally:
            self._close_file()

        return self.activity

    def _close_file(self):
        try:
            if self.hitrack_file and not self.hitrack_file.closed:
                self.hitrack_file.close()
                logging.getLogger(PROGRAM_NAME).debug('HiTrack file <%s> closed', self.hitrack_file.name)
        except Exception as e:
            logging.getLogger(PROGRAM_NAME).error('Error closing HiTrack file <%s>\n', self.hitrack_file.name, e)

    def __del__(self):
        self._close_file()


class HiTarBall:
    _TAR_HITRACK_DIR = 'com.huawei.health/files'
    _HITRACK_FILE_START = 'HiTrack_'

    def __init__(self, tarball_filename: str, extract_dir: str = OUTPUT_DIR):
        # Validate the tarball file parameter
        if not tarball_filename:
            logging.getLogger(PROGRAM_NAME).error('Parameter HiHealth tarball filename is missing')

        try:
            self.tarball = tarfile.open(tarball_filename, 'r')
        except Exception as e:
            logging.getLogger(PROGRAM_NAME).error('Error opening tarball file <%s>\n%s', tarball_filename, e)
            raise Exception('Error opening tarball file <%s>', tarball_filename)

        self.extract_dir = extract_dir
        self.hi_activity_list = []

    def parse(self, from_date: datetime.date = datetime.date(1970, 1, 1)) -> list:
        try:
            # Look for HiTrack files in directory com.huawei.health/files in tarball
            for tar_info in self.tarball.getmembers():
                if tar_info.path.startswith(self._TAR_HITRACK_DIR) \
                        and os.path.basename(tar_info.path).startswith(self._HITRACK_FILE_START):
                    hitrack_filename = os.path.basename(tar_info.path)
                    logging.getLogger(PROGRAM_NAME).info('Found HiTrack file <%s> in tarball <%s>',
                                                         hitrack_filename, self.tarball.name)
                    if from_date:
                        # Is file from or later than start date parameter?
                        hitrack_file_date = _convert_hitrack_timestamp(
                            float(hitrack_filename[
                                  len(self._HITRACK_FILE_START):len(self._HITRACK_FILE_START) + 10])).date()
                        if hitrack_file_date >= from_date:
                            # Parse Hitrack file from tar ball
                            self._extract_and_parse_hitrack_file(tar_info)
                        else:
                            # TODO verify timezone (un)aware display date / time
                            logging.getLogger(PROGRAM_NAME).info(
                                'Skipped parsing HiTrack file <%s> being an activity from %s before %s (YYYYMMDD).',
                                hitrack_filename, hitrack_file_date.isoformat(), from_date.isoformat())
                    else:
                        # Parse HiTrack file from tar ball
                        self._extract_and_parse_hitrack_file(tar_info)
            return self.hi_activity_list
        except Exception as e:
            logging.getLogger(PROGRAM_NAME).error('Error parsing tarball <%s>\n%s', self.tarball.name, e)
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
            logging.getLogger(PROGRAM_NAME).error('Error parsing HiTrack file <%s> in tarball <%s>',
                                                  tar_info.path, self.tarball.name, e)

    def _close_tarball(self):
        try:
            if self.tarball:
                self.tarball.close()
                logging.getLogger(PROGRAM_NAME).debug('Tarball <%s> closed', self.tarball.name)
        except Exception as e:
            logging.getLogger(PROGRAM_NAME).error('Error closing tarball <%s>\n', self.tarball.name, e)

    def __del__(self):
        self._close_tarball()


class HiZip:
    @staticmethod
    def extract_json(zip_filename: str, output_dir: str = OUTPUT_DIR, password: str = None):
        _MOTION_PATH_JSON_FILENAME = 'data/Motion path detail data & description/motion path detail data.json'
        _MOTION_PATH_JSON_FILENAME_ALT = 'Motion path detail data & description/motion path detail data.json'
        _WINDOWS_UNZIP_CMD = '7za x -aoa "-o%s" -bb0 -bse0 -bsp2 "-p%s" -sccUTF-8 "%s" -- "%s"'
        _MACOS_UNZIP_CMD = 'unzip %s -P %s -d %s %s'

        if zipfile.is_zipfile(zip_filename):
            if password is not None:
                zip_json_filename = _MOTION_PATH_JSON_FILENAME_ALT
                if platform.system() == 'Windows':
                    unzip_cmd = _WINDOWS_UNZIP_CMD % (output_dir, password, zip_filename, zip_json_filename)
                elif platform.system() == 'Darwin':
                    unzip_cmd = _MACOS_UNZIP_CMD % (zip_filename, password, output_dir, zip_json_filename)
                else:
                    logging.getLogger(PROGRAM_NAME).error('Encrypted ZIP files not supported on platform %s',
                                                          platform.system());
                    raise NotImplementedError('Encrypted ZIP files not supported on platform %s', platform.system())
                completed_process = subprocess.run(unzip_cmd,
                                                   universal_newlines=True,
                                                   stderr=subprocess.STDOUT,
                                                   stdout=subprocess.PIPE)
                logging.getLogger(PROGRAM_NAME).info(completed_process.stdout)
                if completed_process.returncode != 0:
                    logging.getLogger(PROGRAM_NAME).error('Error extracting JSON file <%s> from encrypted ZIP file <%s>. Return code was %s',
                                                          zip_json_filename, zip_filename, completed_process.returncode)
                    raise Exception('Error extracting JSON file <%s> from encrypted ZIP file <%s>. Return code was %s',
                                    zip_json_filename, zip_filename, completed_process.returncode)
            else:
                with ZipFile(zip_filename, 'r', True) as hi_zip:
                    if _MOTION_PATH_JSON_FILENAME in hi_zip.namelist():
                        zip_json_filename = _MOTION_PATH_JSON_FILENAME
                    elif _MOTION_PATH_JSON_FILENAME_ALT in hi_zip.namelist():
                        zip_json_filename = _MOTION_PATH_JSON_FILENAME_ALT
                    else:
                        logging.getLogger(PROGRAM_NAME).warning('Could not find JSON file <%s> in ZIP file <%s>. \
                                                                Nothing to convert.',
                                                                _MOTION_PATH_JSON_FILENAME, zip_filename)
                        raise Exception('Could not find file <data/motion path detail data.json> in ZIP file <%s>. \
                                        Nothing to convert.', zip_filename)

                    try:
                        hi_zip.extract(zip_json_filename, output_dir)
                    except Exception as e:
                        logging.getLogger(PROGRAM_NAME).error('Error extracting JSON file <%s> from ZIP file <%s>\n%s',
                                                              zip_json_filename, zip_filename, e)
                        raise Exception('Error extracting JSON file <%s> from ZIP file <%s>',
                                        zip_json_filename, zip_filename)
            json_filename = output_dir + '/' + zip_json_filename
            return json_filename
        else:
            logging.getLogger(PROGRAM_NAME).error('Invalid ZIP file or ZIP file not found <%s>', zip_filename)
            raise Exception('Invalid ZIP file or ZIP file not found <%s>', zip_filename)


class HiJson:
    # TODO find the correct values for the unknown/undocumented JSON sport types
    # dan67 - sort by number
    _JSON_SPORT_TYPES = [(2, HiActivity.TYPE_MOUNTAIN_HIKE),
                         (3, HiActivity.TYPE_CYCLE),
                         (4, HiActivity.TYPE_RUN),
                         (5, HiActivity.TYPE_WALK),
                         (101, HiActivity.TYPE_INDOOR_RUN),
                         (102, HiActivity.TYPE_POOL_SWIM),
                         (103, HiActivity.TYPE_INDOOR_CYCLE),
                         (104, HiActivity.TYPE_OPEN_WATER_SWIM),
                         (111, HiActivity.TYPE_CROSS_TRAINER),
                         (117, HiActivity.TYPE_OTHER),
                         (118, HiActivity.TYPE_CROSS_COUNTRY_RUN),
                         (145, HiActivity.TYPE_CROSSFIT),
                         (282, HiActivity.TYPE_HIKE)
                         ]

    _UNSUPPORTED_JSON_SPORT_TYPES = []

    def __init__(self, json_filename: str, output_dir: str = OUTPUT_DIR, export_json_data: bool = False, export_json_summary: bool = False):
        # Validate the JSON file parameter
        if not json_filename:
            logging.getLogger(PROGRAM_NAME).error('Parameter for JSON filename is missing')

        try:
            self.json_file = open(json_filename, 'r')
        except Exception as e:
            logging.getLogger(PROGRAM_NAME).error('Error opening JSON file <%s>\n%s', json_filename, e)
            raise Exception('Error opening JSON file <%s>', json_filename)

        self.output_dir = output_dir
        # If output directory doesn't exist, make it.
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        self.export_json_data = export_json_data

        self.export_json_summary = export_json_summary

        self.hi_activity_list = []

    def parse(self, from_date: datetime.date = datetime.date(1970, 1, 1)) -> list:
        try:
            # Look for HiTrack information in JSON file

            # The JSON file from Huawei contains invalid formatting in the 'partTimeMap' data (missing double quotes
            # for the keys). For now, remove the invalid parts using a regular expression.
            json_string = self.json_file.read()

            json_string = re.sub('\"partTimeMap\"\:{(.*?)}\,', '', json_string)

            data = json.loads(json_string)

            # JSON data structure BEFORE 07/2020
            # data {list}
            #   00 {dict}
            #     motionPathData {list}
            #       0 {dict)
            #         sportType {int}
            #         attribute {str} 'HW_EXT_TRACK_DETAIL@is<HiTrack File Data>&&HW_EXT_TRACK_SIMPLIFY@is<Other Data>
            #       1 {dict)
            #         sportType {int}
            #         attribute {str} 'HW_EXT_TRACK_DETAIL@is<HiTrack File Data>&&HW_EXT_TRACK_SIMPLIFY@is<Other Data>
            #     recordDay {int} 'YYYYMMDD'
            #
            # JSON data structure AS OF 07/2020
            # data {list}
            #   0 {dict)
            #     sportType {int}
            #     attribute {str} 'HW_EXT_TRACK_DETAIL@is<HiTrack File Data>&&HW_EXT_TRACK_SIMPLIFY@is<Other Data>
            #   1 {dict)
            #     sportType {int}
            #     attribute {str} 'HW_EXT_TRACK_DETAIL@is<HiTrack File Data>&&HW_EXT_TRACK_SIMPLIFY@is<Other Data>
            n = -1
            for n, activity_dict in enumerate(data):
                if 'recordDay' in activity_dict:
                    activity_date = dts.strptime(str(activity_dict['recordDay']), "%Y%m%d").date()
                else:
                    activity_date = dts.utcfromtimestamp(activity_dict['startTime'] / 1000).date()

                if activity_date >= from_date:
                    logging.getLogger(PROGRAM_NAME).info(
                        'Found one or more activities in JSON at index %d to parse from %s (YYY-MM-DD)',
                        n, activity_date.isoformat())

                    if 'motionPathData' in activity_dict:
                        for motion_path_dict in activity_dict['motionPathData']:
                            hi_activity = self._parse_activity(motion_path_dict)
                            if hi_activity:
                                self.hi_activity_list.append(hi_activity)
                    else:
                        hi_activity = self._parse_activity(activity_dict)
                        if hi_activity:
                            self.hi_activity_list.append(hi_activity)

                else:
                    logging.getLogger(PROGRAM_NAME).info(
                        'Skipped parsing activity at index %d being an activity from %s before %s (YYYY-MM-DD).',
                        n, activity_date.isoformat(), from_date.isoformat())

            if n == -1:
                logging.getLogger(PROGRAM_NAME).info('No activities found to convert in JSON file <%s>',
                                                     self.json_file.name)
            return self.hi_activity_list
        except Exception as e:
            logging.getLogger(PROGRAM_NAME).error('Error parsing JSON file <%s>\n%s', self.json_file.name, e)
            raise Exception('Error parsing JSON file <%s>', self.json_file.name)


    def _parse_activity(self, activity_dict : dict) -> HiActivity:
        # Create a HiTrack file from the HiTrack data
        hitrack_data = activity_dict['attribute']
        # Strip prefix and suffix from raw HiTrack data
        hitrack_data = re.sub('HW_EXT_TRACK_DETAIL\@is', '', hitrack_data)
        hitrack_data = re.sub('\&\&HW_EXT_TRACK_SIMPLIFY\@is(.*)', '', hitrack_data, flags=re.DOTALL)

        # Get additional activity detail data
        activity_detail_data = activity_dict['attribute']
        activity_detail_data = re.sub('HW_EXT_TRACK_DETAIL\@is(.*)\&\&HW_EXT_TRACK_SIMPLIFY\@is',
                                      '', activity_detail_data, flags=re.DOTALL)
        activity_detail_dict = json.loads(activity_detail_data)

        # Get time zone
        time_zone_string = activity_dict['timeZone']
        time_zone_hours_offset = int(time_zone_string[:3])
        time_zone_minutes_offset = int(time_zone_string[3:])
        time_zone = tz(dts_delta(hours=time_zone_hours_offset,
                                 minutes=time_zone_minutes_offset))

        # Get start date and time in UTC
        activity_start = dts.utcfromtimestamp(activity_dict['startTime'] / 1000)

        # Save HiTrack data to HiTrack file
        hitrack_filename = "%s/HiTrack_%s" % \
                           (self.output_dir,
                            _get_tz_aware_datetime(activity_start, time_zone).strftime('%Y%m%d_%H%M%S')
                            )

        if self.export_json_data:
            # Save a copy of the JSON data of a single activity. Allows re-processing for debugging.
            json_filename = hitrack_filename + '.json'
            logging.getLogger(PROGRAM_NAME).info(
                'Exporting JSON data of activity from %s to file %s', activity_start, json_filename)
            try:
                with open(json_filename, 'w+') as json_file:
                    json_file.write('[')  # Encapsulate the exported JSON data in a list
                    json.dump(activity_dict, json_file)
                    json_file.write(']')
            except Exception as e:
                logging.getLogger(PROGRAM_NAME).error(
                    'Error exporting JSON data of activity from %s.\n%s', activity_start, e)
            finally:
                try:
                    if json_file:
                        json_file.close()
                except Exception as e:
                    logging.getLogger(PROGRAM_NAME).error('Error closing JSON export file <%s>\n%s',
                                                          json_filename, e)

        if self.export_json_summary:
            # Save aditional JSON data as summary of single activity.
            json_summary_filename = hitrack_filename + '_summary.txt'
            try:
                json_summary = open(json_summary_filename, 'w+')
                json_summary_data = self._generate_json_summary(activity_start,time_zone,activity_dict,activity_detail_dict)
                for item in json_summary_data:
                    json_summary.write("%s\n" % item)
            finally:
                try:
                    if json_summary:
                        json_summary.close()
                except Exception as e:
                    logging.getLogger(PROGRAM_NAME).error(
                        'Error saving json summary', activity_start, e)


        logging.getLogger(PROGRAM_NAME).info(
            'Saving activity from %s to HiTrack file %s for parsing', activity_start, hitrack_filename)
        try:
            hitrack_file = open(hitrack_filename, 'w+')
            hitrack_file.write(hitrack_data)
        except Exception as e:
            logging.getLogger(PROGRAM_NAME).error(
                'Error saving activity from %s to HiTrack file for parsing.\n%s', activity_start, e)
        finally:
            try:
                if hitrack_file:
                    hitrack_file.close()
            except Exception as e:
                logging.getLogger(PROGRAM_NAME).error('Error closing HiTrack file <%s>\n%s',
                                                      hitrack_filename, e)

        # Use activity attributes available in JSON data
        # Do NOT process unsupported sport types
        sport_type = activity_dict['sportType']
        if sport_type in self._UNSUPPORTED_JSON_SPORT_TYPES:
            logging.getLogger(PROGRAM_NAME).warning('Activity from %s has an unsupported '
                                                    'activity type %d and will NOT be converted.',
                                                    activity_start, sport_type)
            return

        # Sport type (internal HiActivity sport type)
        sport = HiActivity.TYPE_UNKNOWN
        if any(activity_dict['sportType'] in i for i in self._JSON_SPORT_TYPES):
            sport = \
                [item[1] for item in self._JSON_SPORT_TYPES if
                 item[0] == sport_type][0]

        # Parse the Huawei activity data
        if sport == HiActivity.TYPE_POOL_SWIM:
            # Pool swimming activity, parse the JSON data
            activity_id = os.path.basename(hitrack_filename)
            hi_activity = HiActivity.from_json_pool_swim_data(activity_id,
                                                              activity_start,
                                                              activity_detail_dict['mSwimSegments'])
            if hi_activity is None:
                logging.getLogger(PROGRAM_NAME).warning('Swimming activity %s has no swim segment data and can not ' +
                                                        'be converted.', activity_id)
                return
        else:
            # For all activities except pool swimming, parse the HiTrack file
            hitrack_file = HiTrackFile(hitrack_filename)
            hi_activity = hitrack_file.parse()
            if sport != HiActivity.TYPE_UNKNOWN:
                hi_activity.set_activity_type(sport)
            else:
                logging.getLogger(PROGRAM_NAME).warning('Activity %s from %s has an unknown activity '
                                                        'type %d. Conversion will be attempted but may '
                                                        'not work.',
                                                        os.path.basename(hitrack_filename),
                                                        activity_start,
                                                        sport_type)

        # Start date and time (in UTC)
        hi_activity.start = activity_start

        # Time zone - Use time zone from JSON activity data
        hi_activity.time_zone = time_zone

        # Stop date and time (in UTC) from duration
        hi_activity.stop = activity_start + dts_delta(milliseconds=activity_dict['totalTime'])

        # Total distance
        if 'totalDistance' in activity_detail_dict:
            hi_activity.distance = activity_detail_dict['totalDistance']

        # Total calories
        if 'totalCalories' in activity_detail_dict:
            hi_activity.calories = activity_detail_dict['totalCalories'] / 1000

        # Swimming pool length
        if 'wearSportData' in activity_detail_dict:
            if 'swim_pool_length' in activity_detail_dict['wearSportData']:
                hi_activity.set_pool_length(
                    activity_detail_dict['wearSportData']['swim_pool_length'] / 100)

        return hi_activity

    def _close_json(self):
        try:
            if self.json_file and not self.json_file.closed:
                self.json_file.close()
                logging.getLogger(PROGRAM_NAME).debug('JSON file <%s> closed', self.json_file.name)
        except Exception as e:
            logging.getLogger(PROGRAM_NAME).error('Error closing JSON file <%s>\n', self.json_file.name, e)

    def __del__(self):
        self._close_json()

    def _generate_json_summary(self, activity_start : str, time_zone : str, activity_dict : dict, activity_detail_dict : dict) -> list:
        # generate summary info from original JSON data

        self.json_summary_list = []

        self.json_summary_list.append("Date      : " + _get_tz_aware_datetime(activity_start, time_zone).strftime('%Y%m%d_%H%M%S'))
        self.json_summary_list.append("Activity  : " + str(activity_dict["sportType"]))
        # TODO add line with text sport type (I can not do it :-( )

        self.json_summary_list.append("Duration  : " + str(datetime.timedelta(seconds=activity_dict["totalTime"]/1000)))
        self.json_summary_list.append("Distance  : " + str(activity_dict["totalDistance"]))
        self.json_summary_list.append("Calories  : " + str(activity_dict["totalCalories"]))
        self.json_summary_list.append("HR avg    : " + str(activity_detail_dict["avgHeartRate"]))
        self.json_summary_list.append("HR max    : " + str(activity_detail_dict["maxHeartRate"]))
        self.json_summary_list.append("Pace avg  : " + str(datetime.timedelta(seconds=activity_detail_dict["avgPace"])))
        self.json_summary_list.append("Pace max  : " + str(datetime.timedelta(seconds=activity_detail_dict["bestPace"])))
        if activity_detail_dict["avgPace"] != 0:
            self.json_summary_list.append("Speed avg : " + str(round(3600 / activity_detail_dict["avgPace"], 2)))
        else:
            self.json_summary_list.append("Speed avg : ")
        if activity_detail_dict["bestPace"] != 0:
            self.json_summary_list.append("Speed max : " + str(round(3600 / activity_detail_dict["bestPace"], 2)))
        else:
            self.json_summary_list.append("Speed max : ")
        self.json_summary_list.append("Steps avg : " + str(activity_detail_dict["avgStepRate"]))
        self.json_summary_list.append("Steps max : " + str(activity_detail_dict["bestStepRate"]))
        self.json_summary_list.append("Steps tot : " + str(activity_dict["totalSteps"]))
        self.json_summary_list.append("Alt max   : " + str(activity_detail_dict["mMaxAlti"]))
        self.json_summary_list.append("Alt min   : " + str(activity_detail_dict["mMinAlti"]))
        self.json_summary_list.append("Ascend    : " + str(activity_detail_dict["mTotalDescent"] / 10))
        self.json_summary_list.append("Descend   : " + str(activity_detail_dict["creepingWave"] / 10))

        return self.json_summary_list


class TcxActivity:
    # Strava accepts following sports: walking, running, biking, swimming.
    # Note: TCX XSD only accepts Running, Biking, Other
    _SPORT_OTHER = 'Other'
    _TCX_SPORT_TYPES = [(HiActivity.TYPE_WALK, 'Running'),
                        (HiActivity.TYPE_RUN, 'Running'),
                        (HiActivity.TYPE_CYCLE, 'Biking'),
                        (HiActivity.TYPE_POOL_SWIM, _SPORT_OTHER),
                        (HiActivity.TYPE_OPEN_WATER_SWIM, _SPORT_OTHER),
                        (HiActivity.TYPE_HIKE, _SPORT_OTHER),
                        (HiActivity.TYPE_MOUNTAIN_HIKE, _SPORT_OTHER),
                        (HiActivity.TYPE_INDOOR_RUN, 'Running'),
                        (HiActivity.TYPE_INDOOR_CYCLE, 'Biking'),
                        (HiActivity.TYPE_CROSS_TRAINER, _SPORT_OTHER),
                        (HiActivity.TYPE_OTHER, _SPORT_OTHER),
                        (HiActivity.TYPE_CROSSFIT, _SPORT_OTHER),
                        (HiActivity.TYPE_UNKNOWN, _SPORT_OTHER),
                        (HiActivity.TYPE_CROSS_COUNTRY_RUN, 'Running')]

    # TODO Customize XSD schema in the _validate_xml() function to validate Strava sport types.
    # TODO Upload activities directly into Strava using Strava API
    _STRAVA_SPORT_TYPES = [(HiActivity.TYPE_WALK, 'walking'),
                           (HiActivity.TYPE_RUN, 'running'),
                           (HiActivity.TYPE_CYCLE, 'biking'),
                           (HiActivity.TYPE_POOL_SWIM, 'swimming'),
                           (HiActivity.TYPE_OPEN_WATER_SWIM, 'swimming'),
                           (HiActivity.TYPE_HIKE, 'hiking'),
                           (HiActivity.TYPE_MOUNTAIN_HIKE, 'hiking'),
                           (HiActivity.TYPE_INDOOR_RUN, 'running'), # Not recognized by Strava TCX upload, change activity type after upload manually to Virtual Run.
                           (HiActivity.TYPE_INDOOR_CYCLE, 'biking'), # Not recognized by Strava TCX upload, change activity type after upload manually to Virtual Ride.
                           (HiActivity.TYPE_CROSS_TRAINER, 'elliptical'), # Not recognized by Strava TCX upload, change activity type after upload manually to Elliptical.
                           (HiActivity.TYPE_OTHER, _SPORT_OTHER),
                           (HiActivity.TYPE_CROSSFIT, 'crossfit'), # Not recognzied by Strava TCX upload, chnage activity type after upload manually to Crossfit.
                           (HiActivity.TYPE_UNKNOWN, _SPORT_OTHER),
                           (HiActivity.TYPE_CROSS_COUNTRY_RUN, 'running')]

    def __init__(self, hi_activity: HiActivity, tcx_xml_schema=None, save_dir: str = OUTPUT_DIR,
                 filename_prefix: str = None, filename_suffix: str = None, insert_altitude: bool = False):
        if not hi_activity:
            logging.getLogger(PROGRAM_NAME).error("No valid HiTrack activity specified to construct TCX activity.")
            raise Exception("No valid HiTrack activity specified to construct TCX activity.")
        self.hi_activity = hi_activity
        self.training_center_database = None
        if tcx_xml_schema:
            self.tcx_xml_schema = tcx_xml_schema
        else:
            self.tcx_xml_schema = None
        self.save_dir = save_dir
        self.filename_prefix = filename_prefix
        self.tcx_filename = None
        self.filename_suffix = filename_suffix
        self.insert_altitude = insert_altitude

    def _get_sport(self):
        sport = ''

        try:
            if self.tcx_xml_schema:
                # Use TCX XML compliant sport types when XML validation is used
                sport = \
                    [item[1] for item in self._TCX_SPORT_TYPES if item[0] == self.hi_activity.get_activity_type()][
                        0]
            else:
                # Use Strava sport types when XML validation is NOT used
                sport = \
                    [item[1] for item in self._STRAVA_SPORT_TYPES if
                     item[0] == self.hi_activity.get_activity_type()][0]
        finally:
            if sport == '':
                logging.getLogger(PROGRAM_NAME).warning('Activity <%s> has an undetermined/unknown sport type.',
                                                        self.hi_activity.activity_id)
                sport = self._SPORT_OTHER

        return sport

    def generate_xml(self) -> xml_et.Element:
        """"Generates the TCX XML content."""
        logging.getLogger(PROGRAM_NAME).debug('Generating TCX XML data for activity %s', self.hi_activity.activity_id)
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
            sport = self._get_sport()
            el_activity.set('Sport', sport)

            # Strange enough, according to TCX XSD the Id should be a date.
            # TODO verify if this is the case for Strava too or if something more meaningful can be passed.
            el_id = xml_et.SubElement(el_activity, 'Id')
            el_id.text = _get_tz_aware_datetime(self.hi_activity.start, self.hi_activity.time_zone).isoformat('T')
            # Generate the activity xml content based on the type of activity
            if self.hi_activity.get_activity_type() in [HiActivity.TYPE_WALK,
                                                        HiActivity.TYPE_RUN,
                                                        HiActivity.TYPE_CYCLE,
                                                        HiActivity.TYPE_HIKE,
                                                        HiActivity.TYPE_MOUNTAIN_HIKE,
                                                        HiActivity.TYPE_INDOOR_RUN,
                                                        HiActivity.TYPE_INDOOR_CYCLE,
                                                        HiActivity.TYPE_CROSS_TRAINER,
                                                        HiActivity.TYPE_OTHER,
                                                        HiActivity.TYPE_CROSSFIT,
                                                        HiActivity.TYPE_CROSS_COUNTRY_RUN,
                                                        HiActivity.TYPE_UNKNOWN]:
                self._generate_walk_run_cycle_xml_data(el_activity)
            elif self.hi_activity.get_activity_type() in [HiActivity.TYPE_POOL_SWIM,
                                                          HiActivity.TYPE_OPEN_WATER_SWIM]:
                self._generate_swim_xml_data(el_activity)
            else:
                logging.getLogger(PROGRAM_NAME).warning('Activity %s of type %s has no explicit XML generation method. '
                                                        'Will attempt default XML generation method.',
                                                        self.hi_activity.activity_id,
                                                        self.hi_activity.get_activity_type())
                self._generate_walk_run_cycle_xml_data(el_activity)

            # *** Creator
            # TODO: verify if information is available in JSON file
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
            el_author.set('xsi:type', 'Application_t')
            el_name = xml_et.SubElement(el_author, 'Name')
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
            el_name.text = 'H%ctr%cv%c' % \
                           (chr(105), chr(97), chr(97))
        except Exception as e:
            logging.getLogger(PROGRAM_NAME).error('Error generating TCX XML content for activity <%s>\n%s',
                                                  self.hi_activity.activity_id, e)
            raise Exception('Error generating TCX XML content for activity <%s>\n%s', self.hi_activity.activity_id, e)

        self.training_center_database = training_center_database
        return training_center_database

    def _generate_walk_run_cycle_xml_data(self, el_activity):
        # **** Lap (a lap in the TCX XML corresponds to a segment in the HiActivity)
        for n, segment in enumerate(self.hi_activity.get_segments()):
            el_lap = self._generate_lap_header_xml_data(el_activity, segment)

            # ***** Track
            el_track = xml_et.SubElement(el_lap, 'Track')

            segment_data = self.hi_activity.get_segment_data(segment)
            if segment_data:
                last_altitude = -1000
                if 'altitude start' in self.hi_activity.activity_params:
                    last_altitude = self.hi_activity.activity_params['altitude start']

                for data in segment_data:
                    el_trackpoint = xml_et.SubElement(el_track, 'Trackpoint')
                    el_time = xml_et.SubElement(el_trackpoint, 'Time')
                    el_time.text = _get_tz_aware_datetime(data['t'], self.hi_activity.time_zone).isoformat('T')

                    if 'lat' in data:
                        el_position = xml_et.SubElement(el_trackpoint, 'Position')
                        el_latitude_degrees = xml_et.SubElement(el_position, 'LatitudeDegrees')
                        el_latitude_degrees.text = str(data['lat'])
                        el_longitude_degrees = xml_et.SubElement(el_position, 'LongitudeDegrees')
                        el_longitude_degrees.text = str(data['lon'])

                    if 'alti' in data:
                        el_altitude_meters = xml_et.SubElement(el_trackpoint, 'AltitudeMeters')
                        el_altitude_meters.text = str(data['alti'])
                        last_altitude = data['alti']
                    elif (self.insert_altitude and last_altitude != -1000):
                        el_altitude_meters = xml_et.SubElement(el_trackpoint, 'AltitudeMeters')
                        el_altitude_meters.text = str(last_altitude)

                    if 'distance' in data:
                        el_distance_meters = xml_et.SubElement(el_trackpoint, 'DistanceMeters')
                        el_distance_meters.text = str(data['distance'])

                    if 'hr' in data:
                        el_heart_rate_bpm = xml_et.SubElement(el_trackpoint, 'HeartRateBpm')
                        el_heart_rate_bpm.set('xsi:type', 'HeartRateInBeatsPerMinute_t')
                        value = xml_et.SubElement(el_heart_rate_bpm, 'Value')
                        value.text = str(data['hr'])

                    if 's-r' in data:  # Step frequency (for walking and running)
                        if self.hi_activity.get_activity_type() in (HiActivity.TYPE_WALK, HiActivity.TYPE_RUN,
                                                                    HiActivity.TYPE_HIKE, HiActivity.TYPE_MOUNTAIN_HIKE,
                                                                    HiActivity.TYPE_CROSS_COUNTRY_RUN):
                            el_extensions = xml_et.SubElement(el_trackpoint, 'Extensions')
                            el_tpx = xml_et.SubElement(el_extensions, 'TPX')
                            el_tpx.set('xmlns', 'http://www.garmin.com/xmlschemas/ActivityExtension/v2')
                            el_run_cadence = xml_et.SubElement(el_tpx, 'RunCadence')
                            # [Verified] Strava / TCX expects strides/minute (Strava displays steps/minute
                            # in activity overview). The HiTrack information is in steps/minute. Divide by 2 to have
                            # strides/minute in TCX.
                            el_run_cadence.text = str(int(data['s-r'] / 2))
            else:
                # No detailed segment data. Create two (dummy) trackpoints at start and stop time of segment.
                el_trackpoint = xml_et.SubElement(el_track, 'Trackpoint')
                el_time = xml_et.SubElement(el_trackpoint, 'Time')
                el_time.text = _get_tz_aware_datetime(segment['start'], self.hi_activity.time_zone).isoformat('T')
                el_distance_meters = xml_et.SubElement(el_trackpoint, 'DistanceMeters')
                el_distance_meters.text = '0'

                el_trackpoint = xml_et.SubElement(el_track, 'Trackpoint')
                el_time = xml_et.SubElement(el_trackpoint, 'Time')
                el_time.text = _get_tz_aware_datetime(segment['stop'], self.hi_activity.time_zone).isoformat('T')
                el_distance_meters = xml_et.SubElement(el_trackpoint, 'DistanceMeters')
                el_distance_meters.text = str(segment['distance'])

    def _generate_swim_xml_data(self, el_activity):
        """ Generates the TCX XML content for swimming activities """

        cumulative_distance = 0
        for n, lap in enumerate(self.hi_activity.get_swim_data()):
            el_lap = self._generate_lap_header_xml_data(el_activity, lap)
            el_track = xml_et.SubElement(el_lap, 'Track')

            # Add first TrackPoint for start of lap
            el_trackpoint = xml_et.SubElement(el_track, 'Trackpoint')
            el_time = xml_et.SubElement(el_trackpoint, 'Time')
            el_time.text = _get_tz_aware_datetime(lap['start'], self.hi_activity.time_zone).isoformat('T')
            el_distance_meters = xml_et.SubElement(el_trackpoint, 'DistanceMeters')
            el_distance_meters.text = str(cumulative_distance)

            # Add track points for heart rate, position and distance
            for i, lap_detail_data in enumerate(self.hi_activity.get_segment_data(self.hi_activity.get_segments()[n])):
                if 'hr' in lap_detail_data or 'lat' in lap_detail_data or 'distance' in lap_detail_data:
                    el_trackpoint = xml_et.SubElement(el_track, 'Trackpoint')
                    el_time = xml_et.SubElement(el_trackpoint, 'Time')
                    el_time.text = _get_tz_aware_datetime(lap_detail_data['t'],
                                                          self.hi_activity.time_zone).isoformat('T', 'seconds')

                # Add location records during lap (if any, only for open water swimming)
                if 'lat' in lap_detail_data:
                    el_position = xml_et.SubElement(el_trackpoint, 'Position')
                    el_latitude_degrees = xml_et.SubElement(el_position, 'LatitudeDegrees')
                    el_latitude_degrees.text = str(lap_detail_data['lat'])
                    el_longitude_degrees = xml_et.SubElement(el_position, 'LongitudeDegrees')
                    el_longitude_degrees.text = str(lap_detail_data['lon'])

                # Add heart rate records during lap
                if 'hr' in lap_detail_data:
                    el_heart_rate_bpm = xml_et.SubElement(el_trackpoint, 'HeartRateBpm')
                    el_heart_rate_bpm.set('xsi:type', 'HeartRateInBeatsPerMinute_t')
                    value = xml_et.SubElement(el_heart_rate_bpm, 'Value')
                    value.text = str(lap_detail_data['hr'])

                # Add distance records during lap (if any, only for open water swimming)
                if 'distance' in lap_detail_data:
                    el_distance_meters = xml_et.SubElement(el_trackpoint, 'DistanceMeters')
                    el_distance_meters.text = str(lap_detail_data['distance'])

            # Add second TrackPoint for stop of lap
            cumulative_distance += lap['distance']

            el_trackpoint = xml_et.SubElement(el_track, 'Trackpoint')
            el_time = xml_et.SubElement(el_trackpoint, 'Time')
            el_time.text = _get_tz_aware_datetime(lap['stop'], self.hi_activity.time_zone).isoformat('T')
            el_distance_meters = xml_et.SubElement(el_trackpoint, 'DistanceMeters')
            el_distance_meters.text = str(cumulative_distance)
        return

    def _generate_lap_header_xml_data(self, el_activity, segment) -> xml_et.Element:
        """ Generates the TCX XML lap header content part """
        el_lap = xml_et.SubElement(el_activity, 'Lap')
        el_lap.set('StartTime', _get_tz_aware_datetime(segment['start'], self.hi_activity.time_zone).isoformat('T'))
        el_total_time_seconds = xml_et.SubElement(el_lap, 'TotalTimeSeconds')
        el_total_time_seconds.text = str(segment['duration'])
        # Distance per segment. Use calculated distances. Although they may be off from the total distance provided
        # in the Huawei Health data, there is no straightforward way to derive the real distance per segment.
        el_distance_meters = xml_et.SubElement(el_lap, 'DistanceMeters')
        el_distance_meters.text = str(segment['distance'])
        # Calories per segment. Assume even calorie consumption over all segments and distribute calories
        # per segment based on the ratio segment distance / calculated total distance. For (indoor) activities
        # without distance information, use a duration based ratio.
        if self.hi_activity.calories > 0:
            if self.hi_activity.calculated_distance > 0 and segment['distance'] > 0:
                segment_calories = round(
                    self.hi_activity.calories * segment['distance'] / self.hi_activity.calculated_distance)
            else:
                total_duration = (self.hi_activity.stop - self.hi_activity.start).seconds
                segment_calories = round(self.hi_activity.calories * segment['duration'] / total_duration)
        else:
            segment_calories = 0
        el_calories = xml_et.SubElement(el_lap, 'Calories')
        el_calories.text = str(segment_calories)
        el_intensity = xml_et.SubElement(el_lap, 'Intensity')  # TODO verify if required/correct
        el_intensity.text = 'Active'
        el_trigger_method = xml_et.SubElement(el_lap, 'TriggerMethod')  # TODO verify if required/correct
        el_trigger_method.text = 'Manual'

        return el_lap

    def save(self, tcx_filename: str = None):
        if not self.training_center_database:
            # Call generation of TCX XML date if not already done
            self.generate_xml()

        # Format and save the TCX XML file
        if not tcx_filename:
            self.tcx_filename = self.save_dir + '/'
            if self.filename_prefix:
                # TODO verify timezone (un)aware display date / time
                self.tcx_filename += dts.strftime(self.hi_activity.start, self.filename_prefix)
            self.tcx_filename += self.hi_activity.activity_id
            if self.filename_suffix:
                self.tcx_filename += self.filename_suffix
            self.tcx_filename += '.tcx'
        else:
            self.tcx_filename = tcx_filename
        try:
            logging.getLogger(PROGRAM_NAME).info('Saving TCX file <%s> for HiTrack activity <%s>', self.tcx_filename,
                                                 self.hi_activity.activity_id)
            self._format_xml(self.training_center_database)
            xml_element_tree = xml_et.ElementTree(self.training_center_database)
            # If output directory doesn't exist, make it.
            if not os.path.exists(self.save_dir):
                os.makedirs(self.save_dir)
            # Save the TCX file
            with open(self.tcx_filename, 'wb') as tcx_file:
                tcx_file.write('<?xml version="1.0" encoding="UTF-8"?>'.encode('utf8'))
                xml_element_tree.write(tcx_file, 'utf-8')
        except Exception as e:
            logging.getLogger(PROGRAM_NAME).error(
                'Error saving TCX file <%s> for HiTrack activity <%s> to file <%s>\n%s',
                self.tcx_filename, self.hi_activity.activity_id, e)
            return
        finally:
            try:
                if tcx_file and not tcx_file.closed:
                    tcx_file.close()
                    logging.getLogger(PROGRAM_NAME).debug('TCX file <%s> closed', tcx_file.name)
            except Exception as e:
                logging.getLogger(PROGRAM_NAME).error('Error closing TCX file <%s>\n', tcx_file.name, e)

        # Validate the TCX XML file if option enabled
        if self.tcx_xml_schema:
            self._validate_xml(self.tcx_filename)

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
        logging.getLogger(PROGRAM_NAME).info("Validating generated TCX XML file <%s> for activity <%s>",
                                             tcx_xml_filename, self.hi_activity.activity_id)

        try:
            self.tcx_xml_schema.validate(tcx_xml_filename)
        except Exception as e:
            logging.getLogger(PROGRAM_NAME).error('Error validating TCX XML for activity <%s>\n%s',
                                                  self.hi_activity.activity_id, e)
            raise Exception('Error validating TCX XML for activity <%s>\n%s', self.hi_activity.activity_id, e)


def _init_tcx_xml_schema():
    """ Retrieves the TCX XML XSD schema for validation of files from the internet """

    _TCX_XSD_FILE = 'TrainingCenterDatabasev2.xsd'

    # Hold TCX XML schema in temporary directory
    with tempfile.TemporaryDirectory(PROGRAM_NAME) as tempdir:
        # Download and import schema to check against
        try:
            logging.getLogger(PROGRAM_NAME).info("Retrieving TCX XSD from the internet. Please wait.")
            url = 'https://www8.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd'
            url_req.urlretrieve(url, tempdir + '/' + _TCX_XSD_FILE)
        except:
            logging.getLogger(PROGRAM_NAME).warning(
                'Unable to retrieve TCX XML XSD schema from the web. Validation will not be performed.')
            return None

        try:
            tcx_xml_schema = xmlschema.XMLSchema(tempdir + '/' + _TCX_XSD_FILE)
            return tcx_xml_schema
        except NameError:
            logging.getLogger(PROGRAM_NAME).warning(
                'Unable to initialize XSD xchema for TCX XML. Validation will not be performed.\n' +
                'Is library xmlschema installed?')
            return None
        except Exception as e:
            logging.getLogger(PROGRAM_NAME).warning('TCX XML XSD schema was successfully retrieved from the web ' +
                                                    'but could not be initialized. Validation will not be performed. ' +
                                                    'The following exception occured: %s', e)


def _convert_hitrack_timestamp(hitrack_timestamp: float) -> datetime:
    """ Converts the different timestamp formats appearing in HiTrack files to a Python datetime.

    Known formats are seconds (e.g. 1516273200 or 1.5162732E9) or milliseconds (e.g. 1516273200000 or 1.5162732E12)
    """
    timestamp_digits = int(math.log10(hitrack_timestamp))
    if timestamp_digits == 9:
        return dts.utcfromtimestamp(int(hitrack_timestamp))

    divisor = 10 ** (timestamp_digits - 9) if timestamp_digits > 9 else 0.1 ** (9 - timestamp_digits)
    return dts.utcfromtimestamp(int(hitrack_timestamp / divisor))


def _get_tz_aware_datetime(naive_datetime: dts, time_zone: tz):
    """"All datetimes in the HiActivity are represented as UTC datetimes and are parsed as time zone unaware
    (naive) datetime objects. This method returns the equivalent time zone aware datetime representation using the
    time zone information of the HiTrack activity (if any). If the Hitrack activity has no time zone information,
    UTC (GMT) time zone is assumed.

    :param naive_datetime:
    :param time_zone:
    :type naive_datetime: datetime.datetime
    :type time_zone: datetime.timezone
    :return
    The (time zone) aware datetime corresponding to the naive datetime in the naive_datetime parameter
    """
    utc_datetime = dts.replace(naive_datetime, tzinfo=tz.utc)
    if time_zone:
        aware_datetime = utc_datetime.astimezone(time_zone)
    else:
        aware_datetime = utc_datetime

    return aware_datetime


def _init_logging(level: str = 'INFO'):
    """"
    Initializes the Python logging.getLogger(PROGRAM_NAME). A program specific Logger is created.

    Parameters:
    level (int): Optional - The level to which the logger will be initialized.
        Use any of the available logging.getLogger(PROGRAM_NAME).LEVEL values.
        If not specified, the default level will be set to logging.getLogger(PROGRAM_NAME).INFO

    """
    logger = logging.getLogger(PROGRAM_NAME)
    console = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(funcName)s - %(message)s')
    console.setFormatter(formatter)
    if level == 'INFO':
        logger.setLevel(logging.INFO)
    elif level == 'DEBUG':
        logger.setLevel(logging.DEBUG)
    logger.addHandler(console)
    logger.propagate = False


def _init_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    json_group = parser.add_argument_group('JSON options')
    json_group.add_argument('-z', '--zip', help='The filename of the Huawei Cloud ZIP file containing \
                                                 the JSON file with the motion path detail data to convert. \
                                                 The JSON file will be extracted to the directory in the --output_dir \
                                                 argument and conversion will be performed.')

    json_group.add_argument('-p', '--password', help='The password of the encrypted Huawei Cloud ZIP file. \
                                                     Required for encrypted ZIP files only.')

    json_group.add_argument('-j', '--json', help='The filename of a Huawei Cloud JSON file containing the motion path \
                                                  detail data to convert or the filename of the Huawei Cloud ZIP file \
                                                  containing the JSON file with the motion path detail data (this will \
                                                  work identical to --zip argument above).')

    json_group.add_argument('--json_export', help='Exports a file with the JSON data of each single activity that is \
                                                   converted from the JSON file in the --json argument. The file will \
                                                   be exported to the directory in the --output_dir argument with a \
                                                   .json file extension. The exported file can be reused in the \
                                                   --json argument to e.g. run the conversion again for the JSON \
                                                   activity or for debugging purposes.',
                            action='store_true')
    json_group.add_argument('--json_summary', help='Use data from JSON file, without recalculation',
                            action='store_true')

    file_group = parser.add_argument_group('FILE options')
    file_group.add_argument('-f', '--file', help='The filename of a single HiTrack file to convert.')
    file_group.add_argument('-s', '--sport', help='Force sport for the conversion. Sport will be auto-detected when \
                                                   this option is not used.', type=str,
                            choices=[HiActivity.TYPE_WALK,
                                     HiActivity.TYPE_RUN,
                                     HiActivity.TYPE_CYCLE,
                                     HiActivity.TYPE_POOL_SWIM,
                                     HiActivity.TYPE_OPEN_WATER_SWIM])

    tar_group = parser.add_argument_group('TAR options')
    tar_group.add_argument('-t', '--tar', help='The filename of an (unencrypted) tarball with HiTrack files to \
                                                convert.')

    date_group = parser.add_argument_group('DATE options')

    def from_date_type(arg):
        try:
            return dts.strptime(arg, '%Y-%m-%d').date()
        except ValueError:
            msg = "Invalid date or date format (expected YYYY-MM-DD): '{0}'.".format(arg)
            raise argparse.ArgumentTypeError(msg)

    date_group.add_argument('--from_date', help='Applicable to --json and --tar options only. Only convert HiTrack \
                                                 information from the JSON file or from HiTrack files in the tarball \
                                                 if the activity started on FROM_DATE or later. Format YYYY-MM-DD',
                            type=from_date_type,
                            default='1970-01-01')

    swim_group = parser.add_argument_group('SWIM options')

    def pool_length_type(arg):
        l = int(arg)
        if l < 1:
            raise argparse.ArgumentTypeError("Pool length must be an positive integer value.")
        if l == 1013:
            print('Congrats on your swim in the Alfonso del Mar.')
        return l

    swim_group.add_argument('--pool_length', help='The pool length in meters to use for swimming activities. \
                                                  If the option is not set, the estimated pool length derived from \
                                                  the available speed data in the HiTrack file will be used. Note \
                                                  that the available speed data has a minimum resolution of 1 dm/s.',
                            type=pool_length_type)

    tcx_group = parser.add_argument_group('TCX options')
    tcx_group.add_argument('--tcx_insert_altitude_data',
                           help='When an activity has altitude information, inserts the last known altitude in \
                              every track point of the generated TCX file.',
                           action='store_true')

    output_group = parser.add_argument_group('OUTPUT options')
    output_group.add_argument('--output_dir', help='The path to the directory to store the output files. The default \
                                             directory is ' + OUTPUT_DIR + '.',
                              default=OUTPUT_DIR)
    output_group.add_argument('--use_original_filename',
                              help='In single FILE or TAR mode, when using this option the converted TCX files will \
                              have the same filename as the original input file (except from the file extension).',
                              action='store_true')
    output_group.add_argument('--output_file_prefix',
                              help='Adds the strftime representation of this argument as a prefix to the generated \
                              TCX XML file(s). E.g. use %%Y-%%m-%%d- to add human readable year-month-day information \
                              in the name of the generated TCX file.',
                              type=str)
    output_group.add_argument('--suppress_output_file_sequence',
                              help='Suppresses the sequence number suffix in the filenames of converted TCX files when \
                              converting activities in ZIP or JSON mode.',
                              action='store_true')
    output_group.add_argument('--validate_xml', help='Validate generated TCX XML file(s). NOTE: requires xmlschema library \
                                                and an internet connection to retrieve the TCX XSD.',
                              action='store_true')
    parser.add_argument('--log_level', help='Set the logging level.', type=str, choices=['INFO', 'DEBUG'],
                        default='INFO')

    return parser


def main():
    parser = _init_argument_parser()
    args = parser.parse_args()
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        input('\nPress enter to exit.')
        sys.exit(2)
    if args.log_level:
        _init_logging(args.log_level)
    else:
        _init_logging()

    args_string = str(sys.argv[1:])
    args_string = re.sub("('--password', '\w*')|('-p', '\w*')", "'--password', '********'", args_string)
    logging.getLogger(PROGRAM_NAME).info("%s version %s.%s.%s (build %s.%s) started with arguments %s",
                                          PROGRAM_NAME,
                                          PROGRAM_MAJOR_VERSION,
                                          PROGRAM_MINOR_VERSION,
                                          PROGRAM_PATCH_VERSION,
                                          PROGRAM_MAJOR_BUILD,
                                          PROGRAM_MINOR_BUILD,
                                          args_string)
    logging.getLogger(PROGRAM_NAME).info("Running on Python version %s.%s.%s",
                                          sys.version_info[0],
                                          sys.version_info[1],
                                          sys.version_info[2])

    tcx_xml_schema = None if not args.validate_xml else _init_tcx_xml_schema()

    if not args.suppress_output_file_sequence:
        output_file_suffix_format = '_%03d'
    else:
        output_file_suffix_format = '%.0s'

    if args.file:
        if args.sport:
            hi_file = HiTrackFile(args.file, args.sport)
        else:
            hi_file = HiTrackFile(args.file)
        hi_activity = hi_file.parse()
        if args.pool_length:
            hi_activity.set_pool_length(args.pool_length)
        tcx_activity = TcxActivity(hi_activity, tcx_xml_schema, args.output_dir, args.output_file_prefix,
                                   args.tcx_insert_altitude_data)
        if args.use_original_filename:
            tcx_activity.save()
        else:
            tcx_filename = "%s/HiTrack_%s.tcx" % \
                           (args.output_dir,
                            _get_tz_aware_datetime(hi_activity.start, hi_activity.time_zone).strftime('%Y%m%d_%H%M%S'),
                            )
            tcx_activity.save(tcx_filename)
        logging.getLogger(PROGRAM_NAME).info('Converted %s', hi_activity)
    elif args.tar:
        hi_tarball = HiTarBall(args.tar)
        hi_activity_list = hi_tarball.parse(args.from_date)
        for n, hi_activity in enumerate(hi_activity_list, start=1):
            if args.pool_length:
                hi_activity.set_pool_length(args.pool_length)
            tcx_activity = TcxActivity(hi_activity, tcx_xml_schema, args.output_dir, args.output_file_prefix,
                                       args.tcx_insert_altitude_data)
            if args.use_original_filename:
                tcx_activity.save()
            else:
                output_file_suffix = output_file_suffix_format % (n % 1000)
                tcx_filename = "%s/HiTrack_%s%s.tcx" % \
                                   (args.output_dir,
                                    _get_tz_aware_datetime(hi_activity.start, hi_activity.time_zone).strftime('%Y%m%d_%H%M%S'),
                                    output_file_suffix
                                    )
                tcx_activity.save(tcx_filename)
            logging.getLogger(PROGRAM_NAME).info('Converted %s', hi_activity)
    elif args.json or args.zip:
        if args.zip:
            json_filename = HiZip.extract_json(args.zip, args.output_dir, args.password)
        elif args.json and zipfile.is_zipfile(args.json):
            json_filename = HiZip.extract_json(args.json, args.output_dir, args.password)
        else:
            json_filename = args.json
        hi_json = HiJson(json_filename, args.output_dir, args.json_export, args.json_summary)
        hi_activity_list = hi_json.parse(args.from_date)
        for n, hi_activity in enumerate(hi_activity_list, start=1):
            if args.pool_length:
                hi_activity.set_pool_length(args.pool_length)
            output_file_suffix = output_file_suffix_format % (n % 1000)
            tcx_activity = TcxActivity(hi_activity, tcx_xml_schema, args.output_dir, args.output_file_prefix,
                                       output_file_suffix, args.tcx_insert_altitude_data)
            tcx_activity.save()
            logging.getLogger(PROGRAM_NAME).info('Converted %s', hi_activity)


if __name__ == '__main__':
    main()
