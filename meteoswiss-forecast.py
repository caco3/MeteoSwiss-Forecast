from urllib.request import Request, urlopen
import json
import pprint
import time
import datetime
import matplotlib.pyplot as plt
import numpy as np
import math
import logging
import argparse

class MeteoSwissForecast:
    # Constants
    domain = "https://www.meteoschweiz.admin.ch"
    indexPage = "home.html?tab=overview"

    dataFilePrefix = "/product/output/forecast-chart/version__"
    dataFileSuffix = ".json"

    rainColorSteps = [1, 2, 4, 6, 10, 20, 40, 60, 100] # as used in the MeteoSwiss App
    rainColorStepSizes = [1, 1, 2, 2, 4, 10, 20, 20, 40] # Steps between fields in rainColorSteps
    rainColors = ["#9d7d95", "#0001f9", "#088b2d", "#02ff07", "#70e900", "#feff01", "#ffc900", "#fe1a00", "#ac00e0"] # as used in the MeteoSwiss App

    utcOffset = 0

    days = 0
    data = {}

    def __init__(self, zipCode):
        # Get offset from local time to UTC, see also https://stackoverflow.com/questions/3168096/getting-computers-utc-offset-in-python
        ts = time.time()
        utcOffset = (datetime.datetime.fromtimestamp(ts) -
                    datetime.datetime.utcfromtimestamp(ts)).total_seconds()
        self.utcOffset = int(utcOffset / 3600) # in hours
        logging.debug("UTC offset: %dh" % self.utcOffset)

        self.zipCode = zipCode
        logging.debug("Using data for location with zip code %d" % self.zipCode)


    """
    Gets the data URL
    Example Data URL: https://www.meteoschweiz.admin.ch//product/output/forecast-chart/version__20200605_1122/de/800100.json
    The 8001 represents the Zip Code of the location you want
    The 20200605 is the current date
    The 1122 is the time the forecast model got run by Meteo Swiss
    Since we do not know when the last forecast model got run, we have to parse the Meteo Swiss index page and take it from there.
    """
    def getDataUrl(self):
        req = Request(self.domain + "/" + self.indexPage, headers={'User-Agent': 'Mozilla/5.0'})
        indexPageContent = str(urlopen(req).read())

        dataUrlStartPosition = indexPageContent.find(self.dataFilePrefix)
        dataUrlEndPosition = indexPageContent.find(self.dataFileSuffix, dataUrlStartPosition)

        dataUrl = self.domain + "/" + indexPageContent[dataUrlStartPosition:dataUrlEndPosition - 6] + str(self.zipCode) + "00" + self.dataFileSuffix

        logging.debug("The data URL is: %s" % dataUrl)
        return dataUrl


    """
    Loads the data file (JSON) from the MeteoSwiss server and stores it as a dict of lists
    """
    def collectData(self, dataUrl, daysToUse):
        logging.debug("Downloading data from %s..." % dataUrl)
        req = Request(dataUrl, headers={'User-Agent': 'Mozilla/5.0'})
        forcastDataPlain = (urlopen(req).read()).decode('utf-8')
        logging.debug("Download completed")
        forecastData = json.loads(forcastDataPlain)

        self.days = len(forecastData)
        logging.debug("The forecast contains data for %d days" % self.days)
        if daysToUse != None:
            if self.days < daysToUse:
                daysToUse = self.days
            if self.days != daysToUse:
                logging.debug("But going only to use the first %d days" % daysToUse)
            self.days = daysToUse

        dayNames = []
        formatedTime = []
        timestamps = []
        rainfall = []

        logging.debug("Parsing data...")
        for day in range(0, self.days):
            # get day names
            dayNames.append(forecastData[day]["day_string"]) # name of the day

            # get timestamps (the same for all data)
            for hour in range(0, 24):
                timestamp = forecastData[day]["rainfall"][hour][0]
                timestamp = int(int(timestamp) / 1000) + self.utcOffset * 3600
                timestamps.append(timestamp)

        dayIndex = 0
        for timestamp in timestamps:
            formatedTime.append(datetime.datetime.utcfromtimestamp(timestamp).strftime('%H:%M'))

        rainfall = self.dataExtractorNormal(forecastData, self.days, "rainfall")
        sunshine = self.dataExtractorNormal(forecastData, self.days, "sunshine")
        temperature = self.dataExtractorNormal(forecastData, self.days, "temperature")
        rainfallVarianceMin, rainfallVarianceMax = self.dataExtractorWithVariance(forecastData, self.days, "variance_rain")
        temperatureVarianceMin, temperatureVarianceMax = self.dataExtractorWithVariance(forecastData, self.days, "variance_range")
        wind = self.dataExtractorWithDataInSubfield(forecastData, self.days, "wind")
        windGustPeak = self.dataExtractorWithDataInSubfield(forecastData, self.days, "wind_gust_peak")

        # TODO also extract symbols

        self.data["noOfDays"] = self.days
        self.data["dayNames"] = dayNames
        self.data["timestamps"] = timestamps
        self.data["formatedTime"] = formatedTime
        self.data["rainfall"] = rainfall
        self.data["rainfallVarianceMin"] = rainfallVarianceMin
        self.data["rainfallVarianceMax"] = rainfallVarianceMax
        self.data["temperature"] = temperature
        self.data["temperatureVarianceMin"] = temperatureVarianceMin
        self.data["temperatureVarianceMax"] = temperatureVarianceMax
        self.data["wind"] = wind
        self.data["windGustPeak"] = windGustPeak

        logging.debug("All data parsed")
        return self.data


    """
    Extracts the data when it is normal structured
    """
    def dataExtractorNormal(self, forecastData, days, topic):
        topicData = []
        for day in range(0, days):
            for hour in range(0, 24):
                topicData.append(forecastData[day][topic][hour][1])
        return topicData


    """
    Extracts the data when it is placed in a sub-field
    """
    def dataExtractorWithDataInSubfield(self, forecastData, days, topic):
        topicData = []
        for day in range(0, days):
            for hour in range(0, 24):
                topicData.append(forecastData[day][topic]["data"][hour][1])
        return topicData


    """
    Extracts the data with a min/max value
    """
    def dataExtractorWithVariance(self, forecastData, days, topic):
        topicDataMin = []
        topicDataMax = []
        for day in range(0, days):
            for hour in range(0, 24):
                topicDataMin.append(forecastData[day][topic][hour][1])
                topicDataMax.append(forecastData[day][topic][hour][2])
        return [topicDataMin, topicDataMax]




    """
    
    """
    def generateGraph(self, data, filename, useExtendedStyle, timeDivisions, graphWidth, graphHeight):
        logging.debug("Creating graph...")
        fig, ax1 = plt.subplots()

        # Show gray background on every 2nd day
        for day in range(0, data["noOfDays"], 2):
            plt.axvspan(data["timestamps"][0 + day * 24], data["timestamps"][23 + day * 24] + 3600, facecolor='gray', alpha=0.2)

        # Rain
        rainBars = [0] * len(self.rainColorSteps)

        for i in range(0, len(self.rainColorSteps)):
            rainBars[i] = []
        
        for rain in data["rainfall"]:
            for i in range(0, len(self.rainColorSteps)):
                if rain > self.rainColorSteps[i]:
                    rainBars[i].append(self.rainColorStepSizes[i])
                else:
                    if i > 0:
                        rainBars[i].append(max(rain - self.rainColorSteps[i-1], 0))
                    else:
                        rainBars[i].append(rain)
                    continue
            
        ax1.bar(data["timestamps"], rainBars[0], width=3000, color=self.rainColors[0], align='edge')
        bottom = [0] * len(rainBars[0])
        for i in range(1, len(self.rainColorSteps)):
            bottom = np.add(bottom, rainBars[i-1]).tolist()
            ax1.bar(data["timestamps"], rainBars[i], bottom=bottom, width=3000, color=self.rainColors[i], align='edge')

        #ax1.set_ylabel('Rainfall', color=self.rainColors[1])
        ax1.tick_params(axis='y', labelcolor=self.rainColors[1])
        plt.ylim(0, max(data["rainfall"]) + 1)

        # color bar as y axis (not working)
        #autoAxis = ax1.axis()
        ##rec = plt.Rectangle((autoAxis[0]-0.7,autoAxis[2]-0.2),(autoAxis[1]-autoAxis[0])+1,(autoAxis[3]-autoAxis[2])+0.4,fill=False,lw=2)
        #rec = plt.Rectangle((data["timestamps"][0] - 10000, 0),  10000, 1  , fill=False, lw=2)
        #rec = ax1.add_patch(rec)
        #rec.set_clip_on(False)


        # Temperature
        color = "red"
        ax2 = ax1.twinx()  # instantiate a second axes that shares the same x-axis
        ax2.plot(data["timestamps"], data["temperature"], label = "temperature", color=color, linewidth=4)
        #ax2.set_ylabel('Temperature', color=color)
        ax2.tick_params(axis='y', labelcolor=color)
        ax2.yaxis.tick_left()
        ax1.yaxis.tick_right()

        plt.grid(True)

        # Make sure minimum temperature is 0 or lower
        # Make sure temperature max is multiple of 5
        plt.ylim(min(0, min(data["temperatureVarianceMin"])), math.ceil(float(max(data["temperatureVarianceMax"])) / 5) * 5)

        # Temperature variance
        color = "red"
        ax3 = ax2.twinx()  # instantiate a second axes that shares the same x-axis
        ax3.axes.yaxis.set_visible(False)

        ax3.fill_between(data["timestamps"], data["temperatureVarianceMin"], data["temperatureVarianceMax"], facecolor='red', alpha=0.2)
        ax3.tick_params(axis='y', labelcolor=color)

        plt.ylim(min(0, min(data["temperatureVarianceMin"])), math.ceil(float(max(data["temperatureVarianceMax"])) / 5) * 5)


        # Time axis
        if not timeDivisions:
            timeDivisions = 3 # 3 hours between ticks
        plt.xticks(data["timestamps"][::timeDivisions], data["formatedTime"][::timeDivisions])

        # Time ticks        
        ax1.tick_params(axis='x')


        # Plot dimension and borders
        plt.margins(x=0)
        ax1.margins(x=0)
        ax2.margins(x=0)
        borders = 0.03
        plt.subplots_adjust(left=borders+0.01, right=1-borders-0.01, top=1-borders, bottom=borders+0.13)

        if not graphWidth:
            graphWidth = 1280
        if not graphHeight:
            graphHeight = 300
        fig.set_size_inches(float(graphWidth)/fig.get_dpi(), float(graphHeight)/fig.get_dpi())


        # Print day names
        bbox = ax1.get_window_extent().transformed(fig.dpi_scale_trans.inverted())
        width, height = bbox.width * fig.dpi, bbox.height * fig.dpi
        xPixelsPerDay = width / data["noOfDays"]

        for day in range(0, data["noOfDays"]):
            ax1.annotate(data['dayNames'][day], xy=(day * xPixelsPerDay + xPixelsPerDay / 2, -40), xycoords='axes pixels', ha="center")

        # Show generation date
        y0, ymax = plt.ylim()
        # TODO use absolute position in pixel
        # TODO show date/time of forcast model run
        #plt.text(data["timestamps"][0], ymax * 0.96, " " + "Last updated on " + str(datetime.datetime.now().strftime("%d. %b %Y %H:%M:%S")))
        ax1.annotate("Last updated on " + str(datetime.datetime.now().strftime("%d. %b %Y %H:%M:%S")), xy=(width-10, height - 20), xycoords='axes pixels', ha="right")

        logging.debug("Saving graph to %s" % filename)
        plt.savefig(filename)



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Script to fetch the MeteoSwiss Weather Forecast data and generate a graph')
    parser.add_argument('-v', action='store_true', help='Verbose output')
    parser.add_argument('-z', '--zip-code', action='store', type=int, required=True, help='Zip Code of the location to be represented')
    parser.add_argument('-f', '--file', type=argparse.FileType('w'), required=True, help='File name of the graph to be written')
    parser.add_argument('--extended-style', action='store_true', help='Use extended style instead of MeteoSwiss App mode')
    parser.add_argument('--days-to-show', action='store', type=int, choices=range(1, 8), help='Number of days to show. If not set, use all data')
    parser.add_argument('--height', action='store', type=int, help='Height of the graph in pixel')
    parser.add_argument('--width', action='store', type=int, help='Width of the graph in pixel')
    parser.add_argument('--time-divisions', action='store', type=int, help='DIstance in hours between time labels')

    args = parser.parse_args()

    logLevel = logging.INFO
    if args.v:
        logLevel = logging.DEBUG

    logging.basicConfig(format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%d-%b-%y %H:%M:%S', level=logLevel)

    meteoSwissForecast = MeteoSwissForecast(args.zip_code)
    dataUrl = meteoSwissForecast.getDataUrl()
    data = meteoSwissForecast.collectData(dataUrl, args.days_to_show)
    #pprint.pprint(data)
    meteoSwissForecast.generateGraph(data, args.file.name, args.extended_style, args.time_divisions, args.width, args.height)

