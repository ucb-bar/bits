# Utils code

# Contributors:
# Joao Carreira <joao@eecs.berkeley.edu> (2015)

import os

def make_dir(mydir):
	if not os.path.exists(mydir):
                print "Creating " + mydir
    		os.makedirs(mydir)
        else:
                print "Directory " + mydir + " already exists"
