import math
import numpy as np
import re
import time
import matplotlib
import iso8601
import os
import pickle
import pandas as pd
from pandas import Series,DataFrame
from dateutil import parser
import datetime
from lxml import objectify,etree
from fitparse import FitFile
import os
from pandas.core.indexing import IndexingError

from utils import *
import zipfile

# we're going to plot SI units - convert pound force to Newton
lbstoN = 4.44822

def clean_nan(x):
    for i in range(len(x)-1):
        if np.isnan(x[i+1]):
            if x[i+2]>x[i]:
                x[i+1] = 0.5*(x[i]+x[i+2])
            if x[i+2]<x[i]:
                x[i+1] = 0

    return x

def flexistrptime(inttime):
    
    try:
	t = datetime.datetime.strptime(inttime, "%H:%M:%S.%f")
    except ValueError:
	try:
	    t = datetime.datetime.strptime(inttime, "%M:%S")
	except ValueError:
            try:
	        t = datetime.datetime.strptime(inttime, "%H:%M:%S")
            except ValueError:
	        t = datetime.datetime.strptime(inttime, "%M:%S.%f")

    return t

def flexistrftime(t):
    h = t.hour
    m = t.minute
    s = t.second
    us = t.microsecond

    second = s+us/1.e6
    m = m+60*h
    string = "{m:0>2}:{s:0>4.1f}".format(
        m = m,
        s = s
        )

    return string

def get_file_type(f):
    fop = open(f,'r')
    extension = f[-3:].lower()
    if extension == 'csv':
	# get first and 7th line of file
	firstline = fop.readline()
	
	for i in range(3):
	    fourthline = fop.readline()

	for i in range(3):
	    seventhline = fop.readline()

	fop.close()

        if 'RowDate' in firstline:
            return 'rowprolog'
        
        if 'Concept2 Utility' in firstline:
            return 'c2log'

        if 'Concept2' in firstline:
            return 'c2log'
        
        if 'Avg Watts' in firstline:
            return 'c2log'
        
	if 'SpeedCoach GPS Pro' in fourthline:
	    return 'speedcoach2'

	if 'Practice Elapsed Time (s)' in firstline:
	    return 'mystery'

        if 'Club' in firstline:
            return 'boatcoach'
        
        if 'peak_force_pos' in firstline:
            return 'rowperfect3'
        
	if 'Hair' in seventhline:
	    return 'rp'

	if 'Total elapsed time (s)' in firstline:
	    return 'ergstick'

	if 'Stroke Number' in firstline:
	    return 'ergdata'

	if ' DriveTime (ms)' in firstline:
	    return 'csv'

        if 'ElapsedTime (sec)' in firstline:
            return 'csv'

	if 'HR' in firstline and 'Interval' in firstline and 'Avg HR' not in firstline:
	    return 'speedcoach'

	if 'stroke.REVISION' in firstline:
	    return 'painsleddesktop'

    if extension == 'tcx':
	try:
	    tree = objectify.parse(f)
	    rt = tree.getroot()
	except:
	    return 'unknown'

	if 'HeartRateBpm' in etree.tostring(rt):
	    return 'tcx'
	else:
	    return 'tcxnohr'

    if extension =='fit':
	try:
	    FitFile(f,check_crc=False).parse()
	except:
	    return 'unknown'

	return 'fit'

    if extension == 'zip':
        try:
            z = zipfile.ZipFile(f)
            f2 = z.extract(z.namelist()[0])
            tp = get_file_type(f2)
            os.remove(f2)
            return 'zip',f2,tp
        except:
            return 'unknown'
    
    return 'unknown'
	

def get_file_line(linenr,f):
    fop = open(f,'r')
    for i in range(linenr):
	line = fop.readline()

    fop.close()
    return line


def skip_variable_footer(f):
    counter = 0
    counter2 = 0

    fop = open(f,'r')
    for line in fop:
	if line.startswith('Type') and counter>15:
	    counter2 = counter
	    counter += 1
	else:
	    counter += 1

    fop.close()
    return counter-counter2+1

def get_rowpro_footer(f,converters={}):
    counter = 0
    counter2 = 0

    fop = open(f,'r')
    for line in fop:
	if line.startswith('Type') and counter>15:
	    counter2 = counter
	    counter += 1
	else:
	    counter += 1

    fop.close()
    
    return pd.read_csv(f,skiprows=counter2,
		       converters=converters,
		       engine='python',
		       sep=None,index_col=False)
    

def skip_variable_header(f):
    counter = 0
    summaryc = -2
    fop = open(f,'r')
    for line in fop:
        if line.startswith('Interval Summaries'):
            summaryc = counter
	if line.startswith('Session Detail Data') or line.startswith('Per-Stroke Data'):
	    counter2 = counter
	else:
	    counter +=1

    fop.close()
    return counter2+2,summaryc+2

