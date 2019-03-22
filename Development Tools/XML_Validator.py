# XML_Validator
"""
    Pass this script any number of TCX files as command line arguments and it
    will validate them using the xmlschema package. Any invalid tcx files will
    print the reason for failing validation.

    ---------------------------------------------------------------------------
    $ XML_Validatory.py Valid_TCX.tcx Invalid_TCX.tcx
    >Valid_TCX.tcx
    >   Valid
    >Invalid_TCX.tcx
    >   Invalid:
    >       mismatched tag: line 61, column 48
"""

# Imports
import sys, tempfile, urllib.request, xmlschema

# Make temporary directory
with tempfile.TemporaryDirectory() as tempdir:
    # Download and import schema to check against
    url = 'https://www8.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd'
    urllib.request.urlretrieve(url, tempdir+'/TrainingCenterDatabasev2.xsd')
    schema = xmlschema.XMLSchema(tempdir+'/TrainingCenterDatabasev2.xsd')

# Validate files given in command line to validate
for argument in sys.argv[1:]:
    if argument[-4:] == '.tcx':
        print(argument)
        try:
            schema.validate(argument)
            print('\tValid')
        except Exception as e:
            print('\tInvalid: ', end='\n\t\t')
            print(e)
