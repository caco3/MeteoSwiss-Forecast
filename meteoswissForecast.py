from urllib.request import Request, urlopen
import json
import pprint
import time
import datetime
import pytz
import locale
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.patches import Circle, Rectangle
from matplotlib.offsetbox import TextArea, DrawingArea, OffsetImage, AnnotationBbox
import matplotlib.lines as mlines
import matplotlib.patheffects as path_effects
from matplotlib.ticker import FormatStrFormatter
import numpy as np
import math
import logging
import argparse
import os.path
import json
import measurementDataProvider


#from svglib.svglib import svg2rlg
#from reportlab.graphics import renderPM
#import tempfile


# Meteoswiss only provides the data of the up to 7 days.
maximumNumberOfDays = 7


# Returns the current UTC offset as integer value.
def getCurrentUtcOffset():
    utcOffset = datetime.datetime.now(pytz.timezone('Europe/Zurich')).strftime('%z')
    utcOffset = int(int(utcOffset)/100)
    print("Current UTC Offset: %d" % utcOffset)
    return utcOffset


class MeteoSwissForecast:
    # Constants
    domain = "http://www.meteoschweiz.admin.ch"
    indexPage = "home.html?tab=overview" # => https://www.meteoschweiz.admin.ch/home.html?tab=overview

    dataUrlPrefix = "/product/output/forecast-chart/version__"
    dataUrlSuffix = ".json"

    locationUrlPrefix = "/etc.clientlibs/internet/clientlibs/meteoswiss/resources/ajax/location/"
    locationUrlSuffix = ".json"

    #symbolsUrlPrefix = "/etc.clientlibs/internet/clientlibs/meteoswiss/resources/assets/images/icons/meteo/weather-symbols/"
    #symbolsUrlSuffix = ".svg"

    # MeteoSwiss preset (Violet, Blue, Green, Light Green, Yellow, Light Orange, Orange, Red, Violet)
    rainColorSteps = [1, 2, 4, 6, 10, 20, 40, 60, 100] # as used in the MeteoSwiss App
    rainColorStepSizes = [1, 1, 2, 2, 4, 10, 20, 20, 40] # Steps between fields in rainColorSteps
    rainColors = ["#9d7d95", "#0001f9", "#088b2d", "#06fd0c", "#fffe00", "#ffc703", "#fc7e06", "#fe1a00", "#ac00e0"] # as used in the MeteoSwiss App

    # Surounding colors
    colorsLightMode = {"background": "white", "x-axis": "black", "rain-axis": "#0001f9", "temperature-axis": "red", "temperature-label": "red"}
    colorsDarkMode = {"background": "black", "x-axis": "white", "rain-axis": "lightblue", "temperature-axis": "#ffabab", "temperature-label": "red"}

    temperatureColor = "red"

    textShadowWidth = 3 # pixel

    utcOffset = 0
    days = 0
    data = {}

    def __init__(self, zipCode, utcOffset=None):
        self.zipCode = zipCode

        logging.debug("Using data for location with zip code %d" % self.zipCode)
        try:
            self.cityName = self.getCityName()
        except Exception as e:
            raise Exception("Failed to get City name: %s" % e)

        if utcOffset == None:
            # Get offset from local time to UTC, see also https://stackoverflow.com/questions/3168096/getting-computers-utc-offset-in-python
            ts = time.time()
            utcOffset = (datetime.datetime.fromtimestamp(ts) -
                        datetime.datetime.utcfromtimestamp(ts)).total_seconds()
            self.utcOffset = int(utcOffset / 3600) # in hours
        else:
            self.utcOffset = utcOffset

        logging.debug("UTC offset: %d" % self.utcOffset)


    """
    Gets the data URL
    Example Data URL: https://www.meteoschweiz.admin.ch//product/output/forecast-chart/version__20200605_1122/de/800100.json
    The 8001 represents the Zip Code of the location you want
    The 20200605 is the current date
    The 1122 is the time the forecast model got run by Meteo Swiss
    Since we do not know when the last forecast model got run, we have to parse the Meteo Swiss index page and take it from there.
    """
    def getDataUrl(self):
        indexUrl = self.domain + "/" + self.indexPage
        logging.debug("The index URL is: %s" % indexUrl)
        req = Request(indexUrl, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            indexPageContent = str(urlopen(req).read())
        except Exception as e:
            raise Exception("Failed to fetch index URL (\"%s\"): \"%s\"" % (indexUrl, e))

        dataUrlStartPosition = indexPageContent.find(self.dataUrlPrefix)
        dataUrlEndPosition = indexPageContent.find(self.dataUrlSuffix, dataUrlStartPosition)
        if dataUrlStartPosition == -1:
            raise Exception("Failed to find Data URL prefix (\"%s\") in index URL (\"%s\")" % (self.dataUrlPrefix, indexUrl))
        if dataUrlEndPosition == -1:
            raise Exception("Failed to find Data URL suffix (\"%s\") in index Page (\"%s\")" % (self.dataUrlSuffix, indexUrl))

        dataUrl = self.domain + "/" + indexPageContent[dataUrlStartPosition:dataUrlEndPosition - 6] + str(self.zipCode) + "00" + self.dataUrlSuffix

        logging.debug("The data URL is: \"%s\"" % dataUrl)
        return dataUrl


    """
    Fetches the meta data file and extracts the city name
    Example location URL: https://www.meteoschweiz.admin.ch/etc/designs/meteoswiss/ajax/location/800100.json
    """
    def getCityName(self):
        locationUrl = self.domain + self.locationUrlPrefix + str(self.zipCode) + "00" + self.locationUrlSuffix
        logging.debug("Downloading data from %s..." % locationUrl)
        req = Request(locationUrl, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            locationDataPlain = (urlopen(req).read()).decode('utf-8')
        except Exception as e:
            raise Exception("Failed to fetch location URL (\"%s\"): \"%s\"" % (locationUrl, e))

        logging.debug("Download completed")
        locationData = json.loads(locationDataPlain)

        logging.debug("The location is: %s" % locationData["city_name"])
        return locationData["city_name"]


    """
    Extracts the timestamp (in UTC) of when the model was calculated by meteoSwiss
    """
    def getModelCalculationTimestamp(self, dataUrl):
        arr = dataUrl.split("__")
        # Example of arr[1]: 20200609_0913/de/862000.json
        # Note that the time is in UTC!
        arr = arr[1].split("/")
        # Example of arr[0]: 20200609_0913
        #return int(time.mktime(datetime.datetime.strptime(arr[0],"%Y%m%d_%H%M").timetuple()) + self.utcOffset * 3600)
        return int(time.mktime(datetime.datetime.strptime(arr[0],"%Y%m%d_%H%M").timetuple()))


    """
    Loads the data file (JSON) from the MeteoSwiss server and stores it as a dict of lists
    """
    def collectData(self, dataUrl=None, daysToUse=7, timeFormat="%H:%M", dateFormat="%A, %-d. %B", localeAlias="en_US.utf8"):
        self.data["dataUrl"] = dataUrl
        logging.debug("Downloading data from %s..." % dataUrl)
        req = Request(dataUrl, headers={'User-Agent': 'Mozilla/5.0', 'referer': self.domain + "/" + self.indexPage})
        try:
            forcastDataPlain = (urlopen(req).read()).decode('utf-8')
        except Exception as e:
            raise Exception("Failed to fetch data URL (%s): %s" % (dataUrl, e))

        logging.debug("Download completed")
        forecastData = json.loads(forcastDataPlain)

        # Meteoswiss only provides the data of the up to 7 days.
        if daysToUse > maximumNumberOfDays:
            daysToUse = maximumNumberOfDays
            logging.warning("Limiting days to be shown to %d days!" % maximumNumberOfDays)

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
        ## TODO add zip code and location name to data dict

        try:
            locale.setlocale(locale.LC_ALL, localeAlias)
        except Exception as e:
            logging.warning("Unable to uses locale \"%s\": %s" % (localeAlias, e))

        for day in range(0, self.days):
            # get day names
            timestamp = int(forecastData[day]["min_date"]) / 1000 + self.utcOffset * 3600
            dayNames.append(datetime.datetime.utcfromtimestamp(timestamp).strftime(dateFormat)) # name of the day

            # get timestamps (the same for all data)
            for hour in range(0, 24):
                try: # Last day might not have 24h
                    #print(day, hour)
                    timestamp = forecastData[day]["rainfall"][hour][0]
                    timestamp = int(int(timestamp) / 1000) + self.utcOffset * 3600
                except:
                    logging.warning("For day %d only data of %d hours are provided!" % (day, hour))
                    timestamp = timestamps[-1] + 3600 # Use timstamp of last hour and add 3600 seconds
                timestamps.append(timestamp)

        if self.days < maximumNumberOfDays: # We can also add the first hour of the next day
            timestamp = forecastData[self.days]["rainfall"][0][0]
            timestamp = int(int(timestamp) / 1000) + self.utcOffset * 3600
            timestamps.append(timestamp)

        dayIndex = 0
        for timestamp in timestamps:
            formatedTime.append(datetime.datetime.utcfromtimestamp(timestamp).strftime(timeFormat))
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

        # Testing
        #self.data["temperature"][-1] = -1
        #self.data["temperature"][0] = -1
        #try:
            #self.data["temperature"][48] = -1
        #except:
            #pass

        # Sometimes the data contains None for some fields
        # We replace it by NaN
        for key, data in self.data.items():
            try:
                if key != "dataUrl":
                    self.data[key] =  [np.nan if v is None else v for v in self.data[key]]
            except:
                pass

        logging.debug("All data parsed")

        # Export it for testing
        #self.exportForecastData(forecastData, "forecast.json")

        return self.data


    """
    Extracts the data when it is normal structured
    """
    def dataExtractorNormal(self, forecastData, days, topic, index):
        topicData = []
        for day in range(0, days):
            for hour in range(0, 24):
                try:
                    topicData.append(forecastData[day][topic][hour][index])
                except:
                    logging.warning("For day %d only %s data of %d hours are provided!" % (day, topic, hour))
                    topicData.append(None)

        if days < maximumNumberOfDays: # We can also add the first hour of the next day
            topicData.append(forecastData[day+1][topic][0][index])

        return topicData


    """
    Extracts the data when it is placed in a sub-field
    """
    def dataExtractorWithDataInSubfield(self, forecastData, days, topic, subField, index):
        topicData = []
        for day in range(0, days):
            for hour in range(0, 24):
                try:
                    topicData.append(forecastData[day][topic][subField][hour][index])
                except:
                    logging.warning("For day %d only %s data of %d hours are provided!" % (day, topic, hour))
                    topicData.append(None)

        if days < maximumNumberOfDays: # We can also add the first hour of the next day
            topicData.append(forecastData[day+1][topic][subField][0][index])

        return topicData


    """
    Extracts the data with a min/max value
    """
    def dataExtractorWithVariance(self, forecastData, days, topic, indexMin, indexMax):
        topicDataMin = []
        topicDataMax = []
        for day in range(0, days):
            for hour in range(0, 24):
                try:
                    topicDataMin.append(forecastData[day][topic][hour][indexMin])
                    topicDataMax.append(forecastData[day][topic][hour][indexMax])
                except:
                    logging.warning("For day %d only %s data of %d hours are provided!" % (day, topic, hour))
                    topicDataMin.append(None)
                    topicDataMax.append(None)

        if days < maximumNumberOfDays: # We can also add the first hour of the next day
            topicDataMin.append(forecastData[day+1][topic][0][indexMin])
            topicDataMax.append(forecastData[day+1][topic][0][indexMax])

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

        if days < maximumNumberOfDays: # We can also add the first hour of the next day
            timestamp = forecastData[day+1][topic][index][indexTS]
            timestamps.append(int(int(timestamp) / 1000) + self.utcOffset * 3600)
            ids.append(forecastData[day+1][topic][index][indexId])

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
    Exports a JSON file containing the forecast data ( as generated with the collectData() function) 
    """
    def exportForecastData(self, forecastData, outputFilename):
        with open(outputFilename, 'w') as outfile:
            json.dump(forecastData, outfile, indent=2)
        logging.debug("Forecast data got exported to %s" % outputFilename)


    """
    Import a JSON file containing the forecast data ( as generated with the collectData() function) 
    """
    def importForecastData(self, inputFilename):
        with open(inputFilename) as forecastData:
            return json.load(forecastData)


    def getNextRain(self, forecastData):
        timestampNow = time.mktime(time.gmtime()) + self.utcOffset * 3600

        nextRain = None
        for i in range(len(forecastData['rainfall'])):
            if forecastData['rainfall'][i] > 0:
                t = math.floor((forecastData['timestamps'][i] - timestampNow) / 3600)
                if t > -1: # now or in future
                    nextRain = t
                    break

        nextPossibleRain = None
        for i in range(len(forecastData['rainfallVarianceMax'])):
            print(i, forecastData['timestamps'][i], forecastData['formatedTime'][i], forecastData['rainfallVarianceMax'][i])
            if forecastData['rainfallVarianceMax'][i] > 0:
                t = math.floor((forecastData['timestamps'][i] - timestampNow) / 3600)
                if t > -1: # now or in future
                    nextPossibleRain = t
                    break

        return nextRain, nextPossibleRain


    """
    Generates the graphic containing the forecast
    """
    def generateGraph(self, data=None, outputFilename=None, timeDivisions=6, graphWidth=1920, graphHeight=300, darkMode=False, rainVariance=False, minMaxTemperature=False, fontSize=12, symbolZoom=1.0, symbolDivision=1, showCityName=False, hideDataCopyright=False, writeMetaData=None, progressCallback=None, measuredRain=None, measuredTemperature=None):
        if progressCallback:
            progressCallback("0%")

        logging.debug("Initializing graph...")
        if darkMode:
            colors = self.colorsDarkMode
        else:
            colors = self.colorsLightMode

        fig = plt.figure(0) # Main figure
        rainAxis = fig.add_subplot(111)

        # set font sizes
        plt.rcParams.update({'font.size': fontSize}) # Temperature Y axis and day names
        rainAxis.tick_params(axis='y', labelsize=fontSize) # Rain Y axis
        plt.xticks(fontsize=fontSize) # Time axis


        if not graphWidth:
            graphWidth = 1280
        if not graphHeight:
            graphHeight = 300
        logging.debug("Graph size: %d x %d pixel" % (graphWidth, graphHeight))
        fig.set_size_inches(float(graphWidth)/fig.get_dpi(), float(graphHeight)/fig.get_dpi())


        # Plot dimension and borders
        bbox = rainAxis.get_window_extent().transformed(fig.dpi_scale_trans.inverted())
        width, height = bbox.width * fig.dpi, bbox.height * fig.dpi # plot size in pixel

        plt.margins(x=0)
        rainAxis.margins(x=0)

        plt.subplots_adjust(left=40/width, right=1-40/width, top=1-35/height, bottom=40/height)

        bbox = rainAxis.get_window_extent().transformed(fig.dpi_scale_trans.inverted())
        width, height = bbox.width * fig.dpi, bbox.height * fig.dpi # plot size in pixel
        xPixelsPerDay = width / data["noOfDays"]
        
        # Dimensions of the axis in pixel
        firstDayX = math.ceil(bbox.x0 * fig.dpi)
        firstDayY = math.ceil(bbox.y0 * fig.dpi)
        dayWidth = math.floor((bbox.x1 - bbox.x0) * fig.dpi) / data["noOfDays"]
        dayHeight = math.floor((bbox.y1 - bbox.y0) * fig.dpi)   

        # Show gray background on every 2nd day
        for day in range(0, data["noOfDays"], 2):
            plt.axvspan(data["timestamps"][0 + day * 24], data["timestamps"][23 + day * 24] + 3600, facecolor='gray', alpha=0.2)


        # Time axis and ticks
        plt.xticks(data["timestamps"][::timeDivisions], data["formatedTime"][::timeDivisions])
        rainAxis.tick_params(axis='x', colors=colors["x-axis"])

        # Rain (data gets splitted to stacked bars)
        logging.debug("Creating rain plot...")
        rainBars = [0] * len(self.rainColorSteps)

        for i in range(0, len(self.rainColorSteps)):
            rainBars[i] = []

        if progressCallback:
            progressCallback("20%")

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

        rainAxis.bar(data["timestamps"], rainBars[0], width=3000, color=self.rainColors[0], align='edge')
        bottom = [0] * len(rainBars[0])
        for i in range(1, len(self.rainColorSteps)):
            bottom = np.add(bottom, rainBars[i-1]).tolist()
            rainAxis.bar(data["timestamps"], rainBars[i], bottom=bottom, width=3000, color=self.rainColors[i], align='edge')

        rainAxis.tick_params(axis='y', labelcolor=colors["rain-axis"], width=0, length=8)
        rainYRange = plt.ylim()
        rainScaleMax = max(data["rainfall"]) + 1 # Add a bit to make sure we do not bang our head

        if measuredRain:
            measRainTime, measRain = measuredRain
            measRainTime = [t + self.utcOffset * 3600 for t in measRainTime]
            rainScaleMax = max(rainScaleMax, max(measRain) + 1)


        plt.ylim(0, rainScaleMax)
        rainAxis.locator_params(axis='y', nbins=7)
        # TODO find a better way than rounding 
        rainAxis.yaxis.set_major_formatter(FormatStrFormatter('%0.1f'))

        # Rain color bar as y axis
        plt.xlim(data["timestamps"][0], data["timestamps"][-2] + (data["timestamps"][1] - data["timestamps"][0]))
        pixelToRainX = 1 / xPixelsPerDay * (data["timestamps"][23] - data["timestamps"][0])
        x = data["timestamps"][-2] + (data["timestamps"][1] - data["timestamps"][0]) # end of x
        w = 7 * pixelToRainX

        for i in range(0, len(self.rainColorSteps)):
            y = self.rainColorSteps[i] - self.rainColorStepSizes[i]
            if y > rainScaleMax:
                break
            h = self.rainColorSteps[i] + self.rainColorStepSizes[i]
            if y + h >= rainScaleMax: # reached top
                h = rainScaleMax - y
            rainScaleBar = Rectangle((x, y), w, h, fc=self.rainColors[i], alpha=1)
            rainAxis.add_patch(rainScaleBar)
            rainScaleBar.set_clip_on(False)

        rainScaleBorder = Rectangle((x, 0), w, rainScaleMax, fc="black", fill=False, alpha=1)
        rainAxis.add_patch(rainScaleBorder)
        rainScaleBorder.set_clip_on(False)


        # Rain variance
        if rainVariance:
            rainfallVarianceAxis = rainAxis.twinx()  # instantiate a second axes that shares the same x-axis
            rainfallVarianceAxis.axes.yaxis.set_visible(False)

            timestampsCentered = [i + 1500 for i in data["timestamps"]]
            rainfallVarianceMin = np.subtract(np.array(data["rainfall"]), np.array(data["rainfallVarianceMin"]))
            rainfallVarianceMax = np.subtract(np.array(data["rainfallVarianceMax"]), np.array(data["rainfall"]))
            rainfallVarianceAxis.errorbar(timestampsCentered, data["rainfall"], yerr=[rainfallVarianceMin, rainfallVarianceMax],
                    fmt="none", elinewidth=1, alpha=0.5, ecolor='black', capsize=3)
            plt.ylim(0, rainScaleMax)


        # Show when the model was last calculated
        timestampLocal = data["modelCalculationTimestamp"] + self.utcOffset * 3600
        #l = mlines.Line2D([timestampLocal, timestampLocal], [rainYRange[0], rainScaleMax])
        #rainAxis.add_line(l)
        #rainAxis.plot([timestampLocal], [(rainScaleMax-rainYRange[0])/40], '^', color='blue', linewidth=2)
        rainAxis.plot([timestampLocal], [rainScaleMax* 0.97], 'v', color='green', markersize=10)


        if progressCallback:
            progressCallback("40%")

        # Temperature
        logging.debug("Creating temperature plot...")
        temperatureAxis = rainAxis.twinx()  # instantiate a second axes that shares the same x-axis
        temperatureAxis.plot(data["timestamps"], data["temperature"], label = "temperature", color=self.temperatureColor, linewidth=4)
        #temperatureAxis.set_ylabel('Temperature', color=self.temperatureColor)
        temperatureAxis.tick_params(axis='y', labelcolor=colors["temperature-axis"])
        temperatureAxis.grid(True)


        # Position the Y Scales
        temperatureAxis.yaxis.tick_left()
        rainAxis.yaxis.tick_right()


        # Make sure the temperature scaling has a gap of 45 pixel, so we can fit the labels
        interimPixelToTemperature = (np.nanmax(data["temperature"]) - np.nanmin(data["temperature"])) / height
        extraYScaleGap = float(45) * interimPixelToTemperature
        temperatureScaleMin = np.nanmin(data["temperature"]) - extraYScaleGap
        temperatureScaleMax = np.nanmax(data["temperature"]) + extraYScaleGap


        if measuredTemperature:
            measTempTime, measTemperature = measuredTemperature
            measTempTime = [t + self.utcOffset * 3600 for t in measTempTime]
            temperatureScaleMin = min(temperatureScaleMin, min(measTemperature) - extraYScaleGap)
            temperatureScaleMax = max(temperatureScaleMax, max(measTemperature) + extraYScaleGap)


        plt.ylim(temperatureScaleMin, temperatureScaleMax)
        temperatureAxis.locator_params(axis='y', nbins=6)
        temperatureAxis.yaxis.set_major_formatter(FormatStrFormatter('%0.1f'))
        pixelToTemperature = (temperatureScaleMax - temperatureScaleMin) / height


        # Temperature variance
        temperatureVarianceAxis = temperatureAxis.twinx()  # instantiate a second axes that shares the same x-axis
        temperatureVarianceAxis.axes.yaxis.set_visible(False)

        temperatureVarianceAxis.fill_between(data["timestamps"], data["temperatureVarianceMin"], data["temperatureVarianceMax"], facecolor=self.temperatureColor, alpha=0.2)
        temperatureVarianceAxis.tick_params(axis='y', labelcolor=self.temperatureColor)
        plt.ylim(temperatureScaleMin, temperatureScaleMax)


        if measuredRain:
            logging.debug("Measured rain data got provided, adding it to plot...") 
            #rainAxis.step(measRainTime, measRain, where='post', alpha=0.4, color='red') # Histogram curve
            rainAxis.fill_between(measRainTime, measRain, alpha=0.8, step="post", zorder=2) # Histogram infill

        if measuredTemperature:
            logging.debug("Measured temperature data got provided, adding it to plot...")
            temperatureVarianceAxis.plot(measTempTime, measTemperature, linewidth=4, color='coral', zorder=2)


        logging.debug("Adding various additional information to the graph...")

        if progressCallback:
            progressCallback("60%")

        # Find min/max for each day
        maxTemperatureOfDay = [None] * data["noOfDays"]
        minTemperatureOfDay = [None] * data["noOfDays"]
        if minMaxTemperature:
            da = DrawingArea(2, 2, 0, 0)
            da.add_artist(Circle((1, 1), 4, color=self.temperatureColor, fc="white", lw=2))
            for day in range(0, data["noOfDays"]):
                maxTemperatureOfDay[day] = {"data": -100, "timestamp": 0}
                minTemperatureOfDay[day] = {"data": +100, "timestamp": 0}
                for h in range(0, 24):
                    timestampOfHour = data["timestamps"][day * 24 + h]
                    temperatureOfHour = data["temperature"][day * 24 + h]
                    if temperatureOfHour > maxTemperatureOfDay[day]["data"]:
                        maxTemperatureOfDay[day]["data"] = temperatureOfHour
                        maxTemperatureOfDay[day]["timestamp"] = timestampOfHour
                        maxTemperatureOfDay[day]["xpixel"] = (timestampOfHour - data["timestamps"][0]) / (24*3600) * xPixelsPerDay
                        maxTemperatureOfDay[day]["ypixel"] = (temperatureOfHour - temperatureScaleMin) / (temperatureScaleMax - temperatureScaleMin) * height
                    if temperatureOfHour < minTemperatureOfDay[day]["data"]:
                        minTemperatureOfDay[day]["data"] = temperatureOfHour
                        minTemperatureOfDay[day]["timestamp"] = timestampOfHour
                        minTemperatureOfDay[day]["xpixel"] = (timestampOfHour - data["timestamps"][0]) / (24*3600) * xPixelsPerDay
                        minTemperatureOfDay[day]["ypixel"] = (temperatureOfHour - temperatureScaleMin) / (temperatureScaleMax - temperatureScaleMin) * height

                if day < maximumNumberOfDays-1: # We can also add the first hour of the next day (except on the last day)
                    timestampOfHour = data["timestamps"][(day + 1) * 24]
                    temperatureOfHour = data["temperature"][(day + 1) * 24]
                    if temperatureOfHour > maxTemperatureOfDay[day]["data"]:
                        maxTemperatureOfDay[day]["data"] = temperatureOfHour
                        maxTemperatureOfDay[day]["timestamp"] = timestampOfHour
                        maxTemperatureOfDay[day]["xpixel"] = (timestampOfHour - data["timestamps"][0]) / (24*3600) * xPixelsPerDay
                        maxTemperatureOfDay[day]["ypixel"] = (temperatureOfHour - temperatureScaleMin) / (temperatureScaleMax - temperatureScaleMin) * height
                    if temperatureOfHour < minTemperatureOfDay[day]["data"]:
                        minTemperatureOfDay[day]["data"] = temperatureOfHour
                        minTemperatureOfDay[day]["timestamp"] = timestampOfHour
                        minTemperatureOfDay[day]["xpixel"] = (timestampOfHour - data["timestamps"][0]) / (24*3600) * xPixelsPerDay
                        minTemperatureOfDay[day]["ypixel"] = (temperatureOfHour - temperatureScaleMin) / (temperatureScaleMax - temperatureScaleMin) * height


            # Mark min/max temperature per day
            for day in range(0, data["noOfDays"]):
                dayXPixelMin = day * xPixelsPerDay
                dayXPixelMax = (day + 1) * xPixelsPerDay - 1

                if day == data["noOfDays"]-1 or maxTemperatureOfDay[day]["xpixel"] != maxTemperatureOfDay[day+1]["xpixel"]: # Prevent multiple circles/lables for same spot (00:00/24:00)
                    # Max Temperature Circles
                    temperatureVarianceAxis.add_artist(AnnotationBbox(da, (maxTemperatureOfDay[day]["timestamp"], maxTemperatureOfDay[day]["data"]), xybox=(maxTemperatureOfDay[day]["timestamp"], maxTemperatureOfDay[day]["data"]), xycoords='data', boxcoords=("data", "data"), frameon=False))

                    # Max Temperature Labels
                    text = str(int(round(maxTemperatureOfDay[day]["data"], 0))) + "°C"
                    f = plt.figure(1) # Temporary figure to get the dimensions of the text label
                    t = plt.text(0, 0, text, weight='bold')
                    temporaryLabel = t.get_window_extent(renderer=f.canvas.get_renderer())
                    plt.figure(0) # Select Main figure again

                    # Check if text is fully within the day (x axis)
                    if maxTemperatureOfDay[day]["xpixel"] - temporaryLabel.width / 2 < dayXPixelMin: # To far left
                        maxTemperatureOfDay[day]["xpixel"] = dayXPixelMin + temporaryLabel.width / 2 + self.textShadowWidth / 2
                    if maxTemperatureOfDay[day]["xpixel"] + temporaryLabel.width / 2 > dayXPixelMax: # To far right
                        maxTemperatureOfDay[day]["xpixel"] = dayXPixelMax - temporaryLabel.width / 2 - self.textShadowWidth / 2

                    temperatureVarianceAxis.annotate(text, xycoords=('axes pixels'), xy=(maxTemperatureOfDay[day]["xpixel"], maxTemperatureOfDay[day]["ypixel"] + 8),
                                                    ha="center", va="bottom", color=colors["temperature-label"], weight='bold',
                                                    path_effects=[path_effects.withStroke(linewidth=self.textShadowWidth, foreground="w")])

                if day == data["noOfDays"]-1 or minTemperatureOfDay[day]["xpixel"] != minTemperatureOfDay[day+1]["xpixel"]: # Prevent multiple circles/lables for same spot (00:00/24:00)
                    # Min Temperature Circles
                    temperatureVarianceAxis.add_artist(AnnotationBbox(da, (minTemperatureOfDay[day]["timestamp"], minTemperatureOfDay[day]["data"]), xybox=(minTemperatureOfDay[day]["timestamp"], minTemperatureOfDay[day]["data"]), xycoords='data', boxcoords=("data", "data"), frameon=False))

                    # Min Temperature Labels
                    text = str(int(round(minTemperatureOfDay[day]["data"], 0))) + "°C"
                    f = plt.figure(1) # Temporary figure to get the dimensions of the text label
                    t = plt.text(0, 0, text, weight='bold')
                    temporaryLabel = t.get_window_extent(renderer=f.canvas.get_renderer())
                    plt.figure(0) # Select Main figure again

                    # Check if text is fully within the day (x axis)
                    if minTemperatureOfDay[day]["xpixel"] - temporaryLabel.width / 2 < dayXPixelMin: # To far left
                        minTemperatureOfDay[day]["xpixel"] = dayXPixelMin + temporaryLabel.width / 2 + self.textShadowWidth / 2
                    if minTemperatureOfDay[day]["xpixel"] + temporaryLabel.width / 2 > dayXPixelMax: # To far right
                        minTemperatureOfDay[day]["xpixel"] = dayXPixelMax - temporaryLabel.width / 2 - self.textShadowWidth / 2

                    temperatureVarianceAxis.annotate(text, xycoords=('axes pixels'), xy=(minTemperatureOfDay[day]["xpixel"], minTemperatureOfDay[day]["ypixel"] - 12),
                                                    ha="center", va="top", color=colors["temperature-label"], weight='bold',
                                                    path_effects=[path_effects.withStroke(linewidth=self.textShadowWidth, foreground="w")])

        if progressCallback:
            progressCallback("80%")

        # Print day names
        for day in range(0, data["noOfDays"]):
            rainAxis.annotate(data['dayNames'][day], xy=(day * xPixelsPerDay + xPixelsPerDay / 2, -45), xycoords='axes pixels', ha="center", weight='bold', color=colors["x-axis"])


        # Show y-axis units
        rainAxis.annotate("mm\n/h", linespacing = 0.8, xy=(width + 25, height + 12), xycoords='axes pixels', ha="center", color=colors["rain-axis"])
        rainAxis.annotate("°C", xy=(-20, height + 10), xycoords='axes pixels', ha="center", color=colors["temperature-axis"])


        # Show Symbols above the graph
        for i in range(0, len(data["symbols"]), symbolDivision):
            symbolFile = os.path.dirname(os.path.realpath(__file__)) + "/symbols/" + str(data["symbols"][i]) + ".png"
            if not os.path.isfile(symbolFile):
                logging.warning("The symbol file %s seems to be missing. Please check the README.md!" % symbolFile)
                continue
            symbolImage = mpimg.imread(symbolFile)
            imagebox = OffsetImage(symbolImage, zoom=symbolZoom / 1.41 * 0.15)
            xyPos = ((data["symbolsTimestamps"][i] - data["symbolsTimestamps"][0]) / (24*3600) + len(data["symbols"])/24/6/data["noOfDays"]) * xPixelsPerDay, height + 22
            ab = AnnotationBbox(imagebox, xy=xyPos, xycoords='axes pixels', frameon=False)
            rainAxis.add_artist(ab)


        # Show city name in graph
        if showCityName:
            logging.debug("Adding city name to plot...")
            text = rainAxis.annotate(self.cityName, xy=(width - 5, height - 18), color='gray', ha='right', linespacing = 0.8, xycoords='axes pixels')
            text.set_path_effects([path_effects.Stroke(linewidth=self.textShadowWidth, foreground='white'), path_effects.Normal()])

        # Show data copyright graph
        if not hideDataCopyright:
            logging.debug("Adding data copyright to plot...")
            text = rainAxis.annotate("Data © by Meteoswiss", xy=(width - 5, 5), color='gray', ha='right', linespacing = 0.8, xycoords='axes pixels')
            text.set_path_effects([path_effects.Stroke(linewidth=self.textShadowWidth, foreground='white'), path_effects.Normal()])

        if progressCallback:
            progressCallback("90%")

        # Save the graph in a png image file
        logging.debug("Saving graph to %s" % outputFilename)
        plt.savefig(outputFilename, facecolor=colors["background"])
        plt.close()

        # Write Meta Data
        if writeMetaData:
            logging.debug("Saving Meta Data to %s" % writeMetaData)
            metaData = {}
            metaData['city'] = self.cityName
            metaData['imageHeight'] = graphHeight
            metaData['imageWidth'] = graphWidth
            metaData['firstDayX'] = firstDayX
            metaData['firstDayY'] = firstDayY
            metaData['dayWidth'] = dayWidth
            metaData['dayHeight'] = dayHeight
            metaData['modelTimestamp'] = self.data["modelCalculationTimestamp"] # Seconds in UTC
            metaData['forecastGenerationTimestamp'] = int(datetime.datetime.now().timestamp())
            with open(writeMetaData, 'w') as metaFile:
                json.dump(metaData, metaFile)

        if progressCallback:
            progressCallback("100%")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Script to fetch the MeteoSwiss Weather Forecast data and generate a graph')
    parser.add_argument('-v', action='store_true', help='Verbose output')
    parser.add_argument('-z', '--zip-code', action='store', type=int, required=True, help='Zip Code of the city to be represented')
    parser.add_argument('-f', '--file', type=argparse.FileType('w'), required=True, help='File name of the graph to be written (PNG)')
    parser.add_argument('-m', '--meta', type=argparse.FileType('w'), required=True, help='File name with meta data to be written (JSON)')
    parser.add_argument('--days-to-show', action='store', type=int, choices=range(1, 8), help='Number of days to show. If not set, use all data')
    parser.add_argument('--height', action='store', type=int, help='Height of the graph in pixel')
    parser.add_argument('--width', action='store', type=int, help='Width of the graph in pixel', default=1920)
    parser.add_argument('--utc-offset', action='store', type=int, help='Offset to UTC, only needed if system does not know it (eg in a docker container)', default=None)
    parser.add_argument('--time-divisions', action='store', type=int, help='Distance in hours between time labels', default=6)
    parser.add_argument('--dark-mode', action='store_true', help='Use dark colors')
    parser.add_argument('--font-size', action='store', type=int, help='Font Size', default=12)
    parser.add_argument('--min-max-temperatures', action='store_true', help='Show min/max temperature per day')
    parser.add_argument('--rain-variance', action='store_true', help='Show rain variance')
    parser.add_argument('--locale', action='store', help='Used localization of the date, eg. en_US.utf8', default="en_US.utf8")
    parser.add_argument('--date-format', action='store', help='Format of the dates, eg. \"%%A, %%-d. %%B\", see https://strftime.org/ for details', default="%A, %-d. %B")
    parser.add_argument('--time-format', action='store', help='Format of the times, eg. \"%%H:%%M\", see https://strftime.org/ for details', default="%H:%M")
    parser.add_argument('--symbol-zoom', action='store', type=float, help='scaling of the symbols', default=1.0)
    parser.add_argument('--symbol-divisions', action='store', type=int, help='Only draw every x symbol (1 equals every 3 hours)', default=1)
    parser.add_argument('--city-name', action='store_true', help='Show the name of the city')
    parser.add_argument('--hide-data-copyright', action='store_false', help='Hide the data copyright. Please only do this for personal usage!')

    parser.add_argument('--measurement-data-db-host', action='store', help='DB host providing real local data')
    parser.add_argument('--measurement-data-db-port', action='store', type=int, help='DB port')
    parser.add_argument('--measurement-data-db-user', action='store', help='DB username')
    parser.add_argument('--measurement-data-db-password', action='store', help='DB password')


    args = parser.parse_args()

    logLevel = logging.INFO
    if args.v:
        logLevel = logging.DEBUG

    logging.basicConfig(format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%d-%b-%y %H:%M:%S', level=logLevel)
    logging.getLogger("matplotlib").setLevel(logging.WARNING) # hiding the debug messages from the matplotlib
    logging.getLogger("PIL").setLevel(logging.WARNING) # hiding the debug messages from the PIL


    if args.utc_offset:
        utcOffset = args.utc_offset
    else:
        utcOffset = getCurrentUtcOffset()

    try:
        meteoSwissForecast = MeteoSwissForecast(zipCode=args.zip_code, utcOffset=utcOffset)
    except Exception as e:
        logging.error("An error occurred: %s" % e)
        exit(1)

    try:
        dataUrl = meteoSwissForecast.getDataUrl()
    except Exception as e:
        logging.error("An error occurred: %s" % e)
        exit(1)

    try:
        forecastData = meteoSwissForecast.collectData(dataUrl=dataUrl, daysToUse=args.days_to_show, timeFormat=args.time_format, dateFormat=args.date_format, localeAlias=args.locale)
    except Exception as e:
        logging.error("An error occurred: %s" % e)
        exit(1)

    #pprint.pprint(forecastData)
    #meteoSwissForecast.exportForecastData(forecastData, "./forecast_" + args.zip_code + ".json")
    #forecastData = meteoSwissForecast.importForecastData("./forecast.json")

    #if args.measurement_data_db_host != None and args.measurement_data_db_port != None and args.measurement_data_db_user != None and args.measurement_data_db_password != None:  
        logging.debug("Using Measurement Data to show real local data")
    if True:
        try:
            #mdp = measurementDataProvider.MeasurementDataProvider(measurementDataDbHost=args.measurement_data_db_host, measurementDataDbPort=args.measurement_data_db_port, measurementDataDbUser=args.measurement_data_db_user, measurementDataDbPassword=args.measurement_data_db_password)

            mdp = measurementDataProvider.MeasurementDataProvider(measurementDataDbHost='192.168.1.99', measurementDataDbPort=5086, measurementDataDbUser='meteoswiss-forecast', measurementDataDbPassword='wrewygewtcqxgewtcxeqgwq3')

            try:
                logging.debug("Fetching sensor data (rain)...")
                measuredRain = mdp.getMeasurement(sensor="regen_pro_h", groupingInterval=10, fill="previous")
            except Exception as e:
                logging.error("An error occurred: %s" % e)
                measuredRain = None
        
            try:
                logging.debug("Fetching sensor data (temperature)...")
                #measuredTemperature = mdp.getMeasurement(sensor="aussentemperatur", groupingInterval=10, fill="previous")
                #measuredTemperature = mdp.getMeasurement(sensor="temperatur_vor_dem_haus", groupingInterval=10, fill="previous")
                measuredTemperature = mdp.getMeasurement(sensor="temperatur_im_garten_schopf", groupingInterval=10, fill="previous")
                measuredTemperature[1] = measuredTemperature[1] - 6
            except Exception as e:
                logging.error("An error occurred: %s" % e)
                measuredTemperature = None
        except Exception as e:
            logging.error("Failed to connect to Measurement Data DB: %s" % e)
            measuredRain = None
            measuredTemperature = None
    else:
        measuredRain = None
        measuredTemperature = None

    meteoSwissForecast.generateGraph(data=forecastData, outputFilename=args.file.name, timeDivisions=args.time_divisions, graphWidth=args.width, graphHeight=args.height, darkMode=args.dark_mode, rainVariance=args.rain_variance, minMaxTemperature=args.min_max_temperatures, fontSize=args.font_size, symbolZoom=args.symbol_zoom, symbolDivision=args.symbol_divisions, showCityName=args.city_name, hideDataCopyright=args.hide_data_copyright, writeMetaData=args.meta.name, measuredRain=measuredRain, measuredTemperature=measuredTemperature)