def make_cumvalues_array(xvalues):
    """ Takes a Pandas dataframe with one column as input value.
    Tries to create a cumulative series.
    
    """
    
    newvalues = 0.0*xvalues
    dx = np.diff(xvalues)
    dxpos = dx
    nrsteps = len(dxpos[dxpos<0])
    lapidx = np.append(0,np.cumsum((-dx+abs(dx))/(-2*dx)))
    if (nrsteps>0):
	indexes = np.where(dxpos<0)
	for index in indexes:
	    dxpos[index] = xvalues[index+1]
	newvalues = np.append(0,np.cumsum(dxpos))+xvalues[0]
    else:
	newvalues = xvalues

    return [newvalues,abs(lapidx)]

def make_cumvalues(xvalues):
    """ Takes a Pandas dataframe with one column as input value.
    Tries to create a cumulative series.
    
    """
    
    newvalues = 0.0*xvalues
    dx = xvalues.diff()
    dxpos = dx
    mask = -xvalues.diff()>0.9*xvalues
    nrsteps = len(dx.loc[mask])
    lapidx = np.cumsum((-dx+abs(dx))/(-2*dx))
    lapidx = lapidx.fillna(value=0)
    test = len(lapidx.loc[lapidx.diff()<0])
    if test != 0:
        lapidx = np.cumsum((-dx+abs(dx))/(-2*dx))
        lapidx = lapidx.fillna(method='ffill')
        lapidx.loc[0] = 0
    if (nrsteps>0):
	dxpos[mask] = xvalues[mask]
        try:
	    newvalues = np.cumsum(dxpos)+xvalues.ix[0,0]
	    newvalues.ix[0,0] = xvalues.ix[0,0]
        except IndexingError:
            try:
	        newvalues = np.cumsum(dxpos)+xvalues.iloc[0,0]
                newvalues.iloc[0,0] = xvalues.iloc[0,0]
            except:
                newvalues = np.cumsum(dxpos)

    else:
	newvalues = xvalues

    newvalues.fillna(method='ffill')

    return [newvalues,lapidx]

def timestrtosecs(string):
    dt = parser.parse(string,fuzzy=True)
    secs = 3600*dt.hour+60*dt.minute+dt.second

    return secs

def timestrtosecs2(timestring,unknown=0):
    try:
	h,m,s = timestring.split(':')
	sval = 3600*int(h)+60.*int(m)+float(s)
    except ValueError:
        try:
	    m,s = timestring.split(':')
	    sval = 60.*int(m)+float(s)
        except ValueError:
            sval = unknown
        
    return sval


def getcol(df,column='TimeStamp (sec)'):
    if column:
        try:
            return df[column]
        except KeyError:
            pass

    l = len(df.index)
    return Series(np.zeros(l))
        

class CSVParser(object):
    """ Parser for reading CSV files created by Painsled

    """
    def __init__(self, *args, **kwargs):
        if args:
            csvfile = args[0]
        else:
            csvfile = kwargs.pop('csvfile','test.csv')

            
        skiprows = kwargs.pop('skiprows',0)
        usecols = kwargs.pop('usecols',None)
        sep = kwargs.pop('sep',',')
        engine = kwargs.pop('engine','c')
        skipfooter = kwargs.pop('skipfooter',None)
        converters = kwargs.pop('converters',None)

        self.csvfile = csvfile
        
        self.df = pd.read_csv(csvfile,skiprows=skiprows,usecols=usecols,
                              sep=sep,engine=engine,skipfooter=skipfooter,
                              converters=converters,index_col=False)
        
        self.defaultcolumnnames = [
            'TimeStamp (sec)',
	    ' Horizontal (meters)',
	    ' Cadence (stokes/min)',
	    ' HRCur (bpm)',
	    ' Stroke500mPace (sec/500m)',
	    ' Power (watts)',
	    ' DriveLength (meters)',
	    ' StrokeDistance (meters)',
	    ' DriveTime (ms)',
	    ' DragFactor',
	    ' StrokeRecoveryTime (ms)',
	    ' AverageDriveForce (lbs)',
	    ' PeakDriveForce (lbs)',
	    ' lapIdx',
	    ' ElapsedTime (sec)',
            ' latitude',
            ' longitude',
	]

        self.columns  = {c:c for c in self.defaultcolumnnames}

    def to_standard(self,*args,**kwargs):
        inverted = {value:key for key,value in self.columns.iteritems()}
        self.df.rename(columns = inverted,inplace=True)
        self.columns = {c:c for c in self.defaultcolumnnames}
        
    def time_values(self,*args,**kwargs):
        timecolumn = kwargs.pop('timecolumn','TimeStamp (sec)')
        unixtimes = self.df[timecolumn]

        return unixtimes

    def write_csv(self,*args, **kwargs):
        gzip = kwargs.pop('gzip',False)
        writeFile = args[0]
        
        # defaultmapping  = {c:c for c in self.defaultcolumnnames}
        self.columns = kwargs.pop('columns',self.columns)

	unixtimes = self.time_values(
            timecolumn=self.columns['TimeStamp (sec)'])
        self.df[self.columns['TimeStamp (sec)']] = unixtimes
        self.df[self.columns[' ElapsedTime (sec)']] = unixtimes-unixtimes.iloc[0]
        # Default calculations
        pace = self.df[
            self.columns[' Stroke500mPace (sec/500m)']].replace(0,300)
        self.df[self.columns[' Stroke500mPace (sec/500m)']] = pace
        
        datadict = {name:getcol(self.df,self.columns[name]) 
                    for name in self.columns}

	nr_rows = len(self.df[self.columns[' Cadence (stokes/min)']])

	# Create data frame with all necessary data to write to csv
	data = DataFrame(datadict)

	data = data.sort_values(by='TimeStamp (sec)',ascending=True)
        data = data.fillna(method='ffill')

        # drop all-zero columns
        for c in data.columns:
            if (data[c] == 0).any() and data[c].mean() == 0:
                data = data.drop(c,axis=1)
	
        if gzip:
	    return data.to_csv(writeFile+'.gz',index_label='index',
                               compression='gzip')
        else:
            return data.to_csv(writeFile,index_label='index')


        
