from urllib.request import Request, urlopen
import json
import pprint
import time
import datetime
import pytz
import locale
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.collections import PatchCollection
from matplotlib.patches import Circle, Rectangle
from matplotlib.offsetbox import TextArea, DrawingArea, OffsetImage, AnnotationBbox
import matplotlib.lines as mlines
import concurrent.futures
import functools
import matplotlib.patheffects as path_effects
from matplotlib.ticker import FormatStrFormatter
import numpy as np
import math
import logging
import csv
import calendar
import re
import io
import argparse
import os.path
import json
from scipy import interpolate
# import measurementDataProvider


#from svglib.svglib import svg2rlg
#from reportlab.graphics import renderPM
#import tempfile


# Meteoswiss only provides the data of the up to 9 days.
maximumNumberOfDays = 9


def _download(url):
    logging.debug("Downloading %r..." % url)
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urlopen(req) as response:
            content = response.read()
    except Exception as e:
        raise Exception("Failed to fetch URL (%r): %r" % (url, e))
    logging.debug("Download completed %r: %.2f MB" % (url, len(content) / (1024 * 1024)))
    return content


@functools.lru_cache(maxsize=12)
def _download_cached(url):
    return _download(url)


# Returns the current UTC offset as integer value.
def getCurrentUtcOffset():
    utcOffset = datetime.datetime.now(pytz.timezone('Europe/Zurich')).strftime('%z')
    utcOffset = int(int(utcOffset)/100)
    print("Current UTC Offset: %d" % utcOffset)
    return utcOffset


