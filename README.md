![HiToStrava](./images/HiToStrava_Logo_With_Name.png)
## Table of Contents
- [Introduction](#introduction)  
- [Installation](#installation)  
- [How To Covert](#how-to-convert-your-health-activities-and-import-them-in-strava)  
- [Usage](#usage)  
    - [Command Line Arguments](#command-line-arguments-overview)  
    - [Examples](#usage-examples)
- [Release Notes](#release-notes)  
- [Copyright and License](#copyright-and-license)

## Introduction
HiToStrava converts health activities registered using a Honor or Huawei activity tracker or smart watch in the 
[`Huawei Health`](https://play.google.com/store/apps/details?id=com.huawei.health) app into a file format that can be 
directly uploaded to [`Strava`](https://strava.com).

## Installation
### Requirements
To use HiToStrava, you need:
- [`Python 3.7.x`](https://www.python.org/downloads/) or higher.
    - Python 3.7.6 is the lowest recommended version (developed and tested on this version).
    - Python 3.5.1 is the lowest minimum required version (compatibility tested on this version). 
- A Huawei account to request your health data.

### Installation Procedure
#### Step 1 - Install Python
Only required if you don't have a (suitable) python installation on your system.
- Download the latest Python version for your operating system from the [`Python website`](https://www.python.org/downloads/).
- Run the Python installer (Windows) or follow the instructions for your operating system. 

#### Step 2 - Download and Extract HiToStrava
- Click the green **'Clone or Download'** button on the top of this page.
- A small 'Clone With HTTPS' window will open. Click the **'Download ZIP'** button.
- Save the _HiToStrava-master.zip_ file on your system.
- Extract all contents of the _HiToStrava-master.zip_ file to a location of your choice on your system.

## How to convert your health activities and import them in Strava
All users can use conversion from a **[JSON](#json-conversion-procedure)** file.  
For users with rooted phones, legacy **[file](#single-file-conversion-examples)** and 
**[tar](#tar-file-conversion-examples)** options are still available.

### JSON conversion procedure
Activities can be mass converted using the data from a JSON file that you can request in the Huawei Health app.

The procedure below assumes that you [installed HiToStrava](#installation) and are logged in with your Huawei account in
the Huawei Health app. If you don't have a Huawei account, you can create one in the app.  

#### Step 1 - Request your data in the Huawei Health app
- On your phone, open the Huawei Health app.
- Tap the **'Me'** button in the lower right-hand corner of the main screen.
- Now tap on your account name on top of the screen.
- Tap on **'Privacy Center'**. 
- Tap **'Request Your Data'**. 
- Select **'Health'** from the list. Confirm your selection and follow the in-app instructions.
- Wait for the mail from Huawei to arrive with a link to download the data (ZIP file). 

#### Step 2 - Download your requested data and extract the JSON file 
- In the mail from Huawei, click on the link to download your data and follow the instructions.
- Once downloaded, open the ZIP file and go to the _data/Motion path detail data & description_ folder.
- Extract the file _motion path detail data.json_ from the ZIP file to the installtion folder of HiToStrava. 

#### Step 3 - Convert the data with HiToStrava
- Open a Command Prompt (Windows) or Terminal (Linux / Mac OS) and change the directory to the installation folder of 
HiToStrava.

  >**Tip**: If you're on Windows and you're not familiar with the Command Prompt or just want to do a quick
  > conversion with default arguments, double-click the _Run_HiToStrava.cmd_ file in the installation folder of HiToStrava.                                                                                                                    
                                                                                                                                               
- In the Command Prompt, run HiToStrava.py with the --json command line argument. You can use the default example 
command below or [add / change command line arguments](#command-line-arguments-overview) as you need.
  ```
  HiToStrava.py --json "motion path detail data.json" --json_export
  ```
  The above command will generate both the original HiTrack files and the converted TCX files for ALL activities to the
  _output_ subfolder of the HiToStrava installation folder. In this folder:
  - Files without an extension are the Huawei HiTrack files which contain the raw unconverted data of an activity. 
  - Files with the _.json_ extension represent an exported copy of the JSON data of a single activity. 
  - Files with the **_.tcx_** extension are the **converted files** suitable for upload to Strava.

#### Step 4 - Upload your data to Strava
You can now go to the Strava website to import your data.
- Go to the **[`'Upload and Sync Your Activities'`](https://www.strava.com/upload/select)** page on Strava. 
- Log in with your Strava account. 
- Once logged in, use the **'Browse...'** button on the page and select the converted TCX files (with the _.tcx_ 
extension, up to 25 at once) to upload. 

## Usage
### Command Line Arguments Overview
```
usage: HiToStrava.py [-h] [-j JSON] [--json_export] [-f FILE]
                     [-s {Walk,Run,Cycle,Swim_Pool,Swim_Open_Water}] [-t TAR]
                     [--from_date FROM_DATE] [--pool_length POOL_LENGTH]
                     [--output_dir OUTPUT_DIR]
                     [--output_file_prefix OUTPUT_FILE_PREFIX]
                     [--validate_xml] [--log_level {INFO,DEBUG}]

optional arguments:
  -h, --help            show this help message and exit
  --log_level {INFO,DEBUG}
                        Set the logging level.

JSON options:
  -j JSON, --json JSON  The filename of a Huawei Cloud JSON file containing
                        the motion path detail data or the filename of the
                        Huawei Cloud ZIP file containing the JSON file with
                        the motion path detail data. In the latter case, the
                        JSON file will be extracted to the directory in the
                        --output_dir argument.
  --json_export         Exports a file with the JSON data of each single
                        activity that is converted from the JSON file in the
                        --json argument. The file will be exported to the
                        directory in the --output_dir argument with a .json
                        file extension. The exported file can be reused in the
                        --json argument to e.g. run the conversion again for
                        the JSON activity or for debugging purposes.

FILE options:
  -f FILE, --file FILE  The filename of a single HiTrack file to convert.
  -s {Walk,Run,Cycle,Swim_Pool,Swim_Open_Water}, --sport {Walk,Run,Cycle,Swim_Pool,Swim_Open_Water}
                        Force sport for the conversion. Sport will be auto-
                        detected when this option is not used.

TAR options:
  -t TAR, --tar TAR     The filename of an (unencrypted) tarball with HiTrack
                        files to convert.

DATE options:
  --from_date FROM_DATE
                        Applicable to --json and --tar options only. Only
                        convert HiTrack information from the JSON file or from
                        HiTrack files in the tarball if the activity started
                        on FROM_DATE or later. Format YYYY-MM-DD

SWIM options:
  --pool_length POOL_LENGTH
                        The pool length in meters to use for swimming
                        activities. If the option is not set, the estimated
                        pool length derived from the available speed data in
                        the HiTrack file will be used. Note that the available
                        speed data has a minimum resolution of 1 dm/s.

OUTPUT options:
  --output_dir OUTPUT_DIR
                        The path to the directory to store the output files.
                        The default directory is ./output.
  --output_file_prefix OUTPUT_FILE_PREFIX
                        Adds the strftime representation of this argument as a
                        prefix to the generated TCX XML file(s). E.g. use
                        %Y-%m-%d- to add human readable year-month-day
                        information in the name of the generated TCX file.
  --validate_xml        Validate generated TCX XML file(s). NOTE: requires
                        xmlschema library and an internet connection to
                        retrieve the TCX XSD.
```
                        
### Usage Examples
#### JSON file conversion example
Use the command below to convert all activities available in the motion path JSON file from the requested Huawei 
Privacy data that were started on October, 3rd, 2019 or later. Source HiTrack files and converted TCX files will be 
generated in folder ./my_output_dir/json 
```
 python HiToStrava.py --json "motion path detail data.json" --from_date 2019-10-03 --output_dir my_output_dir/json
```
Same as above, but also create an additional export file for each converted activity containing the raw JSON data of
that activity from the motion path JSON file.
``` 
python HiToStrava.py --json "motion path detail data.json" --json_export --from_date 2019-10-03 --output_dir my_output_dir/json
```

#### Single file conversion examples
The example below converts extracted file HiTrack_12345678901212345678912 to HiTrack_12345678901212345678912.tcx in 
the ./output directory
```
python HiToStrava.py --file HiTrack_12345678901212345678912
```
The next example converts extracted file HiTrack_12345678901212345678912 to HiTrack_12345678901212345678912.tcx in 
the ./my_output_dir directory. The program logging level is set to display debug messages. The converted file is 
validated against the TCX XSD schema (requires installed xmlschema library and an internet connection). 
```
python HiToStrava.py --file HiTrack_12345678901212345678912 --output_dir my_output_dir --validate_xml --log_level DEBUG
```
The following example converts an extracted file HiTrack_12345678901212345678912 to HiTrack_12345678901212345678912.tcx 
in the ./output directory and forces the sport to walking. 
```
python HiToStrava.py --file HiTrack_12345678901212345678912 --sport Walk
```
The next example converts an indoor swimming activity in an extracted file HiTrack_12345678901212345678912 to 
HiTrack_12345678901212345678912.tcx. The length of the pool in meters is specified to have a more accurate swimming data
calculation.  
```
python HiToStrava.py --file HiTrack_12345678901212345678912 --pool_length 25
```
 
#### Tar file conversion examples
The first example extracts and converts any HiTrack file found in tar file com.huawei.health.tar into the ./output 
directory. The output directory will contain both the extracted HiTrack file and the converted TCX XML file. 
```
python HiToStrava.py --tar com.huawei.health.tar
```
In the example below, only activities in the com.huawei.health.tar tarball that were started on August 20th, 2019 or 
later will be extracted and converted to the ./output directory.
```
python HiToStrava.py --tar com.huawei.health.tar --from_date 20190820
```
  
## Release Notes
The release notes of the latest release can be found below.  
For a full changelog of earlier versions, please look [`here`](./CHANGELOG.md).

### Version 3.2.1 (Build 2002.1801)
#### New features and changes
- Small code changes to make HiToStrava compatible with Python versions 3.5.1 or above (was 3.7.3 or above).

## Copyright and License
Original Work Copyright (c) 2019 Ari Cooper Davis, Christoph Vanthuyne  
Modified Work Copyright (c) 2019-2020 Christoph Vanthuyne

Licensed under the Non-Profit Open Software License version 3.0 from HiToStrava version 3.1.1 onward.  
Read the license information [`here`](./LICENSE.md).