class painsledDesktopParser(CSVParser):

    
    def __init__(self, *args, **kwargs):
        super(painsledDesktopParser, self).__init__(*args, **kwargs)
	# remove "00 waiting to row"
	self.df = self.df[self.df[' stroke.endWorkoutState'] != ' "00 waiting to row"']

        self.cols = [
            ' stroke.driveStartMs',
            ' stroke.startWorkoutMeter',
            ' stroke.strokesPerMin',
            ' stroke.hrBpm',
            ' stroke.paceSecPer1k',
            ' stroke.watts',
            ' stroke.driveMeters',
            ' stroke.strokeMeters',
            ' stroke.driveMs',
            ' stroke.dragFactor',
            ' stroke.slideMs',
            '',
            '',
            ' stroke.intervalNumber',
            ' stroke.driveStartMs',
            ' latitude',
            ' longitude',
        ]

        self.cols = [b if a=='' else a \
                     for a,b in zip(self.cols,self.defaultcolumnnames)]


        self.columns = dict(zip(self.defaultcolumnnames,self.cols))

        # calculations
        pace = self.df[self.columns[' Stroke500mPace (sec/500m)']]/2.
        pace = np.clip(pace,0,1e4)
        self.df[self.columns[' Stroke500mPace (sec/500m)']] = pace
        timestamps = self.df[self.columns['TimeStamp (sec)']]
	# convert to unix style time stamp
	tts = timestamps.apply(lambda x:iso8601.parse_date(x[2:-1]))
        unixtimes = tts.apply(lambda x:time.mktime(x.timetuple()))
        self.df[self.columns['TimeStamp (sec)']] = unixtimes
        self.columns[' ElapsedTime (sec)'] = ' ElapsedTime (sec)'
        self.df[self.columns[' ElapsedTime (sec)']] = unixtimes-unixtimes.iloc[0]
        self.to_standard()

class BoatCoachParser(CSVParser):

    def __init__(self, *args, **kwargs):
        kwargs['skiprows']=1
        kwargs['usecols']=range(25)

        if args:
            csvfile = args[0]
        else:
            csvfile = kwargs['csvfile']
            
        super(BoatCoachParser, self).__init__(*args, **kwargs)

        self.cols = [
            'DateTime',
            'workDistance',
            'strokeRate',
            'currentHeartRate',
            'stroke500MPace',
            'strokePower',
            'strokeLength',
            '',
            'strokeDriveTime',
            'dragFactor',
            ' StrokeRecoveryTime (ms)',
            'strokeAverageForce',
            'strokePeakForce',
            'intervalCount',
            'workTime',
            ' latitude',
            ' longitude',
        ]

        self.cols = [b if a=='' else a \
                     for a,b in zip(self.cols,self.defaultcolumnnames)]

        self.columns = dict(zip(self.defaultcolumnnames,self.cols))

        # get date from footer
        fop = open(csvfile,'r')
        line = fop.readline()
        dated =  re.split('Date:',line)[1][1:-1]
	row_date = parser.parse(dated,fuzzy=True)
        fop.close()

        try:
            datetime = self.df[self.columns['TimeStamp (sec)']]
            row_date = parser.parse(datetime[0],fuzzy=True)
            datetime = datetime.apply(lambda x:parser.parse(x,fuzzy=True))
            unixtimes = datetime.apply(lambda x:time.mktime(x.timetuple()))
        except KeyError:
            # calculations
            row_date2 = time.mktime(row_date.timetuple())
            timecolumn = self.df[self.columns[' ElapsedTime (sec)']]
            timesecs = timecolumn.apply(lambda x:timestrtosecs(x))
            timesecs = make_cumvalues(timesecs)[0]
            unixtimes = row_date2+timesecs

        self.df[self.columns['TimeStamp (sec)']] = unixtimes
        self.columns[' ElapsedTime (sec)'] = ' ElapsedTime (sec)'

        self.df[self.columns[' ElapsedTime (sec)']] = unixtimes-unixtimes[0]
        
        pace = self.df[self.columns[' Stroke500mPace (sec/500m)']].apply(lambda x:timestrtosecs(x))
        self.df[self.columns[' Stroke500mPace (sec/500m)']] = pace

        self.df[self.columns[' DriveTime (ms)']] = 1.0e3*self.df[self.columns[' DriveTime (ms)']]
        
        drivetime = self.df[self.columns[' DriveTime (ms)']]
        stroketime = 60.*1000./(1.0*self.df[self.columns[' Cadence (stokes/min)']])
        recoverytime = stroketime-drivetime
        recoverytime.replace(np.inf,np.nan)    
        recoverytime.replace(-np.inf,np.nan)
        recoverytime = recoverytime.fillna(method='bfill')

        self.df[self.columns[' StrokeRecoveryTime (ms)']] = recoverytime

        self.to_standard()


