# HiToStrava Changelog

All notable changes to this project are documented in this file. 

## Release Notes
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
- Small code changes to make HiToStrava compatible with Python versions 3.5.1 or above (was 3.7.3 or above).

### Version 3.2.0 (Build 2002.1501)
#### New features and changes
- JSON conversion: it is now possible to directly pass the ZIP file with the health data from Huawei in the --json 
argument. The program will extract the "motion path detail data.json" file and start conversion.
- Added Windows batch file HiToStrava.cmd for quick execution of JSON conversion with default arguments. 

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
command line. Added a wait message when HiToStrava is run without arguments (from prompt or by double-clicking it) to
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
