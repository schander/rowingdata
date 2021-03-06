#! /usr/bin/python
import rowingdata
from sys import argv

def main():
    readFile = argv[1]

    try:
	rowerFile = argv[2]
    except IndexError:
	rowerFile = "defaultrower.txt"

    rower = rowingdata.getrower(rowerFile)

    csvoutput = readFile+"_o.CSV"

    sc = rowingdata.speedcoachParser(readFile)
    sc.write_csv(csvoutput)

    res = rowingdata.rowingdata(csvoutput,rowtype="On-water",
				rower=rower)

    res.plotmeters_otw()

    print res.allstats()



    print "done "+readFile
