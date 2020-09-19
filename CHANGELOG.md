# Hitrava Changelog

All notable changes to this project are documented in this file. 

## Release Notes
### Version 3.6.1 (build 2009.1901)
#### Solved Issues
- Conversion stopped with an error when an empty swim activity is encountered (0 distance and no swim segments).
A warning message is now logged for these activities and they are not converted. Closes #28.

### Version 3.6.0 (build 2009.1501)
#### New features and changes
- Added a new command line argument option _--tcx_insert_altitude_data_ that forcibly inserts the last known altitude 
information in every track point of the generated TCX file. You don't need it for Strava, and technically it is optional
data in the TCX specification, but it seems that some 3rd party TCX visualization tools seem to expect this to properly 
display altitude information. Closes #27.

#### Solved Issues
- Corrected a faulty log message stating no activities were found to convert when converting a single activity.

### Version 3.5.4 (build 2009.0201)
#### Solved Issues
- Legacy FILE and TAR options only: hitrava would stop with an error when generating the TCX files for indoor 
activities. Closes #24.

### Version 3.5.3 (build 2008.1801)
#### New features and changes
- Changed logging messages with startup parameters from debug to info and added python version info on which Hitrava
is running.
- Added an error message if the file in the --zip argument is an invalid ZIP file.
- Added an info message if the JSON data in the ZIP file contains no activities.
 
#### Solved Issues
- Conversion failed with an error when the Hitrack data starts with records with relative timestamps before the first
 record with an absolute timestamp could be processed. The issue is patched by ignoring these records. 
 The logging will show a warning that a relative time record has been ignored. Closes #22.

#### Known Limitations
- Related to issue #22: A potential issue remains when the order of the records in the Hitrack data deviates more and 
more from the chronological order. The conversion result could be off because data with relative timestamps would 
currently either be ignored or placed at a wrong absolute time. If you would see too many messages of ignored relative 
timestamp records, don't hesitate to file an issue.

### Version 3.5.2 (build 2008.0701)
#### Solved Issues
- Hitrava would crash when using the command line argument _--suppress_output_file_sequence_. Closes #19.

### Version 3.5.1 (build 2007.2901)
#### New features and changes
- FILE and TAR conversion: the filenames of the converted TCX files are now more readable (i.e. the same as for the
ones generated in ZIP or JSON mode: format _Hitrack_ISO timestamp_sequence.tcx_). If you want to retain the original 
filename, you can use the new command line argument _--use_original_filename_. Closes #18.
- Added 'Mountain Hike' ('Climb') to the list of supported sport types. It will be converted in Strava as 'Hike'. See 
also #2.

### Version 3.5.0 (build 2007.0801)
#### New features and changes
- ZIP conversion: added support for the new Huawei data format as of July, 7th in the ZIP/JSON data. Closes #16.

### Version 3.4.2 (build 2007.0601)
#### Solved Issues
- Corrected an error where parsing would error out for activities recorded on devices that provide speed values as 
numbers with a decimal fraction (e.g Band Pro devices). Closes #15.

### Version 3.4.1 (build 2006.2101)
#### Solved Issues
- Solved a bug where Hitrava would stop with an error when the activity has no calorie information. Closes #13.

### Version 3.4.0 (build 2006.1501)
#### New features and changes
- ZIP conversion: added support for sport types Indoor Cycle, Cross Trainer, Other and Cross Fit. Closes #12.

#### Solved Issues
- Calorie information for indoor run activities was missing in the converted TCX file (always zero).

#### Known Limitations
- The Strava upload functionality does not have the functionality to recognize all sport types. It is recommended to 
manually change the sport type after uploading for the following sport types (e.g. to allow Strava to display the 
heart rate information):
    - Indoor Run: is converted as regular Run. Manually change to Virtual Run.
    - Indoor Cycle: is converted as regular Run. Manually change to Virtual Ride.
    - Cross Trainer: Manually change to Elliptical.
    - Other: ?
    - Crossfit: Manually change to Crossfit.

