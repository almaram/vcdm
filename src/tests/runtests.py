#!/usr/bin/python
import sys
# TODO: move the unit tests to the test package
sys.path.append('../vcdm')

from test_common import *
from test_clientsdk import *
import unittest 

if __name__ == '__main__':
    unittest.main()