class MeteoSwissForecast:
    # Constants
    stacCollectionUrl = "https://data.geo.admin.ch/api/stac/v1/collections/ch.meteoschweiz.ogd-local-forecasting"
    pointMetaUrl = "https://data.geo.admin.ch/ch.meteoschweiz.ogd-local-forecasting/ogd-local-forecasting_meta_point.csv"

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
                        datetime.datetime.fromtimestamp(ts, datetime.UTC)).total_seconds()
            self.utcOffset = int(utcOffset / 3600) # in hours
        else:
            self.utcOffset = utcOffset

        logging.debug("UTC offset: %d" % self.utcOffset)


    def getUrlJson(self, url):
        return json.loads(_download(url).decode('utf-8'))


    def getUrlText(self, url):
        return io.TextIOWrapper(io.BytesIO(_download_cached(url)), encoding='latin1')


    def getForecastDataUrl(self):
        if not hasattr(self, 'latestRun') or not self.latestRun:
            self.getLatestForecastRun()
        href = self.getParameterAssetUrl('tre200h0', self.latestRun)
        logging.debug("The data URL is: %r" % href)
        return href


    def getCityName(self):
        logging.debug("Loading point metadata from %r..." % self.pointMetaUrl)
        handle = self.getUrlText(self.pointMetaUrl)
        try:
            reader = csv.reader(handle, delimiter=';')
            header = next(reader)
            pointIdIdx = header.index('point_id')
            pointTypeIdx = header.index('point_type_id')
            postalCodeIdx = header.index('postal_code')
            pointNameIdx = header.index('point_name')
            for row in reader:
                if row[postalCodeIdx] == str(self.zipCode) and row[pointTypeIdx] == '2':
                    self.pointId = row[pointIdIdx]
                    self.pointType = row[pointTypeIdx]
                    self.cityName = row[pointNameIdx]
                    logging.debug("The location is: %s" % self.cityName)
                    return self.cityName
        finally:
            handle.close()
        raise Exception("Unknown zip code: %d" % self.zipCode)


    def getLatestForecastRun(self):
        itemsUrl = self.stacCollectionUrl + "/items"
        logging.debug("Loading STAC items from %r..." % itemsUrl)
        items = self.getUrlJson(itemsUrl)
        candidates = [f for f in items.get('features', []) if f.get('assets')]
        if not candidates:
            raise Exception("No STAC items with assets found")

        # Choose the latest run that has every parameter we need
        requiredParameters = [
            'tre200h0', 'treq10h0', 'treq90h0', 'rre150h0',
            'rreq10h0', 'rreq90h0', 'fu3010h0', 'fu3010h1',
            'sre000h0', 'jww003i0',
        ]
        bestRun = None
        bestItem = None
        for item in candidates:
            runs = {}
            for key in item['assets']:
                m = re.search(r'\.(\d{12})\.(\w+)\.csv$', key)
                if not m:
                    continue
                run, parameter = m.group(1), m.group(2)
                runs.setdefault(run, set()).add(parameter)
            for run, parameters in runs.items():
                if all(p in parameters for p in requiredParameters):
                    if bestRun is None or run > bestRun:
                        bestRun = run
                        bestItem = item

        if bestRun is None:
            raise Exception("No forecast run with all required parameters found")

        self.stacItemId = bestItem['id']
        self.itemAssets = bestItem['assets']
        self.latestRun = bestRun
        logging.debug("Using forecast run %r" % self.latestRun)
        return self.latestRun


    def getParameterAssetUrl(self, parameter, run=None):
        if not hasattr(self, 'itemAssets') or not self.itemAssets:
            self.getLatestForecastRun()
        candidates = {}
        for key, asset in self.itemAssets.items():
            if not key.endswith('.' + parameter + '.csv'):
                continue
            m = re.search(r'\.(\d{12})\.' + parameter + r'\.csv$', key)
            if not m:
                continue
            candidates[m.group(1)] = asset['href']
        if not candidates:
            raise Exception("No asset found for parameter %r" % parameter)
        if run is not None:
            if run in candidates:
                return candidates[run]
            raise Exception("Run %r not available for parameter %r" % (run, parameter))
        return candidates[max(candidates)]


    def _extractRun(self, forecastDataUrl):
        if forecastDataUrl is None:
            return None
        # Accept a raw 12 digit run or a full asset URL
        if re.match(r'^\d{12}$', str(forecastDataUrl)):
            return forecastDataUrl
        m = re.search(r'\.(\d{12})\.\w+\.csv', str(forecastDataUrl))
        if m:
            return m.group(1)
        return None


    def _parseDate(self, dateStr):
        return calendar.timegm(datetime.datetime.strptime(dateStr, "%Y%m%d%H%M").timetuple())


    def loadParameterSeries(self, url, parameter, asFloat=True):
        logging.debug("Loading %s from %r..." % (parameter, url))
        handle = self.getUrlText(url)
        try:
            reader = csv.reader(handle, delimiter=';')
            header = next(reader)
            pointIdIdx = header.index('point_id')
            pointTypeIdx = header.index('point_type_id')
            dateIdx = header.index('Date')
            valueIdx = header.index(parameter)
            series = {}
            for row in reader:
                if row[pointIdIdx] != self.pointId:
                    continue
                if row[pointTypeIdx] != self.pointType:
                    continue
                dateStr = row[dateIdx]
                value = row[valueIdx]
                if not dateStr:
                    continue
                if not value:
                    parsed = None
                else:
                    try:
                        if asFloat:
                            parsed = float(value)
                        else:
                            parsed = int(value)
                    except ValueError:
                        parsed = None
                series[dateStr] = parsed
            if not series:
                raise Exception("No data found for point %s/%s in %s" % (self.pointId, self.pointType, url))
            return series
        finally:
            handle.close()


    def getModelCalculationTimestamp(self, forecastDataUrl):
        run = self._extractRun(forecastDataUrl)
        if run is None:
            run = self.getLatestForecastRun()
        return int(calendar.timegm(datetime.datetime.strptime(run, "%Y%m%d%H%M").timetuple()))


    def collectData(self, forecastDataUrl=None, daysToUse=7, timeFormat="%H:%M", dateFormat="%A, %-d. %B", localeAlias="en_US.utf8", showSunshine=False, rainVariance=False):
        run = self._extractRun(forecastDataUrl)
        if run is None:
            run = self.getLatestForecastRun()
        else:
            self.latestRun = run
            if not hasattr(self, 'itemAssets') or not self.itemAssets:
                self.getLatestForecastRun()

        logging.debug("%r, %r" % (daysToUse, maximumNumberOfDays))
        if daysToUse > maximumNumberOfDays:
            daysToUse = maximumNumberOfDays
            logging.warning("Limiting days to be shown to %d days!" % maximumNumberOfDays)

        parameterConfig = [
            ('temperature', 'tre200h0', True),
            ('temperatureVarianceMin', 'treq10h0', True),
            ('temperatureVarianceMax', 'treq90h0', True),
            ('rainfall', 'rre150h0', True),
            ('rainfallVarianceMax', 'rreq90h0', True),
            ('wind', 'fu3010h0', True),
            ('symbols', 'jww003i0', False),
        ]

        if rainVariance:
            parameterConfig.append(('rainfallVarianceMin', 'rreq10h0', True))
        if showSunshine:
            parameterConfig.append(('sunshine', 'sre000h0', False))

        series = {}
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(self.loadParameterSeries, self.getParameterAssetUrl(parameter, run), parameter, asFloat): field
                for field, parameter, asFloat in parameterConfig
            }
            for future in concurrent.futures.as_completed(futures):
                field = futures[future]
                series[field] = future.result()

        symbolsSeries = series['symbols']

        # Use the temperature time series as the reference time line
        allDates = sorted(series['temperature'].keys())
        if not allDates:
            raise Exception("No forecast data available for point %s" % self.pointId)

        # Prefer to start on a 00:00 local-time full-day boundary
        # (the CSV Date is the end of the hour, so the display time is one hour earlier)
        startIndex = 0
        for i, date in enumerate(allDates):
            utcTs = self._parseDate(date)
            localTs = utcTs + self.utcOffset * 3600
            displayTs = localTs - 3600
            if displayTs % 86400 == 0:
                startIndex = i
                break

        availableDates = allDates[startIndex:]
        fullDays = max(1, len(availableDates) // 24)
        self.days = min(daysToUse, fullDays, maximumNumberOfDays)
        logging.debug("The forecast contains data for %d days" % self.days)

        wantedCount = self.days * 24
        if self.days < maximumNumberOfDays and len(availableDates) > wantedCount:
            wantedCount += 1
        selectedDates = availableDates[:wantedCount]
        if not selectedDates:
            raise Exception("No forecast data available for the requested days")

        self.data["modelCalculationTimestamp"] = self.getModelCalculationTimestamp(forecastDataUrl if forecastDataUrl else run)

        try:
            locale.setlocale(locale.LC_ALL, localeAlias)
        except Exception as e:
            logging.warning("Unable to uses locale \"%s\": %s" % (localeAlias, e))

        dayNames = []
        formatedTime = []
        timestamps = []
        dayTimestamps = {}
        for date in selectedDates:
            utcTs = self._parseDate(date)
            localTs = utcTs + self.utcOffset * 3600
            displayTs = localTs - 3600
            dayTimestamps[date] = displayTs
            timestamps.append(displayTs)
            formatedTime.append(datetime.datetime.fromtimestamp(displayTs, datetime.UTC).strftime(timeFormat))

        for day in range(0, self.days):
            dayNames.append(datetime.datetime.fromtimestamp(timestamps[day * 24], datetime.UTC).strftime(dateFormat))

        rainfall = [series['rainfall'].get(d) for d in selectedDates]
        temperature = [series['temperature'].get(d) for d in selectedDates]
        rainfallVarianceMin = [series['rainfallVarianceMin'].get(d) for d in selectedDates] if rainVariance else [None] * len(selectedDates)
        rainfallVarianceMax = [series['rainfallVarianceMax'].get(d) for d in selectedDates]
        temperatureVarianceMin = [series['temperatureVarianceMin'].get(d) for d in selectedDates]
        temperatureVarianceMax = [series['temperatureVarianceMax'].get(d) for d in selectedDates]
        wind = [series['wind'].get(d) for d in selectedDates]
        sunshine = [series['sunshine'].get(d) for d in selectedDates] if showSunshine else [None] * len(selectedDates)

        symbols = []
        symbolsTimestamps = []
        for day in range(0, self.days):
            for h in [0, 3, 6, 9, 12, 15, 18, 21]:
                idx = day * 24 + h
                if idx >= self.days * 24:
                    continue
                date = selectedDates[idx]
                value = symbolsSeries.get(date)
                if value is not None:
                    symbols.append(value)
                    symbolsTimestamps.append(dayTimestamps[date])

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
        self.data["sunshine"] = sunshine
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
                if key != "forecastDataUrl":
                    self.data[key] =  [np.nan if v is None else v for v in self.data[key]]
            except:
                pass

        logging.debug("All data parsed")

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
                # timestamps mark the start of the hour, add 3600 to get the end
                t = math.floor((forecastData['timestamps'][i] + 3600 - timestampNow) / 3600)
                if t > -1: # now or in future
                    nextRain = t
                    break

        nextPossibleRain = None
        for i in range(len(forecastData['rainfallVarianceMax'])):
            # print(i, forecastData['timestamps'][i], forecastData['formatedTime'][i], forecastData['rainfallVarianceMax'][i])
            if forecastData['rainfallVarianceMax'][i] > 0:
                # timestamps mark the start of the hour, add 3600 to get the end
                t = math.floor((forecastData['timestamps'][i] + 3600 - timestampNow) / 3600)
                if t > -1: # now or in future
                    nextPossibleRain = t
                    break

        return nextRain, nextPossibleRain


    """
    Generates the graphic containing the forecast
    """
    def generateGraph(self, data=None, outputFilename=None, timeDivisions=6, graphWidth=1920, graphHeight=300, darkMode=False, rainVariance=False, minMaxTemperature=False, fontSize=12, symbolZoom=1.0, symbolDivision=1, showCityName=False, hideDataCopyright=False, writeMetaData=None, progressCallback=None, measuredRain=None, measuredTemperature=None, showSunshine=False, sunshineBars=False):
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

        rainAxis.tick_params(axis='y', labelcolor=colors["rain-axis"], width=0, length=8)
        rainYRange = plt.ylim()
        rainScaleMax = max(data["rainfall"]) + 1 # Add a bit to make sure we do not bang our head

        # Sunshine visualization (drawn before rain to be behind)
        if showSunshine and "sunshine" in data:
            maxSunshineHeight = 0.99 * rainScaleMax
            sunshineHeight = [min(s / 60.0, 0.99) * maxSunshineHeight for s in data["sunshine"]]
            if sunshineBars:
                sunshinePatches = [Rectangle((t, 0), 3000, h, facecolor='#e8b400', edgecolor='none') for t, h in zip(data["timestamps"], sunshineHeight)]
                rainAxis.add_collection(PatchCollection(sunshinePatches, match_original=True, zorder=1))
            else:
                # Center the sunshine line/fill on each hour
                lineTimestamps = [t + 1800 for t in data["timestamps"]]
                # Create smooth spline interpolation
                timestamps = np.array(lineTimestamps)
                sunshine = np.array(sunshineHeight)
                # Use spline interpolation for smooth curve
                spline = interpolate.make_interp_spline(timestamps, sunshine, k=3)
                smooth_timestamps = np.linspace(timestamps.min(), timestamps.max(), 100)
                smooth_sunshine = spline(smooth_timestamps)
                # Clamp to maximum height to prevent spline overshoot
                smooth_sunshine = np.clip(smooth_sunshine, 0, maxSunshineHeight)
                rainAxis.fill_between(smooth_timestamps, 0, smooth_sunshine, color='#fff3b0', alpha=0.5, zorder=1)
                rainAxis.plot(smooth_timestamps, smooth_sunshine, color='#e8b400', linewidth=2, zorder=2)

        rainPatches = []
        bottom = [0] * len(rainBars[0])
        for i in range(0, len(self.rainColorSteps)):
            for t, h, b in zip(data["timestamps"], rainBars[i], bottom):
                if h > 0:
                    rainPatches.append(Rectangle((t, b), 3000, h, facecolor=self.rainColors[i], edgecolor='none'))
            if i < len(self.rainColorSteps) - 1:
                bottom = [b + h for b, h in zip(bottom, rainBars[i])]
        if rainPatches:
            rainAxis.add_collection(PatchCollection(rainPatches, match_original=True, zorder=3))

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
            # Use original variance data directly
            rainfallVarianceMin = data["rainfallVarianceMin"]
            rainfallVarianceMax = data["rainfallVarianceMax"]

            # Calculate variance ranges for errorbar
            errorbarMin = np.subtract(np.array(data["rainfall"]), np.array(rainfallVarianceMin))
            errorbarMin = [max(0, x) for x in errorbarMin]
            errorbarMax = np.subtract(np.array(rainfallVarianceMax), np.array(data["rainfall"]))
            errorbarMax = [max(0, x) for x in errorbarMax]

            # rainfallVarianceAxis.errorbar(timestampsCentered, data["rainfall"], yerr=[errorbarMin, errorbarMax],
                    # fmt="none", elinewidth=1, alpha=0.5, ecolor='darkgray', capsize=3)
            # Add variance bar starting from rainfallVarianceMin to rainfallVarianceMax
            varianceRange = np.subtract(rainfallVarianceMax, rainfallVarianceMin)
            rainfallVarianceAxis.bar(timestampsCentered, varianceRange, 
                    bottom=rainfallVarianceMin, width=3000, fill=False, edgecolor='darkgray', linewidth=1, alpha=0.5, zorder=4)
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
    parser.add_argument('--days-to-show', action='store', type=int, default=4, choices=range(1, maximumNumberOfDays+1), help='Number of days to show. If not set, use all data')
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
    parser.add_argument('--export-forecast-data', action='store_true', help='Export fetched forecast data to JSON file')
    parser.add_argument('--show-sunshine', action='store_true', help='Show sunshine in the background')
    parser.add_argument('--sunshine-bars', action='store_true', help='Show sunshine as bars instead of a smooth line/fill')

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
        forecastDataUrl = meteoSwissForecast.getForecastDataUrl()
    except Exception as e:
        logging.error("An error occurred: %s" % e)
        exit(1)

    try:
        forecastData = meteoSwissForecast.collectData(forecastDataUrl=forecastDataUrl, daysToUse=args.days_to_show, timeFormat=args.time_format, dateFormat=args.date_format, localeAlias=args.locale, showSunshine=args.show_sunshine, rainVariance=args.rain_variance)
    except Exception as e:
        logging.error("An error occurred: %s" % e)
        exit(1)

    #pprint.pprint(forecastData)
    if args.export_forecast_data:
        forecastDataFile = args.file.name.replace(".png", ".json")
        meteoSwissForecast.exportForecastData(forecastData, forecastDataFile)
    #forecastData = meteoSwissForecast.importForecastData("./forecast.json")

    #if args.measurement_data_db_host != None and args.measurement_data_db_port != None and args.measurement_data_db_user != None and args.measurement_data_db_password != None:  
    #    logging.debug("Using Measurement Data to show real local data")
#     if True:
#         try:
#             #mdp = measurementDataProvider.MeasurementDataProvider(measurementDataDbHost=args.measurement_data_db_host, measurementDataDbPort=args.measurement_data_db_port, measurementDataDbUser=args.measurement_data_db_user, measurementDataDbPassword=args.measurement_data_db_password)
# 
#             mdp = measurementDataProvider.MeasurementDataProvider(measurementDataDbHost='192.168.1.99', measurementDataDbPort=5086, measurementDataDbUser='meteoswiss-forecast', measurementDataDbPassword='wrewygewtcqxgewtcxeqgwq3')
# 
#             try:
#                 logging.debug("Fetching sensor data (rain)...")
#                 measuredRain = mdp.getMeasurement(sensor="regen_pro_h", groupingInterval=10, fill="previous")
#             except Exception as e:
#                 logging.error("An error occurred: %s" % e)
#                 measuredRain = None
#         
#             try:
#                 logging.debug("Fetching sensor data (temperature)...")
#                 #measuredTemperature = mdp.getMeasurement(sensor="aussentemperatur", groupingInterval=10, fill="previous")
#                 measuredTemperature = mdp.getMeasurement(sensor="temperatur_vor_dem_haus", groupingInterval=10, fill="previous")
#                 #measuredTemperature = mdp.getMeasurement(sensor="temperatur_im_garten_schopf", groupingInterval=10, fill="previous")
#             except Exception as e:
#                 logging.error("An error occurred: %s" % e)
#                 measuredTemperature = None
#         except Exception as e:
#             logging.error("Failed to connect to Measurement Data DB: %s" % e)
#             measuredRain = None
#             measuredTemperature = None
#     else:
    measuredRain = None
    measuredTemperature = None

    meteoSwissForecast.generateGraph(data=forecastData, outputFilename=args.file.name, timeDivisions=args.time_divisions, graphWidth=args.width, graphHeight=args.height, darkMode=args.dark_mode, rainVariance=args.rain_variance, minMaxTemperature=args.min_max_temperatures, fontSize=args.font_size, symbolZoom=args.symbol_zoom, symbolDivision=args.symbol_divisions, showCityName=args.city_name, hideDataCopyright=args.hide_data_copyright, writeMetaData=args.meta.name, measuredRain=measuredRain, measuredTemperature=measuredTemperature, showSunshine=args.show_sunshine, sunshineBars=args.sunshine_bars)