class ErgDataParser(CSVParser):

    def __init__(self, *args, **kwargs):
        super(ErgDataParser, self).__init__(*args, **kwargs)

        self.row_date = kwargs.pop('row_date',datetime.datetime.utcnow())
        self.cols = [
            'Time (seconds)',
            'Distance (meters)',
            'Stroke Rate',
            'Heart Rate',
            'Pace (seconds per 500m',
            ' Power (watts)',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            ' lapIdx',
            'Time(sec)',
            ' latitude',
            ' longitude',
        ]

        try:
            pace = self.df[self.cols[4]]
        except KeyError:
            self.cols[4] = 'Pace (seconds per 500m)'
            
        self.cols = [b if a=='' else a \
                     for a,b in zip(self.cols,self.defaultcolumnnames)]

        self.columns = dict(zip(self.defaultcolumnnames,self.cols))
                
        
        # calculations
        # get date from footer
        pace = self.df[self.columns[' Stroke500mPace (sec/500m)']]
        pace = np.clip(pace,0,1e4)
        pace = pace.replace(0,300)
        self.df[self.columns[' Stroke500mPace (sec/500m)']] = pace


        seconds = self.df[self.columns['TimeStamp (sec)']]
        firststrokeoffset = seconds.values[0]
        dt = seconds.diff()
        nrsteps = len(dt[dt<0])
        res = make_cumvalues(seconds)
        seconds2 = res[0]+seconds[0]
        lapidx = res[1]
        unixtime = seconds2+totimestamp(self.row_date)

        velocity = 500./pace
        power = 2.8*velocity**3

        self.df[self.columns['TimeStamp (sec)']] = unixtime
        self.columns[' ElapsedTime (sec)'] = ' ElapsedTime (sec)'
        self.df[self.columns[' ElapsedTime (sec)']] = unixtime-unixtime[0]
        self.df[self.columns[' ElapsedTime (sec)']] += firststrokeoffset

        self.df[self.columns[' lapIdx']] = lapidx
        self.df[self.columns[' Power (watts)']] = power

        self.to_standard()
        
class speedcoachParser(CSVParser):

    def __init__(self, *args, **kwargs):
        super(speedcoachParser, self).__init__(*args, **kwargs)

        self.row_date = kwargs.pop('row_date',datetime.datetime.utcnow())
        self.cols = [
            'Time(sec)',
            'Distance(m)',
            'Rate',
            'HR',
            'Split(sec)',
            ' Power (watts)',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            ' lapIdx',
            'Time(sec)',
            ' latitude',
            ' longitude',
        ]

        self.cols = [b if a=='' else a \
                     for a,b in zip(self.cols,self.defaultcolumnnames)]

        self.columns = dict(zip(self.defaultcolumnnames,self.cols))
                
        
        # calculations
        # get date from footer
        pace = self.df[self.columns[' Stroke500mPace (sec/500m)']]
        pace = np.clip(pace,0,1e4)
        self.df[self.columns[' Stroke500mPace (sec/500m)']] = pace

        seconds = self.df[self.columns['TimeStamp (sec)']]
        unixtimes = seconds+totimestamp(self.row_date)


        self.df[self.columns['TimeStamp (sec)']] = unixtimes
        self.columns[' ElapsedTime (sec)'] = ' ElapsedTime (sec)'
        self.df[self.columns[' ElapsedTime (sec)']] = unixtimes-unixtimes[0]

        self.to_standard()

