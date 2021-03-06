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

    tcxFile = readFile+".TCX"
    csvsummary = readFile+".CSV"
    csvoutput = readFile+"_o.CSV"

    tcx = rowingdata.TCXParser(tcxFile)
    tcx.write_csv(csvoutput,window_size=10)

    res = rowingdata.rowingdata(open(csvoutput),rowtype="On-water",
				rower=rower)

    res.plotmeters_otw()

    sumdata = rowingdata.summarydata(csvsummary)
    sumdata.shortstats()

    sumdata.allstats()




    print "done "+readFile