### Version 3.3.2 (build 2005.1501)
#### Solved Issues
- ZIP conversion: conversion no longer stops with an error when an activity with an unknown activity type is 
encountered. This version will display a warning message when encountering such activities and will attempt conversion.
You are encouraged to check the conversion result of these activities and report any conversion errors that might occur. 
Closes #11. 

#### Known Limitations
- The following activity types are known to produce unreliable conversion data and will be skipped (for now):
    - Indoor Cycle
    - Cross Trainer
    - Other
    - CrossFit
     
### Version 3.3.1 (build 2005.0501)
#### New features and changes
- ZIP conversion: Added 3 digit sequence number suffix to the filenames of the converted TCX files. This allows for
easier manual selection per 25 (Strava upload limit) when uploading the file TCX files to Strava. Thank you for the
suggestion in #9. 
- ZIP conversion: Added a new command line argument _--suppress_output_file_sequence_ to suppress the sequence numbers 
in the TCX filenames.  

### Version 3.3.0 (build 2005.0201)
#### New features and changes
- ZIP conversion: Pool Swim activities are directly detected from the Huawei data.
- ZIP conversion: Pool Swim activities are converted directly from the specific Huawei data for this activity type, 
instead of the generic activity (HiTrack) data. This guarantees a 100% correct conversion of the pool swim data (the 
previous conversion method sometimes needed to rely on calculations).

#### Solved Issues
- ZIP conversion: The new method to convert Pool Swim activities ensures the 'division by zero' won't occur anymore.
 Closes #8.