class ErgStickParser(CSVParser):

    
    def __init__(self, *args, **kwargs):
        super(ErgStickParser, self).__init__(*args, **kwargs)

        self.row_date = kwargs.pop('row_date',datetime.datetime.utcnow())
        self.cols = [
            'Total elapsed time (s)',
            'Total distance (m)',
            'Stroke rate (/min)',
            'Current heart rate (bpm)',
            'Current pace (/500m)',
            ' Power (watts)',
            'Drive length (m)',
            'Stroke distance (m)',
            'Drive time (s)',
            'Drag factor',
            'Stroke recovery time (s)',
            'Ave. drive force (lbs)',
            'Peak drive force (lbs)',
            ' lapIdx',
            'Total elapsed time (s)',
            ' latitude',
            ' longitude',
        ]

        self.cols = [b if a=='' else a \
                     for a,b in zip(self.cols,self.defaultcolumnnames)]

        self.columns = dict(zip(self.defaultcolumnnames,self.cols))

        # calculations
        self.df[self.columns[' DriveTime (ms)']] *= 1000.
        self.df[self.columns[' StrokeRecoveryTime (ms)']] *= 1000.
        
        pace = self.df[self.columns[' Stroke500mPace (sec/500m)']]
        pace = np.clip(pace,1,1e4)
        self.df[self.columns[' Stroke500mPace (sec/500m)']] = pace

        velocity = 500./pace
        power = 2.8*velocity**3

        self.df[' Power (watts)'] = power

        seconds = self.df[self.columns['TimeStamp (sec)']]
        res = make_cumvalues(seconds)
        seconds2 = res[0]+seconds[0]
        lapidx = res[1]
        unixtimes = seconds2+totimestamp(self.row_date)
        self.df[self.columns[' lapIdx']] = lapidx
        self.df[self.columns['TimeStamp (sec)']] = unixtimes
        self.columns[' ElapsedTime (sec)'] = ' ElapsedTime (sec)'
        self.df[self.columns[' ElapsedTime (sec)']] = unixtimes-unixtimes.iloc[0]

        self.to_standard()

class RowPerfectParser(CSVParser):

    
    def __init__(self, *args, **kwargs):
        super(RowPerfectParser, self).__init__(*args, **kwargs)

        self.row_date = kwargs.pop('row_date',datetime.datetime.utcnow())
        self.cols = [
            'time',
            'distance',
            'stroke_rate',
            'pulse',
            '',
            'power',
            'stroke_length',
            'distance_per_stroke',
            'drive_time',
            '',
            'recover_time',
            '',
            'peak_force',
            'workout_interval_id',
            '',
            ' latitude',
            ' longitude',
        ]

        self.cols = [b if a=='' else a \
                     for a,b in zip(self.cols,self.defaultcolumnnames)]

        self.columns = dict(zip(self.defaultcolumnnames,self.cols))

        # calculations
        self.df[self.columns[' DriveTime (ms)']] *= 1000.
        self.df[self.columns[' StrokeRecoveryTime (ms)']] *= 1000.
        self.df[self.columns[' PeakDriveForce (lbs)']]/= lbstoN
        self.df[self.columns[' DriveLength (meters)']] /= 100.

        
        
        wperstroke = self.df['energy_per_stroke']
        fav = wperstroke/self.df[self.columns[' DriveLength (meters)']]
        fav /= lbstoN

        self.df[self.columns[' AverageDriveForce (lbs)']] = fav
        
        power = self.df[self.columns[' Power (watts)']]
        v = (power/2.8)**(1./3.)
        pace = 500./v
 
        self.df[' Stroke500mPace (sec/500m)'] = pace

        seconds = self.df[self.columns['TimeStamp (sec)']]
        dt = seconds.diff()
        nrsteps = len(dt[dt<0])
        res = make_cumvalues(seconds)
        seconds2 = res[0]+seconds[0]
        lapidx = res[1]
        unixtime = seconds2+totimestamp(self.row_date)

        self.df[self.columns[' lapIdx']] = lapidx
        self.df[self.columns['TimeStamp (sec)']] = unixtime
        self.columns[' ElapsedTime (sec)'] = ' ElapsedTime (sec)'
        self.df[self.columns[' ElapsedTime (sec)']] = unixtime-unixtime.iloc[0]

        self.to_standard()

