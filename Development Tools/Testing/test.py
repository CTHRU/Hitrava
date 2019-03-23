# test.py
# Ari Cooper-Davis, 2019 - github.com/aricooperdavis/Huawei-TCX-Converter

"""
This script makes testing changes a little easier by running the converter for
three known example HiTrack files then comparing the output to the currently
accepted correct output.

Copy the Huawei-TCX-Converter.py file that is being tested to this directory and
run test.py
"""

# Import main function
import os, sys
converter = __import__('Huawei-TCX-Converter')

print('- Testing -')

# Write output to file
std_stdout = sys.stdout
sys.stdout = open('logfile', 'w')

# Loop over files calling the converter
files = ['HiTrack_1', 'HiTrack_2', 'HiTrack_3']
for file in files:

    sys.argv = ['', '-f', '-v', file]
    # Stop testing if the converter fails and report the error
    try:
        converter.main()
    except Exception as e:
        sys.stdout = std_stdout
        print('Conversion failed for '+file+': ')
        print('\t'+e)
        exit()
    # Delete tcx file once done
    os.remove(file+'.tcx')

# Print results
sys.stdout = std_stdout
with open('valid_logfile', 'r') as vlog:
    with open('logfile', 'r') as log:
        if vlog.read() == log.read():
            print('PASSED')
        else:
            print('FAILED - see logfile for details')
            exit()
os.remove('logfile')