#### Known Limitations
- Huawei might have made changes to / might not maintain the generic (HiTrack) data for Pool Swim activities. Users 
using the legacy HiTrack File or Tar conversion methods for Pool Swim activities, might notice differences in laps / 
times / distances or even get an error (see also #8). The legacy conversion method for swimming activities will no
longer be maintained. You are encouraged to use the ZIP or JSON conversion method for Pool Swim activities.

### Version 3.2.7 (build 2004.2301)
#### New features and changes
- ZIP conversion: added support for 'Indoor Run' activity types. Indoor Run activities are uploaded to Strava as regular
run activities (no specific activity type available for indoor run via file upload). Closes #7. 

#### Solved Issues
- ZIP conversion: the filename of all generated files now contains the time zone aware local time from when the activity
took place.

### Version 3.2.6 (build 2004.1801)
#### Solved Issues
- ZIP conversion: added support for the new folder structure of the Huawei Health ZIP files. See also #7. 
- ZIP and JSON conversion: solved an issue that caused Hitrava to error out for activities without a 'wearSportData' 
section. See also #7.  
- ZIP and JSON conversion: activities of known unsupported (JSON) activity types will be skipped instead of stopping
Hitrava with an error. A warning message is logged during parsing of the JSON data to inform you. See also #7. 

#### Known Limitations
- Activities with activity type '101' in the JSON data are currently (unknown and) unsupported.

### Version 3.2.5 (build 2004.1101)
#### New features and changes
- ZIP and JSON conversion: Running and hiking activity types are now directly detected from the Huawei data.
- Strava TCX: Hiking activities are generated with the corresponding Strava activity type. You don't need to 
manually adjust the activity type for hiking activities in Strava after upload. See also #2.

### Version 3.2.4 (build 2003.1101)
#### Solved issues
- Calories burned information was wrong for (non-swimming) activities with more than 1 segment/lap (e.g. when activity
was paused or GPS loss occurred during activity). For each subsequent segment/lap, the calories of all preceding 
segments were added again which caused a too high total calories burned value in Strava. Closes #5.
- Segment/Lap distance information was wrong for (non-swimming) activities with more than 1 segment/lap.(e.g. when activity
was paused or GPS loss occurred during activity). For each subsequent segment/lap, the distances of all preceding 
segments were added again which caused a wrong value in the _Lap_ overview in Strava. Closes #6.

#### Known Limitations
- Calories burned information is not available for swimming activities (need real-life data to code/test).

### Version 3.2.3 (build 2002.2901)
#### New features and changes
- Oops, made a mistake. Didn't think about the Swedish word for 'to strive' being a trademark.
The application has been gracefully renamed to Hitrava, a convenient abbreviation of h(uawe)i, tra(ck) and the last 2
characters of the Swedish word for 'to strive'.  
All application name references in text and code have been changed too. You will have to adapt your scripts to use the 
new application name, sorry for the inconvenience.  
- Changed the conversion procedure in the _README_ to use the direct ZIP conversion (requires less steps than the JSON 
conversion) and changed the _Run_Hitrava.cmd_ batch script accordingly. 
- Cleaned up some superfluous code and comments. Did a technical correction to a regexp in code.

#### Solved issues
- Removed erroneous 'test' logging message when program runs in debug mode.

### Version 3.2.2 (build 2002.2001)
#### New features and changes
- ZIP conversion: made ZIP conversion explicit with new -z or --zip arguments and in usage. JSON conversion with -j or
--json arguments also still checks for ZIP file and will extract JSON before starting conversion.

#### Solved issues
- ZIP conversion: the --output_dir argument was ignored when extracting the JSON file from the ZIP file.

#### Known Issues
- There seems to be a problem lately to properly initialize the TCX XSD schema when using the --validate_xml argument. 

### Version 3.2.1 (Build 2002.1801)
#### New features and changes
- Small code changes to make Hitrava compatible with Python versions 3.5.1 or above (was 3.7.3 or above).

### Version 3.2.0 (Build 2002.1501)
#### New features and changes
- JSON conversion: it is now possible to directly pass the ZIP file with the health data from Huawei in the --json 
argument. The program will extract the "motion path detail data.json" file and start conversion.
- Added Windows batch file Hitrava.cmd for quick execution of JSON conversion with default arguments. 

### Version 3.1.2 (Build 2002.1301)
#### New features and changes
- Changed program exit codes for wrong Python version (1) or no arguments (2) 
- Extended error logging related to the TCX XSD schema.
- Code optimization in TCX XML generation.

#### Solved issues
- Distance calculation for activities with pauses is corrected. Closes #3.

### Version 3.1.1 (Build 2002.1201)
#### New features and changes
- Added Python version check (minimum 3.7.3) and accompanying error message if used version doesn't comply.   
- The program can now be executed without typing 'python' at the beginning of the
command line. Added a wait message when Hitrava is run without arguments (from prompt or by double-clicking it) to
make sure the help information is displayed.
- Changed versioning (added patch to version number) to comply with Semantic Versioning.
- From this version onward, a Non-Profit Open Software License 3.0 (NPOSL-3.0) license applies to all new changes.

### Version 3.1 Build 2002.0101
#### New features and changes
- JSON conversion: new command line argument **--json_export** that exports a file with the JSON data of each single
  activity that is converted from the JSON file in the --json argument. The file will be exported to the directory in 
  the --output_dir argument with a .json file extension. The exported file can be reused in the --json argument to e.g. 
  run the conversion again for the JSON activity or for debugging purposes.

#### Solved issues
- Corrected a potential bug for activities with an unknown sport type.

### Version 3.0 Build 2001.2301
#### Solved issues
- INFO logging level now works again.

### Version 3.0 Build 2001.2001
#### New features and changes
- JSON conversion: Use calories burned information from Huawei Health data.

### Version 3.0 Build 2001.1301
#### New features and changes
- Display help message when no arguments are passed.

### Version 3.0 Build 1912.1902
#### New features and changes
- Refactored logging to use a program specific logger instead of the root logger for more reliable logging.
- Reformatted some logging messages to have clearer logging of dates / times.

### Version 3.0 Build 1912.1901
#### New features and changes
- JSON conversion now uses the following detailed information available in the JSON data:
    - Sport types for walking and cycling activities are automatically set (instead of being detected based on the HiTrack
    data).
    - All date and time information in the converted TCX files includes the time zone information of the
    local time when the activity took place.

#### Solved issues
- Conversion failed if HiTrack data started with a GPS loss / pause record.

#### Known Limitations
- We (currently) don't have the JSON sport type values for activity types other than walking or cycling. 

### Version 3.0 Build 1912.0301
#### New features and changes
- Generated TCX files now contain the Strava custom sport type when XML validation is NOT being used.
  Strava recognizes the correct sport type on import without the need to manually adjust it after import.
  
  NOTE: when using the --validate_xml option, TCX XML compliant sport types will be used as in previous versions.

#### Solved issues
- Script terminated with error when using --tar and --json options without --from_date option.
- Conversion failed with a division by zero error when there is only 1 valid step frequency record. 
- When there are multiple activities on the same date, only the first activity would be converted. 
    
### Version 3.0 Build 1910.0301
#### New features and changes
- It is now possible to (mass) convert activity data from the JSON file with the motion path detail data available in
  the Privacy Data zip file that you can request in the Huawei Health app. Use the new --json command line option and
  specify your extracted "motion path detail data.json" file.
  To be able to request your data in the Huawei Health app, a prerequisite is to have an enabled Huawei account in the app.
  To request your data, tap the "Me" button in the lower right-hand corner, then tap on your account name on top of 
  the screen. Next, tap on 'Privacy Center' (one but last option just above 'Settings'). You can now request ALL your
  Huawei Health app data in a zip file by tapping 'Request Your Data'. You will receive a mail with a link to download
  the zip file. Once downloaded, open the zip file and go to the "data/Motion path detail data & description" folder.
  Extract the file "motion path detail data.json" from the zip file. Use this file in the --json command line option.  
  This will generate both the original HiTrack files and the converted TCX files.

#### Known Limitations
- The JSON file from the Huawei Privacy export contains other interesting data and information which is currently not
  used (yet). 

### Version 2.3 Build 1909.2401
#### Solved issues
- Program would error out when trying to convert without the --validate_xml option when the xmlschema library wasn't 
  installed.

#### Known Limitations
- Since the latest version of Huawei Backup (10.0.0.360_OVE) and more importantly Huawei Health (10.0.0.533), the
  program is ( / might be) defunct in its current state. Last version of Huawei Health app seems to disallow
  backups through its properties. Huawei Backup release notes state that encryption of the backup is required.

### Version 2.3 Build 1909.1501
#### New features and changes
- Added **--output_file_prefix** command line argument option. You can now add the strftime representation of this argument 
   as a prefix to the generated TCX XML file(s). E.g. use %Y-%m-%d- to add human readable year-month-day information in 
   the name of the generated TCX file.
- Reworked auto-detection of activity types. This was needed for the detection and distinction between pool swimming 
   and open water swimming. Added internal auto-distinction between walking and running based on
   research in https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5435734. For validation purposes, both types will still be
   converted as 'Run' in the TCX file (for now) to comply with the Garmin TCX XSD.
- The --sport command line argument now disables auto-detection of the type of sport of the activity and also enforces 
   the selected type of sport for the conversion.
- The values of --sport command line argument have been changed. 'Swim' has been replaced by 'Swim_Pool' or 
   'Swim_Open_water'. Please adapt your script(s) or remove the command line argument and try the (improved) auto-detection.   
- Alpha support for open water swimming activities. Tested on a single activity file only. SWOLF and speed
   data were found to be unreliable / unusable. The conversion relies on the GPS data for this type of activity. We welcome
   your feedback if you have any problems or remarks using this feature. 

#### Solved issues
- Bug solved in swimming lap generation that could cause each lap to be generated twice (probably since V2.0 B1908.3101).
- Bug solved that could cause the --sport command line argument to get overruled by auto-detection.

#### Known Limitations
- Distance calculation during long(er) pause periods can be off due to continuing speed data records
  during the pause in the HiTrack file. If you suspect a converted activity to have a wrong distance, you can 
  try to recalculate the distance from the activity details screen in Strava for now.

### Version 2.2 Build 1909.0801
#### New features and changes
- Conversion of Walking, Running ad Cycling activities without any GPS data is supported. You can now convert 
  activities that were recorded using a fitness band only (that has no GPS) without using your phone during the 
  activity. Distance calculation is an estimated distance and may differ from the real distance because calculation is
  based on (average) speed data during a period of seconds (typically 5 seconds) with a resolution of 1 dm/s.

#### Solved issues
- Solved conversion error due to improper segment handling in some cases of GPS loss and/or pause.
- Solved potential conversion error due to improper distance calculation in case the HiTrack file would not contain 
  an explicit stop record.

#### Known Limitations
- Open water swimming activities were not and are not supported (yet).

### Version 2.1 Build 1909.0701
#### New features and changes
- More accurate distance calculation in case of GPS loss during an activity is now supported for walking, running and 
  cycling activities. The real-time speed data in the HiTrack file is used to determine the distance during GPS loss.

#### Known Limitations
- Walking, Running and Cycling activities without any GPS data at all can't be converted (yet) and the conversion will
  fail with an error. This might be related to the 0 m distance reported in pre-version 2. Possible use-case: 
  You use your fitness band (that has no GPS) without your phone during an activity. To be solved in a future update.

### Version 2.0 Build 1908.3101
#### Solved issues
- Solved issue causing only a part of the activity to be converted. It was detected in a case where the
  activity track contained multiple loops over the same track (and/or on some devices, the records in the HiTrack
  file are not in chronological order).

### Version 2.0 Build 1908.2901
#### New features and changes
- Changed the auto-detected activity type from 'Walk' to 'Run' for walking or running activities. Please note that the
  known limitation from the previous version still exists: no auto-distinction between walking and running activities,
  they both are detected as running activities.  

#### Solved issues
- Error parsing altitude data from tp=alti records in HiTrack file

### Version 2.0 Build 1908.2201
#### New features and changes
- Support for swimming activities

  In this version duration and distances are supported. SWOLF data is available 
  from the HiTrack files but is not exported (yet) since we don't have the information how to pass it in the TCX 
  format or if Strava supports it natively.
- Direct conversion from tarball

  It is now possible to convert activities directly from the tarball without the 
  need to extract them.
- Auto activity type detection

  Auto detection of running, cycling or swimming activities. There is no auto 
  distinction (yet) between walking and running activities. For now, walking activities will be detected as running. The 
  activity type can be changed in Strava directly after importing the file. 
- Extended program logging

  Ability to log only information messages or to have a more extensive debug logging.
- Restructured and new command line options
  
  This includes new options for direct tarball processing (--tar and 
    --from_date), file processing (--file), forcing the sport type (--sport), setting the pool length for swim
    activities (--pool_length) and general options to set the directory for extracted and converted files 
    (--output_dir), the logging detail (--log_level) and the optional validation of converted TCX XML files 
    (--validate_xml)   
- The source code underwent a restructuring to facilitate the new features. 

#### Solved issues
- Step frequency corrected. Strava displays steps/minute in app but reads the value in the imported file as 
strides/minute. As a consequence, imported step frequency information from previous versions was 2 times the real value.

#### Known Limitations
- Auto distinction between walking and running activities is not included in this version.
- For walking and swimming activities, in this version the correct sport type must be manually changed in Strava directly 
  after importing the TCX file.
- Distance calculation may be incorrect in this version when GPS signal is lost during a longer period or there is no
GPS signal at all.
- Due to the very nature of the available speed data (minimum resolution is 1 dm/s) for swimming activities, swimming
  distances are an estimation (unless the --pool_length option is used) and there might be a second difference in the
  actual lap times versus the ones shown in the Huawei Health app.
- There is no direct upload functionality to upload the converted activities to Strava in this version.
- This program is dependent on the availability of the temporary/intermediate 'HiTrack' files in the Huawei Health app.
- This program is dependent on the Huawei Backup to take an unencrypted backup of the Huawei Health app data.
- This program was not tested on Python versions prior to version 3.7.3