class MysteryParser(CSVParser):

    
    def __init__(self, *args, **kwargs):
        super(MysteryParser, self).__init__(*args, **kwargs)
        self.df = self.df.drop(self.df.index[[0]])
        self.row_date = kwargs.pop('row_date',datetime.datetime.utcnow())
        
        kwargs['engine'] = 'python'
        kwargs['sep'] = None
        
        self.row_date = kwargs.pop('row_date',datetime.datetime.utcnow())
        self.cols = [
            'Practice Elapsed Time (s)',
            'Distance (m)',
            'Stroke Rate (SPM)',
            'HR (bpm)',
            ' Stroke500mPace (sec/500m)',
	    ' Power (watts)',
	    ' DriveLength (meters)',
	    ' StrokeDistance (meters)',
	    ' DriveTime (ms)',
	    ' DragFactor',
	    ' StrokeRecoveryTime (ms)',
	    ' AverageDriveForce (lbs)',
	    ' PeakDriveForce (lbs)',
	    ' lapIdx',
	    ' ElapsedTime (sec)',
            'Lat',
            'Lon',
        ]

        self.cols = [b if a=='' else a \
                     for a,b in zip(self.cols,self.defaultcolumnnames)]
        self.columns = dict(zip(self.defaultcolumnnames,self.cols))

        # calculations
        velo = pd.to_numeric(self.df['Speed (m/s)'],errors='coerce')
        
        pace = 500./velo
	pace = pace.replace(np.nan,300)
        pace = pace.replace(np.inf,300)
        self.df[self.columns[' Stroke500mPace (sec/500m)']] = pace

        power = 2.8*velo**3
        self.df[' Power (watts)'] = power

        seconds = self.df[self.columns['TimeStamp (sec)']]
        res = make_cumvalues_array(np.array(seconds))
        seconds3 = res[0]
        lapidx = res[1]


        spm = self.df[self.columns[' Cadence (stokes/min)']]
        strokelength = velo/(spm/60.)
        
        unixtimes = pd.Series(seconds3+totimestamp(self.row_date))
        
        self.df[self.columns[' lapIdx']] = lapidx
        self.df[self.columns['TimeStamp (sec)']] = unixtimes
        self.columns[' ElapsedTime (sec)'] = ' ElapsedTime (sec)'
        self.df[self.columns[' ElapsedTime (sec)']] = unixtimes-unixtimes.iloc[0]
        self.df[self.columns[' StrokeDistance (meters)']] = strokelength

        self.to_standard()

class RowProParser(CSVParser):

    def __init__(self, *args, **kwargs):

        if args:
            csvfile = args[0]
        else:
            csvfile = kwargs['csvfile']
            
        skipfooter = skip_variable_footer(csvfile)
        kwargs['skipfooter'] = skipfooter
        kwargs['engine'] = 'python'
        kwargs['skiprows']=14
        kwargs['usecols']=None

        super(RowProParser, self).__init__(*args, **kwargs)
        self.footer = get_rowpro_footer(csvfile)
        
        #crude EU format detector
        try:
            p = self.df['Pace']*500.
        except TypeError:
            converters = {
		'Distance': \
                lambda x: float(x.replace('.','').replace(',','.')),
		'AvgPace': \
                lambda x: float(x.replace('.','').replace(',','.')),
		'Pace': \
                lambda x: float(x.replace('.','').replace(',','.')),
		'AvgWatts': \
                lambda x: float(x.replace('.','').replace(',','.')),
		'Watts': lambda x: float(x.replace('.','').replace(',','.')),
		'SPM': lambda x: float(x.replace('.','').replace(',','.')),
		'EndHR': lambda x: float(x.replace('.','').replace(',','.')),
		}
            kwargs['converters'] = converters
            super(RowProParser, self).__init__(*args, **kwargs)
            self.footer = get_rowpro_footer(csvfile,converters=converters)

	# replace key values
	footerwork = self.footer[self.footer['Type']<=1]
	maxindex = self.df.index[-1]
	endvalue = self.df.loc[maxindex,'Time']
	#self.df.loc[-1,'Time'] = 0
	dt = self.df['Time'].diff()
	therowindex = self.df[dt<0].index

	if len(footerwork)==2*(len(therowindex)+1):
	    footerwork = self.footer[self.footer['Type']==1]
	    self.df.loc[-1,'Time'] = 0
	    dt = self.df['Time'].diff()
	    therowindex = self.df[dt<0].index
	    nr = 0
	    for i in footerwork.index:
		ttime = footerwork.ix[i,'Time']
		distance = footerwork.ix[i,'Distance']
		avgpace = footerwork.ix[i,'AvgPace']
		self.df.ix[therowindex[nr],'Time'] = ttime
		self.df.ix[therowindex[nr],'Distance'] = distance
		nr += 1
	
	if len(footerwork)==len(therowindex)+1:
	    self.df.loc[-1,'Time'] = 0
	    dt = self.df['Time'].diff()
	    therowindex = self.df[dt<0].index
	    nr = 0
	    for i in footerwork.index:
		ttime = footerwork.ix[i,'Time']
		distance = footerwork.ix[i,'Distance']
		avgpace = footerwork.ix[i,'AvgPace']
		self.df.ix[therowindex[nr],'Time'] = ttime
		self.df.ix[therowindex[nr],'Distance'] = distance
		nr += 1
	else:
	    self.df.loc[maxindex,'Time'] = endvalue
	    for i in footerwork.index:
		ttime = footerwork.ix[i,'Time']
		distance = footerwork.ix[i,'Distance']
		avgpace = footerwork.ix[i,'AvgPace']
		diff = self.df['Time'].apply(lambda z: abs(ttime-z))
		diff.sort_values(inplace=True)
		theindex = diff.index[0]
		self.df.ix[theindex,'Time'] = ttime
		self.df.ix[theindex,'Distance'] = distance

        dateline = get_file_line(11,csvfile)
        dated = dateline.split(',')[0]
        dated2 = dateline.split(';')[0]
        try:
            self.row_date = parser.parse(dated,fuzzy=True)
        except ValueError:
            self.row_date = parser.parse(dated2,fuzzy=True)
            
        self.cols = [
            'Time',
            'Distance',
            'SPM',
            'HR',
            'Pace',
            'Watts',
            '',
            '',
            '',
            '',
            '',
            '',
            '',
            ' lapIdx',
            ' ElapsedTime (sec)',
            ' latitude',
            ' longitude',
        ]

        self.cols = [b if a=='' else a \
                     for a,b in zip(self.cols,self.defaultcolumnnames)]

        self.columns = dict(zip(self.defaultcolumnnames,self.cols))

        # calculations
        self.df[self.columns[' Stroke500mPace (sec/500m)']]*=500.0
        seconds = self.df[self.columns['TimeStamp (sec)']]/1000.
        res = make_cumvalues(seconds)
        seconds2 = res[0]+seconds[0]
        lapidx = res[1]
        seconds3 = seconds2.interpolate()
        seconds3[0] = seconds[0]
        seconds3 = pd.to_timedelta(seconds3,unit='s')
        tts = self.row_date+seconds3
        
        unixtimes = tts.apply(lambda x:time.mktime(x.timetuple()))
        # unixtimes = totimestamp(self.row_date+seconds3)
        self.df[self.columns[' lapIdx']] = lapidx
        self.df[self.columns['TimeStamp (sec)']] = unixtimes
        self.columns[' ElapsedTime (sec)'] = ' ElapsedTime (sec)'
        self.df[self.columns[' ElapsedTime (sec)']] = unixtimes-unixtimes.iloc[0]

        self.to_standard()

