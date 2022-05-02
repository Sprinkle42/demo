import os
import sys
import pickle

if len(sys.argv) < 2:
    print ("usage: python3 fsdb_read_record.py <fsdb_file>")
    sys.exit(1)

with open(sys.argv[1], 'rb') as db_file:
    d = pickle.load(db_file)
    root = os.path.basename(sys.argv[1])
    print ('Dependency of %s:' % root)
    for dep in sorted(list(d.keys())):
        print (dep)
