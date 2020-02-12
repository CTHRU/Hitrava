# HiToStrava
## Introduction
HiToStrava converts health activities registered using a Honor or Huawei activity tracker or smart watch in the 
[`Huawei Health`](https://play.google.com/store/apps/details?id=com.huawei.health) app into a file format that can be 
directly imported in Strava.

The activities are converted to Garmin TCX XML files which can be directly [`imported in Strava`](https://www.strava.com/upload/select). 

## How to convert your health activities and import them in Strava
All users can use conversion from a JSON file using the --json option. For users with rooted phones, legacy file and tar
options are still available.

You can get the required JSON file as follows.

Activities can be mass converted using the data from the JSON file with the motion path detail data available in the 
Privacy Data zip file that you can request in the Huawei Health app.

Use the new --json command line option and specify your extracted "motion path detail data.json" file.
To be able to request your data in the Huawei Health app, a prerequisite is to have an enabled Huawei account in the app.

To request your data:
- Tap the 'Me' button in the lower right-hand corner, then tap on your account name on top of 
the screen.
- Tap on 'Privacy Center' (one but last option just above 'Settings'). 
- Tap 'Request Your Data' You can now request ALL your Huawei Health app data in a zip file. 

You will receive a mail with a link to download the zip file. 
- Once downloaded, open the zip file and go to the "data/Motion path detail data & description" folder.
- Extract the file "motion path detail data.json" from the zip file. Use this file in the --json command line option.  
This will generate both the original HiTrack files and the converted TCX files.

You can now go to the Strava website to import your data.
- Go to the [`'Upload and Sync Your Activities'`](https://www.strava.com/upload/select) page. 
- Log in to your account. 
- Once logged in, use the 'Browse...' button on the page and select the converted TCX files (up to 25 at once) to 
import. 

## Requirements
- [`Python 3.7.3`](https://www.python.org/downloads/) or higher.
- A Huawei account to request your health data.

## Usage
### Command Line Arguments Overview
> usage: HiToStrava.py [-h] [-f FILE]
>                     [-s {Walk,Run,Cycle,Swim_Pool,Swim_Open_Water}] [-j JSON]
>                     [-t TAR] [--from_date FROM_DATE]
>                     [--pool_length POOL_LENGTH] [--output_dir OUTPUT_DIR]
>                     [--output_file_prefix OUTPUT_FILE_PREFIX]
>                     [--validate_xml] [--log_level {INFO,DEBUG}]
>
>optional arguments:
>>  -h, --help            show this help message and exit

>>  --log_level {INFO,DEBUG}
>>                        Set the logging level.

>FILE options:
>>  -f FILE, --file FILE  The filename of a single HiTrack file to convert.
>
>> -s {Walk,Run,Cycle,Swim_Pool,Swim_Open_Water}, --sport {Walk,Run,Cycle,Swim_Pool,Swim_Open_Water}
>>                        Force sport for the conversion. Sport will be auto-
>>                        detected when this option is not used.

>JSON options:
>>  -j JSON, --json JSON  The filename of a Huawei Cloud JSON file containing
>>                        the motion path detail data.

>>  --json_export         Exports a file with the JSON data of each single
>>                        activity that is converted from the JSON file in the
>>                        --json argument. The file will be exported to the
>>                        directory in the --output_dir argument with a .json
>>                        file extension. The exported file can be reused in the
>>                        --json argument to e.g. run the conversion again for
>>                        the JSON activity or for debugging purposes.

>TAR options:
>>  -t TAR, --tar TAR     The filename of an (unencrypted) tarball with HiTrack
>>                        files to convert.

>DATE options:
>>  --from_date FROM_DATE
>>                        Applicable to --json and --tar options only. Only
>>                        convert HiTrack information from the JSON file or from
>>                        HiTrack files in the tarball if the activity started
>>                        on FROM_DATE or later. Format YYYY-MM-DD

>SWIM options:
>>  --pool_length POOL_LENGTH
>>                        The pool length in meters to use for swimming
>>                        activities. If the option is not set, the estimated
>>                        pool length derived from the available speed data in
>>                        the HiTrack file will be used. Note that the available
>>                        speed data has a minimum resolution of 1 dm/s.

>OUTPUT options:
>>  --output_dir OUTPUT_DIR
>>                        The path to the directory to store the output files.
>>                        The default directory is ./output.

>>  --output_file_prefix OUTPUT_FILE_PREFIX
>>                        Adds the strftime representation of this argument as a
>>                        prefix to the generated TCX XML file(s). E.g. use
>>                        %Y-%m-%d- to add human readable year-month-day
>>                        information in the name of the generated TCX file.

>>  --validate_xml        Validate generated TCX XML file(s). NOTE: requires
>>                        xmlschema library and an internet connection to
>>                        retrieve the TCX XSD.
                        
### Usage Examples
#### JSON file conversion example
Use the command below to convert all activities available in the motion path JSON file from the requested Huawei 
Privacy data that were started on October, 3rd, 2019 or later. Source HiTrack files and converted TCX files will be 
generated in folder ./my_output_dir/json 
>python HiToStrava --json "motion path detail data.json" --from_date 2019-10-03 --output_dir my_output_dir/json

Same as above, but also create an additional export file for each converted activity containing the raw JSON data of
that activity from the motion path JSON file.
>python HiToStrava --json "motion path detail data.json" --json_export --from_date 2019-10-03 --output_dir my_output_dir/json

#### Single file conversion examples
The example below converts extracted file HiTrack_12345678901212345678912 to HiTrack_12345678901212345678912.tcx in 
the ./output directory

>python HiToStrava --file HiTrack_12345678901212345678912

The next example converts extracted file HiTrack_12345678901212345678912 to HiTrack_12345678901212345678912.tcx in 
the ./my_output_dir directory. The program logging level is set to display debug messages. The converted file is 
validated against the TCX XSD schema (requires installed xmlschema library and an internet connection). 

>python HiToStrava --file HiTrack_12345678901212345678912 --output_dir my_output_dir --validate_xml --log_level DEBUG

The following example converts an extracted file HiTrack_12345678901212345678912 to HiTrack_12345678901212345678912.tcx 
in the ./output directory and forces the sport to walking. 

>python HiToStrava --file HiTrack_12345678901212345678912 --sport Walk

The next example converts an indoor swimming activity in an extracted file HiTrack_12345678901212345678912 to 
HiTrack_12345678901212345678912.tcx. The length of the pool in meters is specified to have a more accurate swimming data
calculation.  

>python HiToStrava --file HiTrack_12345678901212345678912 --pool_length 25

#### Direct tar file conversion examples
The first example extracts and converts any HiTrack file found in tar file com.huawei.health.tar into the ./output 
directory. The output directory will contain both the extracted HiTrack file and the converted TCX XML file. 

>python HiToStrava --tar com.huawei.health.tar

In the example below, only activities in the com.huawei.health.tar tarball that were started on August 20th, 2019 or 
later will be extracted and converted to the ./output directory.

>python HiToStrava --tar com.huawei.health.tar --from_date 20190820
 
## Release Notes
The release notes of the latest release can be found below.  
For a full changelog of earlier version, please look [`here`](./CHANGELOG.md).

### Version 3.1.1 (Build 2002.1201)
#### New features and changes
- Added Python version check (minimum 3.7.3) and message if used version doesn't comply.   
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

## Copyright and License
Copyright (c) 2019 Ari Cooper Davis, Christoph Vanthuyne  
Copyright (C) 2019-2020 Christoph Vanthuyne

Read the license [`here`](./LICENSE).