class SpeedCoach2Parser(CSVParser):

    def __init__(self, *args, **kwargs):
        
        if args:
            csvfile = args[0]
        else:
            csvfile = kwargs['csvfile']
            
        skiprows,summaryline = skip_variable_header(csvfile)
        kwargs['skiprows'] = skiprows
        super(SpeedCoach2Parser, self).__init__(*args, **kwargs)
        self.df = self.df.drop(self.df.index[[0]])

        for c in self.df.columns:
            if c not in ['Elapsed Time']:
                self.df[c] = pd.to_numeric(self.df[c],errors='coerce')
        
        self.cols = [
            'Elapsed Time',
            'GPS Distance',
            'Stroke Rate',
            'Heart Rate',
            'Split (GPS)',
            'Power',
            '',
            '',
            '',
            '',
            '',
            'Force Avg',
            'Force Max',
            'Interval',
            ' ElapsedTime (sec)',
            'GPS Lat.',
            'GPS Lon.',
            'GPS Speed',
            'Catch',
            'Slip',
            'Finish',
            'Wash',
            'Work',
            'Max Force Angle',
            'cum_dist',
        ]

        self.defaultcolumnnames += [
            'GPS Speed',
            'catch',
            'slip',
            'finish',
            'wash',
            'driveenergy',
            'peakforceangle',
            'cum_dist',
        ]
        
        
        self.cols = [b if a=='' else a \
                     for a,b in zip(self.cols,self.defaultcolumnnames)]

        self.columns = dict(zip(self.defaultcolumnnames,self.cols))

        try:
            dist2 = self.df['GPS Distance']
        except KeyError:
            dist2 = self.df['Distance (GPS)']
            self.columns[' Horizontal (meters)'] = 'Distance (GPS)'
            self.columns['GPS Speed'] = 'Speed (GPS)'
            self.df[self.columns[' PeakDriveForce (lbs)']]/= lbstoN
            self.df[self.columns[' AverageDriveForce (lbs)']]/= lbstoN

        
        cum_dist = make_cumvalues_array(dist2.fillna(method='ffill').values)[0]
        self.df[self.columns['cum_dist']] = cum_dist
        velo = self.df[self.columns['GPS Speed']]
        pace = 500./velo
        pace = pace.replace(np.nan,300)
        self.df[self.columns[' Stroke500mPace (sec/500m)']] = pace

        # get date from header
        dateline = get_file_line(4,csvfile)
        dated = dateline.split(',')[1]
	self.row_date = parser.parse(dated,fuzzy=True)

        timestrings = self.df[self.columns['TimeStamp (sec)']]
        datum = time.mktime(self.row_date.timetuple())
        seconds = timestrings.apply(lambda x:timestrtosecs2(x,unknown=np.nan))
        seconds = clean_nan(np.array(seconds))
        seconds = pd.Series(seconds).fillna(method='ffill').values
        res = make_cumvalues_array(np.array(seconds))
        seconds3 = res[0]
        lapidx = res[1]

        unixtimes = seconds3+totimestamp(self.row_date)
        self.df[self.columns[' lapIdx']] = lapidx
        self.df[self.columns['TimeStamp (sec)']] = unixtimes
        self.columns[' ElapsedTime (sec)'] = ' ElapsedTime (sec)'
        self.df[self.columns[' ElapsedTime (sec)']] = unixtimes-unixtimes[0]

        self.to_standard()
        
        # Read summary data
        skipfooter = 7+len(self.df)
        if summaryline:
            self.summarydata = pd.read_csv(csvfile,
                                           skiprows=summaryline,
                                           skipfooter=skipfooter,
                                           engine='python')
            self.summarydata.drop(0,inplace=True)
        else:
            self.summarydata = pd.DataFrame()

    def allstats(self,separator='|'):
        stri = self.summary(separator=separator)+self.intervalstats(separator=separator)
        return stri
            
    def summary(self,separator='|'):
        stri1 = "Workout Summary - "+self.csvfile+"\n"
        stri1 += "--{sep}Total{sep}-Total-{sep}--Avg--{sep}-Avg-{sep}Avg-{sep}-Avg-{sep}-Max-{sep}-Avg\n".format(sep=separator)
        stri1 += "--{sep}Dist-{sep}-Time--{sep}-Pace--{sep}-Pwr-{sep}SPM-{sep}-HR--{sep}-HR--{sep}-DPS\n".format(sep=separator)

        d = self.df[self.columns['cum_dist']]
        dist = d.max()-d.min()
        t = self.df[self.columns['TimeStamp (sec)']]
        time = t.max()-t.min()
        pace = self.df[self.columns[' Stroke500mPace (sec/500m)']].mean()
        pwr = self.df[self.columns[' Power (watts)']].mean()
        spm = self.df[self.columns[' Cadence (stokes/min)']].mean()
        avghr = self.df[self.columns[' HRCur (bpm)']].mean()
        maxhr = self.df[self.columns[' HRCur (bpm)']].max()
        pacestring = format_pace(pace)
        timestring = format_time(time)
        avgdps = self.df['Distance/Stroke (GPS)'].mean()

        stri1 += "--{sep}{dist:0>5.0f}{sep}".format(
            sep = separator,
            dist = dist,
            )

        stri1 += timestring+separator+pacestring

        stri1 += "{sep}{avgpower:0>5.1f}".format(
            sep = separator,
            avgpower = pwr,
        )
    
        stri1 += "{sep}{avgsr:2.1f}{sep}{avghr:3.1f}{sep}".format(
	    avgsr = spm,
	    sep = separator,
	    avghr = avghr
	)

        stri1 += "{maxhr:3.1f}{sep}{avgdps:0>4.1f}\n".format(
	    sep = separator,
	    maxhr = maxhr,
	    avgdps = avgdps
	)

    
        return stri1

    def intervalstats(self,separator='|'):
        stri = "Workout Details\n"
	stri += "#-{sep}SDist{sep}-Split-{sep}-SPace-{sep}-Pwr-{sep}SPM-{sep}AvgHR{sep}DPS-\n".format(
	    sep = separator
	)
        aantal = len(self.summarydata)
        for i in range(aantal):
            sdist = self.summarydata.ix[self.summarydata.index[[i]],'Total Distance (GPS)']
            split  = self.summarydata.ix[self.summarydata.index[[i]],'Total Elapsed Time']
            space = self.summarydata.ix[self.summarydata.index[[i]],'Avg Split (GPS)']
            pwr = self.summarydata.ix[self.summarydata.index[[i]],'Avg Power']
            spm = self.summarydata.ix[self.summarydata.index[[i]],'Avg Stroke Rate']
            avghr = self.summarydata.ix[self.summarydata.index[[i]],'Avg Heart Rate']
            nrstrokes = self.summarydata.ix[self.summarydata.index[[i]],'Total Strokes']
            dps = float(sdist)/float(nrstrokes)
            splitstring = split.values[0]
            newsplitstring = flexistrftime(flexistrptime(splitstring))
            pacestring = space.values[0]
            newpacestring = flexistrftime(flexistrptime(pacestring))
            
            stri += "{i:0>2}{sep}{sdist:0>5}{sep}{split}{sep}{space}{sep} {pwr} {sep}".format(
                i=i+1,
                sdist = int(float(sdist.values[0])),
                split = newsplitstring,
                space = newpacestring,
                pwr = pwr.values[0],
                sep = separator,
                )
            stri += " {spm} {sep} {avghr:0>3} {sep}{dps:0>4.1f}\n".format(
                sep = separator,
                avghr = avghr.values[0],
                spm = spm.values[0],
                dps = dps,
                )

        return stri
            
