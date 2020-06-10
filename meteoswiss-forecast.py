from urllib.request import Request, urlopen
import json
import pprint
import time
import datetime
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.offsetbox import TextArea, DrawingArea, OffsetImage, AnnotationBbox
import matplotlib.lines as mlines
import numpy as np
import math
import logging
import argparse
import os.path

#from svglib.svglib import svg2rlg
#from reportlab.graphics import renderPM
#import tempfile

class MeteoSwissForecast:
    # Constants
    domain = "https://www.meteoschweiz.admin.ch"
    indexPage = "home.html?tab=overview"

    dataUrlPrefix = "/product/output/forecast-chart/version__"
    dataUrlSuffix = ".json"
    
    symbolsUrlPrefix = "/etc/designs/meteoswiss/assets/images/icons/meteo/weather-symbols/"
    symbolsUrlSuffix = ".svg"

    # MeteoSwiss preset
    rainColorSteps = [1, 2, 4, 6, 10, 20, 40, 60, 100] # as used in the MeteoSwiss App
    rainColorStepSizes = [1, 1, 2, 2, 4, 10, 20, 20, 40] # Steps between fields in rainColorSteps
    rainColors = ["#9d7d95", "#0001f9", "#088b2d", "#02ff07", "#70e900", "#feff01", "#ffc900", "#fe1a00", "#ac00e0"] # as used in the MeteoSwiss App

    # Surounding colors
    colorsLightMode = {"background": "white", "x-axis": "black", "rain-axis": "#0001f9", "temperature-axis": "red"}
    colorsDarkMode = {"background": "black", "x-axis": "white", "rain-axis": "lightblue", "temperature-axis": "red"}


    utcOffset = 0
    days = 0
    data = {}

    def __init__(self):
        # Get offset from local time to UTC, see also https://stackoverflow.com/questions/3168096/getting-computers-utc-offset-in-python
        ts = time.time()
        utcOffset = (datetime.datetime.fromtimestamp(ts) -
                    datetime.datetime.utcfromtimestamp(ts)).total_seconds()
        self.utcOffset = int(utcOffset / 3600) # in hours
        logging.debug("UTC offset: %dh" % self.utcOffset)



    """
    Gets the data URL
    Example Data URL: https://www.meteoschweiz.admin.ch//product/output/forecast-chart/version__20200605_1122/de/800100.json
    The 8001 represents the Zip Code of the location you want
    The 20200605 is the current date
    The 1122 is the time the forecast model got run by Meteo Swiss
    Since we do not know when the last forecast model got run, we have to parse the Meteo Swiss index page and take it from there.
    """
    def getDataUrl(self, zipCode):
        self.zipCode = zipCode
        logging.debug("Using data for location with zip code %d" % self.zipCode)

        req = Request(self.domain + "/" + self.indexPage, headers={'User-Agent': 'Mozilla/5.0'})
        indexPageContent = str(urlopen(req).read())

        dataUrlStartPosition = indexPageContent.find(self.dataUrlPrefix)
        dataUrlEndPosition = indexPageContent.find(self.dataUrlSuffix, dataUrlStartPosition)

        dataUrl = self.domain + "/" + indexPageContent[dataUrlStartPosition:dataUrlEndPosition - 6] + str(self.zipCode) + "00" + self.dataUrlSuffix

        logging.debug("The data URL is: %s" % dataUrl)
        return dataUrl


    """
    Extracts the timestamp of when the model was calculated by meteoSwiss
    """
    def getModelCalculationTimestamp(self, dataUrl):
        arr = dataUrl.split("__")
        # Example of arr[1]: 20200609_0913/de/862000.json
        arr = arr[1].split("/")
        # Example of arr[0]: 20200609_0913
        return int(time.mktime(datetime.datetime.strptime(arr[0],"%Y%m%d_%H%M").timetuple())) + 2*self.utcOffset * 3600



    """
    Loads the data file (JSON) from the MeteoSwiss server and stores it as a dict of lists
    """
    def collectData(self, dataUrl=None, daysToUse=7, compactTimeFormat=False):
        logging.debug("Downloading data from %s..." % dataUrl)
        req = Request(dataUrl, headers={'User-Agent': 'Mozilla/5.0', 'referer': self.domain + "/" + self.indexPage})
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
        self.data["modelCalculationTimestamp"] = self.getModelCalculationTimestamp(dataUrl)
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
            if compactTimeFormat:
                formatedTime.append(datetime.datetime.utcfromtimestamp(timestamp).strftime('%-H'))
            else:
                formatedTime.append(datetime.datetime.utcfromtimestamp(timestamp).strftime('%H:%M'))
        rainfall = self.dataExtractorNormal(forecastData, self.days, "rainfall", 1)
        sunshine = self.dataExtractorNormal(forecastData, self.days, "sunshine", 1)
        temperature = self.dataExtractorNormal(forecastData, self.days, "temperature", 1)
        rainfallVarianceMin, rainfallVarianceMax = self.dataExtractorWithVariance(forecastData, self.days, "variance_rain", 1, 2)
        temperatureVarianceMin, temperatureVarianceMax = self.dataExtractorWithVariance(forecastData, self.days, "variance_range", 1, 2)
        wind = self.dataExtractorWithDataInSubfield(forecastData, self.days, "wind", "data", 1)
        windGustPeak = self.dataExtractorWithDataInSubfield(forecastData, self.days, "wind_gust_peak", "data", 1)

        #symbols = self.dataExtractorNormal(forecastData, self.days, "symbols", 1)
        symbolsTimestamps, symbols = self.dataExtractorSymbols(forecastData, self.days, "symbols", "timestamp", "weather_symbol_id")
        
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
        self.data["symbols"] = symbols
        self.data["symbolsTimestamps"] = symbolsTimestamps

        logging.debug("All data parsed")
        return self.data


    """
    Extracts the data when it is normal structured
    """
    def dataExtractorNormal(self, forecastData, days, topic, index):
        topicData = []
        for day in range(0, days):
            for hour in range(0, 24):
                topicData.append(forecastData[day][topic][hour][index])
        return topicData


    """
    Extracts the data when it is placed in a sub-field
    """
    def dataExtractorWithDataInSubfield(self, forecastData, days, topic, subField, index):
        topicData = []
        for day in range(0, days):
            for hour in range(0, 24):
                topicData.append(forecastData[day][topic][subField][hour][index])
        return topicData


    """
    Extracts the data with a min/max value
    """
    def dataExtractorWithVariance(self, forecastData, days, topic, indexMin, indexMax):
        topicDataMin = []
        topicDataMax = []
        for day in range(0, days):
            for hour in range(0, 24):
                topicDataMin.append(forecastData[day][topic][hour][indexMin])
                topicDataMax.append(forecastData[day][topic][hour][indexMax])
        return [topicDataMin, topicDataMax]


    """
    Extracts the symbols
    """
    def dataExtractorSymbols(self, forecastData, days, topic, indexTS, indexId):
        timestamps = []
        ids = []
        for day in range(0, days):
            for index in range(0, 8):
                timestamp = forecastData[day][topic][index][indexTS]
                timestamps.append(int(int(timestamp) / 1000) + self.utcOffset * 3600)
                ids.append(forecastData[day][topic][index][indexId])
        return [timestamps, ids]


    """
    Download the symbol and convert it to a png file
    Does not work, see readme for manual way
    """
    #def downloadSymbol(self, id):
        #req = Request(self.domain + "/" + self.symbolsUrlPrefix + str(id) + self.symbolsUrlSuffix, headers={'User-Agent': 'Mozilla/5.0'})
        #symbol = urlopen(req).read()
        #open(tempfile.gettempdir() + "/" + str(id) + '.svg', 'w').write(symbol.decode('utf-8'))
        #drawing = svg2rlg(tempfile.gettempdir() + "/" + str(id) + ".svg")
        #renderPM.drawToFile(drawing, tempfile.gettempdir() + "/" + str(id) + ".png", fmt="PNG") # Note, background will be white, see https://github.com/deeplook/svglib/issues/171


    """
    Generates the graphic containing the forecast
    """
    def generateGraph(self, data=None, outputFilename=None, useExtendedStyle=False, timeDivisions=3, graphWidth=1280, graphHeight=300, darkMode=False):
        logging.debug("Creating graph...")
        if darkMode:
            colors = self.colorsDarkMode
        else:
            colors = self.colorsLightMode

        fig, ax1 = plt.subplots()

        # Show gray background on every 2nd day
        for day in range(0, data["noOfDays"], 2):
            plt.axvspan(data["timestamps"][0 + day * 24], data["timestamps"][23 + day * 24] + 3600, facecolor='gray', alpha=0.2)

        # Rain (data gets splitted to stacked bars)
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

        #ax1.set_ylabel('Rainfall', color=colors["rain-axis"])
        ax1.tick_params(axis='y', labelcolor=colors["x-axis"])
        plt.ylim(0, max(data["rainfall"]) + 1)
        
        rainYRange = plt.ylim()

        # Show when the model was last calculated
        l = mlines.Line2D([data["modelCalculationTimestamp"], data["modelCalculationTimestamp"]], [rainYRange[0], rainYRange[1]])
        ax1.add_line(l)

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
        ax2.tick_params(axis='y', labelcolor=colors["temperature-axis"])
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
        plt.xticks(data["timestamps"][::timeDivisions], data["formatedTime"][::timeDivisions])

        # Time ticks        
        ax1.tick_params(axis='x', colors=colors["x-axis"])


        # Plot dimension and borders
        plt.margins(x=0)
        ax1.margins(x=0)
        ax2.margins(x=0)
        borders = 0.03
        plt.subplots_adjust(left=borders+0.01, right=1-borders-0.01, top=1-borders-0.2, bottom=borders+0.15)

        if not graphWidth:
            graphWidth = 1280
        if not graphHeight:
            graphHeight = 300
        logging.debug("Graph size: %dy%d" % (graphWidth, graphHeight))
        fig.set_size_inches(float(graphWidth)/fig.get_dpi(), float(graphHeight)/fig.get_dpi())

        # Print day names
        bbox = ax1.get_window_extent().transformed(fig.dpi_scale_trans.inverted())
        width, height = bbox.width * fig.dpi, bbox.height * fig.dpi
        xPixelsPerDay = width / data["noOfDays"]

        for day in range(0, data["noOfDays"]):
            ax1.annotate(data['dayNames'][day], xy=(day * xPixelsPerDay + xPixelsPerDay / 2, -40), xycoords='axes pixels', ha="center", weight='bold', color=colors["x-axis"])

        # Show y-axis units
        ax1.annotate("mm/h", xy=(width + 20, height + 15), xycoords='axes pixels', ha="center", color=colors["rain-axis"])
        ax1.annotate("°C", xy=(-20, height + 15), xycoords='axes pixels', ha="center", color=colors["temperature-axis"])

        # Symbols
        for i in range(0, len(data["symbols"])):
            symbolFile = "symbols/" + str(data["symbols"][i]) + ".png"
            if not os.path.isfile(symbolFile):
                logging.warning("The symbol file %s seems to be missing. Please check the README.md!" % symbolFile)
                continue
            symbolImage = mpimg.imread(symbolFile)
            imagebox = OffsetImage(symbolImage, zoom=0.1)
            xyPos = ((data["symbolsTimestamps"][i] - data["symbolsTimestamps"][0]) / (24*3600) + len(data["symbols"])/24/6/data["noOfDays"]) * xPixelsPerDay, height + 28
            ab = AnnotationBbox(imagebox, xy=xyPos, xycoords='axes pixels', frameon=False)
            ax1.add_artist(ab)

        # Show generation date
        #y0, ymax = plt.ylim()
        ## TODO use absolute position in pixel
        ## TODO show date/time of forcast model run
        ##plt.text(data["timestamps"][0], ymax * 0.96, " " + "Last updated on " + str(datetime.datetime.now().strftime("%d. %b %Y %H:%M:%S")))
        #ax1.annotate("Last updated on " + str(datetime.datetime.now().strftime("%d. %b %Y %H:%M:%S")), xy=(width-10, height - 20), xycoords='axes pixels', ha="right")
        logging.debug("Saving graph to %s" % outputFilename)
        plt.savefig(outputFilename, facecolor=colors["background"])



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Script to fetch the MeteoSwiss Weather Forecast data and generate a graph')
    parser.add_argument('-v', action='store_true', help='Verbose output')
    parser.add_argument('-z', '--zip-code', action='store', type=int, required=True, help='Zip Code of the location to be represented')
    parser.add_argument('-f', '--file', type=argparse.FileType('w'), required=True, help='File name of the graph to be written')
    parser.add_argument('--extended-style', action='store_true', help='Use extended style instead of MeteoSwiss App mode')
    parser.add_argument('--days-to-show', action='store', type=int, choices=range(1, 8), help='Number of days to show. If not set, use all data')
    parser.add_argument('--height', action='store', type=int, help='Height of the graph in pixel')
    parser.add_argument('--width', action='store', type=int, help='Width of the graph in pixel')
    parser.add_argument('--time-divisions', action='store', type=int, help='Distance in hours between time labels')
    parser.add_argument('--compact-time-format', action='store_true', help='Show only hours instead of Hours and Minutes')
    parser.add_argument('--dark-mode', action='store_true', help='Use dark colors')

    args = parser.parse_args()

    logLevel = logging.INFO
    if args.v:
        logLevel = logging.DEBUG

    logging.basicConfig(format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%d-%b-%y %H:%M:%S', level=logLevel)

    meteoSwissForecast = MeteoSwissForecast()
    dataUrl = meteoSwissForecast.getDataUrl(args.zip_code)
    forecastData = meteoSwissForecast.collectData(dataUrl=dataUrl, daysToUse=args.days_to_show, compactTimeFormat=args.compact_time_format)
    #pprint.pprint(forecastData)
    meteoSwissForecast.generateGraph(data=forecastData, outputFilename=args.file.name, useExtendedStyle=args.extended_style, timeDivisions=args.time_divisions, graphWidth=args.width, graphHeight=args.height, darkMode=args.dark_mode)

