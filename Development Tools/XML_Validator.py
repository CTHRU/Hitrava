# XML_Validator

# Imports
import xmlschema
import urllib.request

# Download and import schema to check against
url = 'https://www8.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd'
urllib.request.urlretrieve(url, 'TrainingCenterDatabasev2.xsd')
schema = xmlschema.XMLSchema('TrainingCenterDatabasev2.xsd')

# Validate
schema.validate('1551547691000155155114800030001.tcx')
