<img align="left" width="80" height="80" src="./Development Tools/icon.png" alt="Huawei TCX Converter icon">

# Huawei TCX Converter
A makeshift python tool that generates TCX files from Huawei HiTrack files.

Users of Huawei Watches/Bands sync their fitness data with the Huawei Health App. It is [notoriously difficult](https://uk.community.huawei.com/software-17/huawei-health-integration-with-other-services-1198/index3.html) to get the data out of this app, but [through some cunning](https://forum.xda-developers.com/smartwatch/huawei-watch/huawei-watch-gt-export-data-health-t3874330) you can find `HiTrack` files which seem to contain some run data. This program allows you to take these files and generate `.TCX` files for use in your tracking app of choice (e.g. Strava). The outputted `.TCX` files will contain timestamped GPS, altitude, heart-rate, and cadence data where available.

## How to get the HiTrack Files
- Open the Huawei Health app and open the exercise that you want to convert to view it's trajectory. This ensures that its HiTrack file is generated.

If you have a **rooted** phone you can simply navigate to: `data/data/com.huawei.health/files/` where you should find a number of files prefixed `HiTrack`.

If you have an **unrooted** phone then:
- Download the [Huawei Backup App](https://play.google.com/store/apps/details?id=com.huawei.KoBackup&hl=en_GB) onto your phone.
- Start a new **unencrypted** backup of the Huawei Health app data to your external storage (SD Card)
- Navigate to `Huawei/Backup/***/backupFiles/***/` and copy `com.huawei.health.tar` to your computer.
- Unzip the file and navigate to `com.huawei.health/files/` and you should should see a number of `HiTrack` files.

## How to use the Huawei TCX Converter
You need [`python 3`](https://www.python.org/downloads/) to use this tool.

Download the [Huawei TCX Converter](https://raw.githubusercontent.com/aricooperdavis/Huawei-TCX-Converter/master/Huawei-TCX-Converter.py) and save it as a Python script in the same folder as your HiTrack file.

The tool is run on the command line by passing it the name of your file as a command line argument.
Other command line arguments:
* `-v` - validate the final TCX file in order to check that the conversion has worked (requires [xmlschema](https://pypi.org/project/xmlschema/) and an internet connection to download the TCX schema to check against)
* `-f` - do not attempt to filter out any aberrant records (such as loss of GPS signal)
* `-b` - change sport to Biking

You can rename your HiTrack files if you wish, but for clarity in the examples below I leave mine exactly as I found it.

### Illustration
I have copied the `Huawei-TCX-Converter.py` file to the directory containing my HiTrack file (`HiTrack_1551732120000155173259000030001` ). Now I can run the tool as follows:

    python Huawei-TCX-Converter.py HiTrack_1551732120000155173259000030001 -f -v

This gives me the output:

    ---- Input File ----
    reading: OKAY
    filtering: OKAY
    processing gps: OKAY
    processing heart-rate/cadence: OKAY

    ---- Details ----
    sport: Running
    start: 2019-03-04 20:42:00
    duration: 00:07:49
    distance: 1700m

    ---- XML file ----
    generating: OKAY
    saving: OKAY
    validating: OKAY

I've included both the HiTrack file and the resultant TCX file in the Examples folder for you to have a go with. You can also [visualise the data online](https://www.mygpsfiles.com/app/#3gcQ1H3M).

### Next steps
Some users have recommended the [TCX Converter](http://www.tcxconverter.com/TCX_Converter/TCX_Converter_ENG.html) tool to add altitude data to your TCX files once they've been converted. This may overwrite altitude data extracted from your device, if it collects this.

## Comparison
This is an image of the GPS trace from the .tcx file. The command line output above also lists the start time as 2019-03-04 20:42:00, the distance as 1.70km, and the duration as 00:07:49.

![Map of example route](https://raw.githubusercontent.com/aricooperdavis/Huawei-TCX-Converter/master/Examples/Route.PNG)

For comparison, below is the data visable on the Huawei Health App. You can see that the distance is off by about 80m, and the duration off by 1 second, but the GPS trace is spot on.

![Huawei Health App example route](https://raw.githubusercontent.com/aricooperdavis/Huawei-TCX-Converter/master/Examples/Huawei_Health.png)

## Contributing
This is a very early alpha version of this tool, so please help me by making it better! There are some scripts in the Development Tools folder that I find useful for debugging. I'll accept any improvements, but if you're looking for inspiration you could start with this to-do list:
* ~~Remove reliance on using the original filename~~
* ~~Enable changing sport type from running (default) to biking~~
* ~~Read timestamped heart-rate, cadence, and altitude data where available~~
* ~~See if we really need to add the unused data elements (e.g. Calories) to the TCX (edit: we do as there is no minOccurs in the schema)~~
* Add a GUI to make life easier for users who aren't familiar with the command line
* Build for common platforms so that users don't need to install python independently (Android?)
* Work with API's (i.e. Strava/Garmin) for automating tcx upload
* Check that this works for files other than those generated using the Huawei Band 2 Pro:
  * Confirmed working on a [file from a Huawei Watch GT](https://forum.xda-developers.com/smartwatch/huawei-watch/huawei-watch-gt-export-data-health-t3874330#post79042345)
* Improve the distance measurement method (currently using [Viscenty's Formulae](https://en.wikipedia.org/wiki/Vincenty%27s_formulae))
* Try and work out what `tp=b-p-m` is
* Add interpolated heart-rate/pace/average speed data to each location element
* Work on splitting data into `Laps`/`Tracks` rather than shoving it all into one
* Try to call on an open API to get altitude data for location points that don't have it
* Inspect other files in `com.huawei.health` to see if we can get any more relevant data out of them
