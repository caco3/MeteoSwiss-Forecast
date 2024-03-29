#!/usr/bin/python
from http.server import BaseHTTPRequestHandler,HTTPServer
from urllib.parse import urlparse, parse_qs
from meteoswissForecast import MeteoSwissForecast
from markGraphic import markGraphic
import logging
import os
from os.path import exists
import json
import datetime, pytz
import measurementDataProvider

# Meteoswiss only provides the data of the up to 7 days.
maximumNumberOfDays = 7

def str2bool(v):
    return v.lower() in ("yes", "true", "t", "1")


# Returns the current UTC offset as integer value.
def getCurrentUtcOffset():
    utcOffset = datetime.datetime.now(pytz.timezone('Europe/Zurich')).strftime('%z')
    utcOffset = int(int(utcOffset)/100)
    print("Current UTC Offset: %d" % utcOffset)
    return utcOffset


# This class will handle any incoming request from
# a browser 
class myHandler(BaseHTTPRequestHandler):
    # Handler for the GET requests
    def do_GET(self):
        self.send_response(200)        
        
        parsed_url = urlparse(self.path)
        query = parse_qs(parsed_url.query)
        
        print("File: %s, query: %s" % (parsed_url.path, query), flush=True)
        
        if parsed_url.path == "/generate-forecast":
            self.generate(query)
        elif parsed_url.path == "/get-forecast":
            self.returnMarkedImage(query)
        elif parsed_url.path == "/get-metadata":
            self.returnMetaData(query)
        elif parsed_url.path == "/get-next-rain":
            self.returnNextRain(query)
        elif parsed_url.path == "/":
            self.showHelp(False)
        else:
            self.showHelp(True)

        
    def showHelp(self, invalid=True):
        print("Showing help")
        self.send_header('Content-type','text/html')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        self.wfile.write(b"<h1>Meteoswiss Forecast Generator</h1>\n")
        
        if invalid:
            self.wfile.write(b"<span style=\"color: red\">Invalid call!</span><br><br><hr><br>\n")
        
        self.wfile.write(b"The generation of the forcast takes a moment. Because of this, it is a two-step-process:<br>1. Generate a forecast for a Zip Code using the wanted configuration. This has only to be done once an hour, MeteoSwiss only re-runs the model every few hours.<br>2. Download the forecast as many times as you want, applying the same zip code and optionally a time mark.<br>\n")                
        self.wfile.write(b"Since every generated forecast is linked to its zip code, forecasts for differen cities can be provided at the same time.<br>\n")
        
        self.wfile.write(b"<h2>Generate</h2>\n")
        url = "generate-forecast?zip-code=8001"
        link = "<a href=\"" + url + "\">" + url + "</a>"
        self.wfile.write(bytes(link, 'utf-8'))
        
        self.wfile.write(b"<h3>Note</h3>\n")
        self.wfile.write(b"Depending on the number of days to show, this will take several seconds!\n")
        
        self.wfile.write(b"<h3>Parameters</h3>\n")
        self.wfile.write(b"<table>\n")
        self.wfile.write(b"<tr><td><b>zip-code:</b></td><td>Zip Code, eg. 8001</td><td>Mandatory</td></tr>\n")
        self.wfile.write(b"<tr><td><b>days-to-show:</b></td></td><td>Number of days to show (1..%d).</td><td>Optional, default: %d</td></tr>\n" % (maximumNumberOfDays, maximumNumberOfDays))
        self.wfile.write(b"<tr><td><b>height:</b></td><td>Height of the graph in pixel.</td><td>Optional, default: 300</td></tr>\n")
        self.wfile.write(b"<tr><td><b>width:</b></td><td>Width of the graph in pixel.</td><td>Optional, default: 1920</td></tr>\n")
        self.wfile.write(b"<tr><td><b>time-divisions:</b></td><td>Distance in hours between time labels.</td><td>Optional, default: 6</td></tr>\n")
        self.wfile.write(b"<tr><td><b>use-dark-mode:</b></td><td>Use dark colors.</td><td>Optional, default: False</td></tr>\n")
        self.wfile.write(b"<tr><td><b>font-size:</b></td><td>Font Size in pixel.</td><td>Optional, default: 12</td></tr>\n")
        self.wfile.write(b"<tr><td><b>show-min-max-temperatures:</b></td><td>Show min/max temperature per day.</td><td>Optional, default: False</td></tr>\n")
        self.wfile.write(b"<tr><td><b>show-rain-variance:</b></td><td>Show rain variance.</td><td>Optional, default: False</td></tr>\n")
        self.wfile.write(b"<tr><td><b>locale:</b></td><td>Used localization of the date, eg. en_US.utf8.</td><td>Optional, default: en_US.utf8</td></tr>\n")
        self.wfile.write(b"<tr><td><b>utc-offset:</b></td><td>UTC Offset in hours</td><td>Optional, default: Current Offset for Switzerland</td></tr>\n")
        self.wfile.write(b"<tr><td><b>date-format:</b></td><td>Format of the dates, eg. \"%%A, %%-d. %%B\", see https://strftime.org/ for details'.</td><td>Optional, default: %A, %-d. %B</td></tr>\n")
        self.wfile.write(b"<tr><td><b>time-format:</b></td><td>Format of the times, eg. \"%%H:%%M\", see https://strftime.org/ for details'.</td><td>Optional, default: %H:%M</td></tr>\n")
        self.wfile.write(b"<tr><td><b>symbol-zoom:</b></td><td>Scaling of the symbols.</td><td>Optional, default: 1.0</td></tr>\n")
        self.wfile.write(b"<tr><td><b>symbol-divisions:</b></td><td>Only draw every x symbol (1 equals every 3 hours).</td><td>Optional, default: 1</td></tr>\n")
        self.wfile.write(b"<tr><td><b>show-city-name:</b></td><td>Show the name of the city.</td><td>Optional, default: False</td></tr>\n")
        self.wfile.write(b"<tr><td><b>hide-data-copyright:</b></td><td>Hide the data copyright. Please only do this for personal usage!</td><td>Optional, default: False</td></tr>\n")
        self.wfile.write(b"</table>\n")
        
        self.wfile.write(b"<h3>Example</h3>\n")
        url = "generate-forecast?zip-code=8001&time-format=%H&time-divisions=3&height=250&width=600&days-to-show=2&show-min-max-temperatures=true&font-size=12&locale=de_DE.utf8&symbol-zoom=1.0&show-rain-variance=true"
        link = "<a href=\"" + url + "\">" + url + "</a>\n"
        self.wfile.write(bytes(link, 'utf-8'))
    
    
        self.wfile.write(b"<h2>Get Forecast Image</h2>\n")
        url = "get-forecast?zip-code=8001"
        link = "<a href=\"" + url + "\">" + url + "</a>\n"
        self.wfile.write(bytes(link, 'utf-8'))
        self.wfile.write(b"<h3>Parameters</h3>\n")
        self.wfile.write(b"<table>\n")
        self.wfile.write(b"<tr><td><b>zip-code:</b></td><td>Zip Code, eg. 8001</td><td>Mandatory</td></tr>\n")
        self.wfile.write(b"<tr><td><b>mark-time:</b></td><td>Add a mark of the current time.</td><td>Optional, default: False</td></tr>\n")
        self.wfile.write(b"<tr><td><b>max-forecast-age:</b></td><td>Maximing age of a cached forecast in seconds. If the forecast is older, you need to call generate-forecast first.</td><td>Optional, default: 4200</td></tr>\n")
        self.wfile.write(b"</table>\n")

        self.wfile.write(b"<h3>Example</h3>\n")
        url = "get-forecast?zip-code=8001&mark-time=1"
        link = "<a href=\"" + url + "\">" + url + "</a>\n"
        self.wfile.write(bytes(link, 'utf-8'))


        self.wfile.write(b"<h2>Get Forecast Metadata</h2>\n")
        url = "get-metadata?zip-code=8001"
        link = "<a href=\"" + url + "\">" + url + "</a>\n"
        self.wfile.write(bytes(link, 'utf-8'))
        self.wfile.write(b"<h3>Parameters</h3>\n")
        self.wfile.write(b"<table>\n")
        self.wfile.write(b"<tr><td><b>zip-code:</b></td><td>Zip Code, eg. 8001</td><td>Mandatory</td></tr>\n")
        self.wfile.write(b"</table>\n")

        
        self.wfile.write(b"<h2>Get Hours until Next Rain</h2>\n")
        url = "get-next-rain?zip-code=8001"
        link = "<a href=\"" + url + "\">" + url + "</a>\n"
        self.wfile.write(bytes(link, 'utf-8'))
        self.wfile.write(b"<h3>Parameters</h3>\n")
        self.wfile.write(b"<table>\n")
        self.wfile.write(b"<tr><td><b>zip-code:</b></td><td>Zip Code, eg. 8001</td><td>Mandatory</td></tr>\n")
        self.wfile.write(b"</table>\n")
    
    
    def getForecastImage(self, query):
        try:
            if 'zip-code' in query:
                zipCode = int(query['zip-code'][0])
            else:
                self.showHelp()
                return
        
        except Exception as e:
            self.wfile.write(bytes("An error occurred: %s!" % e, 'utf-8'))
            return
        
        self.send_header('Content-type','image/png')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        try:
            f = open(forecastFile + str(zipCode) + ".png", 'rb').read()
            self.wfile.write(f)
        except Exception as e:
            self.wfile.write(bytes("An error occurred: %s!" % e, 'utf-8'))
    
    
    def returnMarkedImage(self, query):
        # Validate parameters
        try:
            if 'zip-code' in query:
                zipCode = int(query['zip-code'][0])
            else:
                self.showHelp()
                return

            if 'max-forecast-age' in query:
                maxForecastAge = int(query['max-forecast-age'][0])
            else:
                maxForecastAge = 60*70 # 70 minutes

            if 'mark-time' in query:
                markTime = str2bool(query['mark-time'][0])
            else:
                markTime = False

            if 'utc-offset' in query:
                utcOffset = query['utc-offset']
            else:
                utcOffset = getCurrentUtcOffset()
        except Exception as e:
            self.wfile.write(bytes("An error occurred: %s!" % e, 'utf-8'))
            return

        # Check if forecast image exists
        if not exists(forecastFile + str(zipCode) + ".png"):
            self.wfile.write(bytes("An error occurred: Forecast Image is missing! You need to call /generate-forecast first!", 'utf-8'))
            return

        # Load Meta Data
        if not exists(metaDataFile + str(zipCode) + ".json"):
            self.wfile.write(bytes("An error occurred: Meta File is missing!", 'utf-8'))
            return

        try:
            with open(metaDataFile + str(zipCode) + ".json") as metaFile:
                metaData = json.load(metaFile)
        except Exception as e:
            self.wfile.write(bytes("An error occurred: %s!" % e, 'utf-8'))
            return

        print("Meta Data:", metaData)

        # Check if forecast is not too old
        now = int(datetime.datetime.now().timestamp())
        print("Current timestamp: %d, time since last forecast update: %d s (max. allowed forecast age: %d s)" % (now, now - metaData['forecastGenerationTimestamp'], maxForecastAge))
        if now - metaData['forecastGenerationTimestamp'] > maxForecastAge:
            self.wfile.write(bytes("An error occurred: Forecast is too old! You need to update it first using /generate-forecast!", 'utf-8'))
            return

        # Mark current time on image
        if markTime:
            markGraphic(inputFile=forecastFile + str(zipCode) + ".png", 
                        outputFile=markedForecastFile + str(zipCode) + ".png", 
                        metaFile=metaDataFile + str(zipCode) + ".json", x=metaData['firstDayX'], y=metaData['firstDayY'],
                        w=metaData['dayWidth'], h=metaData['dayHeight'], utcOffset=utcOffset, fakeTime=False, test=False)

        self.send_header('Content-type','image/png')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        try:
            if markTime:
                filename = markedForecastFile + str(zipCode) + ".png"
            else:
                filename = forecastFile + str(zipCode) + ".png"
            print("Sending %s" % filename)
            f = open(filename, 'rb').read()
            self.wfile.write(f)
        except Exception as e:
            self.wfile.write(bytes("An error occurred: %s!" % e, 'utf-8'))
    
    
    def returnMetaData(self, query):
        try:
            if 'zip-code' in query:
                zipCode = int(query['zip-code'][0])
            else:
                self.showHelp()
                return
        
        except Exception as e:
            self.wfile.write(bytes("An error occurred: %s!" % e, 'utf-8'))
            return
        
        self.send_header('Content-type','application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        try:
            f = open(metaDataFile + str(zipCode) + ".json", 'rb').read()
            self.wfile.write(f)
        except Exception as e:
            self.wfile.write(bytes("An error occurred: %s!" % e, 'utf-8'))


    def returnNextRain(self, query):
        try:
            if 'zip-code' in query:
                zipCode = int(query['zip-code'][0])
            else:
                self.showHelp()
                return

        except Exception as e:
            self.wfile.write(bytes('{ "error": "%s" }' % e, 'utf-8'))
            return

        self.send_header('Content-type','application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        try:
            try:
                meteoSwissForecast = MeteoSwissForecast(zipCode, getCurrentUtcOffset())
            except Exception as e:
                print(e)
                if "404" in str(e):
                    self.wfile.write(b'{ "error": "Unknown Zip Code" }')
                else:
                    self.wfile.write(bytes('{ "error": "%s" }' % e, 'utf-8'))
                return

            forecastData = meteoSwissForecast.importForecastData(forecastFile + str(zipCode) + ".json")
            nextRain, nextPossibleRain = meteoSwissForecast.getNextRain(forecastData)

            if nextRain == None:
                nextRain = 4 * 24

            if nextPossibleRain == None:
                nextPossibleRain = 4 * 24

            nextRainText = nextRain
            nextPossibleRainText = nextPossibleRain

            if nextRain > 24:
                nextRainText = ">24"

            if nextPossibleRain > 24:
                nextPossibleRainText = ">24"

            jsonData = '{ "nextRain": "' + str(nextRain) + '", "nextPossibleRain": "' + str(nextPossibleRain) + '", "nextRainText": "' + str(nextRainText) + '",  "nextPossibleRainText": "' + str(nextPossibleRainText) + '" }'
            self.wfile.write(bytes(jsonData, 'utf-8'))
        except Exception as e:
            if "No such file" in str(e):
                self.wfile.write(b'{ "error": "You first have to call generate" }')
            else:
                self.wfile.write(bytes('{ "error": "%s" }' % e, 'utf-8'))


    def generate(self, query):
        logLevel = logging.INFO
                
        # TODO return json with result info
        self.send_header('Content-type','text/html')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        parameter = None

        try:
            parameter = 'zip-code'
            if parameter in query:
                zipCode = int(query[parameter][0])
            else:
                self.showHelp()
                return
                
            parameter = 'days-to-show'
            if parameter in query:
                daysToShow = int(query[parameter][0])
                if daysToShow < 1 or daysToShow > maximumNumberOfDays:
                    self.wfile.write(bytes("%s must be 1..%d!" % (parameter, maximumNumberOfDays), 'utf-8'))
                    return
            else:
                daysToShow = 2
                    
            parameter = 'height'
            if parameter in query:
                height = int(query[parameter][0])
            else:
                height = 300

            parameter = 'width'
            if parameter in query:
                width = int(query[parameter][0])
            else:
                width = 1920

            parameter = 'time-divisions'
            if parameter in query:
                timeDivisions = int(query[parameter][0])
            else:
                timeDivisions = 6

            parameter = 'use-dark-mode'
            if parameter in query:
                darkMode = str2bool(query[parameter][0])
            else:
                darkMode = False
                    
            parameter = 'font-size'
            if parameter in query:
                fontSize = int(query[parameter][0])
            else:
                fontSize = 12

            parameter = 'show-min-max-temperatures'
            if parameter in query:
                minMaxTemperatures = str2bool(query[parameter][0])
            else:
                minMaxTemperatures = False
            
            parameter = 'show-rain-variance'
            if parameter in query:
                rainVariance = str2bool(query[parameter][0])
            else:
                rainVariance = False
            
            parameter = 'locale'
            if parameter in query:
                locale = query[parameter][0]
            else:
                locale = "en_US.utf8"
            
            parameter = 'utc-offset'
            if parameter in query:
                utcOffset = query[parameter][0]
            else:
                utcOffset = getCurrentUtcOffset()

            parameter = 'date-format'
            if parameter in query:
                dateFormat = query[parameter][0]
            else:
                dateFormat = "%A, %-d. %B"
            
            parameter = 'time-format'
            if parameter in query:
                timeFormat = query[parameter][0]
            else:
                timeFormat = "%H:%M"
            
            parameter = 'symbol-zoom'
            if parameter in query:
                symbolZoom = float(query[parameter][0])
            else:
                symbolZoom = 1.0
            
            parameter = 'symbol-divisions'
            if parameter in query:
                symbolDivisions = int(query[parameter][0])
            else:
                symbolDivisions = 1
            
            parameter = 'show-city-name'
            if parameter in query:
                cityName = str2bool(query[parameter][0])
            else:
                cityName = False
            
            parameter = 'hide-data-copyright'
            if parameter in query:
                hideDataCopyright = str2bool(query[parameter][0])
            else:
                hideDataCopyright = False

        except Exception as e:
            self.wfile.write(bytes("An error occurred on parameter \"%s\": %s!" % (parameter, e), 'utf-8'))
            return

            
        self.wfile.write(b"Parameters ok<br>\n")
        self.wfile.flush()
        print("Parameters ok", flush=True)
            
        logging.basicConfig(format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%d-%b-%y %H:%M:%S', level=logLevel)
        logging.getLogger("matplotlib").setLevel(logging.WARNING) # hiding the debug messages from the matplotlib

        self.wfile.write(b"Feching data for %d...<br>\n" % zipCode)
        self.wfile.flush()
        print("Fetching data for %d..." % zipCode, flush=True)

        try:
            meteoSwissForecast = MeteoSwissForecast(zipCode, getCurrentUtcOffset())
        except Exception as e:
            print(e)
            if "404" in str(e):
                self.wfile.write(b"Unknown Zip Code!")
            else:
                self.wfile.write(bytes("An error occurred: %s!" % e, 'utf-8'))            
            return

        forecastDataUrl = meteoSwissForecast.getForecastDataUrl()
        print("Forecast Data URL: %s" % forecastDataUrl, flush=True)

        self.wfile.write(b"Generating Forecast...<br>\n")
        self.wfile.flush()
        print("Generating Forecast...", flush=True)
        
        def progressCallback(message):
            try:
                self.wfile.write(b"%s<br>\n" % bytes(message, 'utf-8'))
                self.wfile.flush()
                print(message, flush=True)
            except:
                pass

        
        #try:
            #mdp = measurementDataProvider.MeasurementDataProvider(influxDbHost='192.168.1.99', influxDbPort=5086, influxDbUser='python', influxDbPassword='heaven7') # TODO move to config file
            #measuredRain = mdp.getMeasurement(sensor="regenstaerke", groupingInterval=10, fill=0)
            #measuredTemperature = mdp.getMeasurement(sensor="aussentemperatur", groupingInterval=5, fill="previous")
        #except Exception as e:
            #logging.error("An error occurred: %s" % e)
            #measuredRain = None
            #measuredTemperature = None
            
        #if measurement_data_db_host != None and measurement_data_db_port != None and measurement_data_db_user != None and measurement_data_db_password != None: 
        if True:
            logging.debug("Using Measurement Data to show real local data")
            try:
                #mdp = measurementDataProvider.MeasurementDataProvider(measurementDataDbHost=measurement_data_db_host, measurementDataDbPort=measurement_data_db_port, measurementDataDbUser=measurement_data_db_user, measurementDataDbPassword=measurement_data_db_password)
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
                    #measuredTemperature = mdp.getMeasurement(sensor="temperatur_im_garten_schopf", groupingInterval=10, fill="previous")
                    measuredTemperature = mdp.getMeasurement(sensor="temperatur_vor_dem_haus", groupingInterval=10, fill="previous")
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

        forecastData = meteoSwissForecast.collectData(forecastDataUrl=forecastDataUrl, daysToUse=daysToShow, timeFormat=timeFormat, dateFormat=dateFormat, localeAlias=locale)
        meteoSwissForecast.exportForecastData(forecastData, forecastFile + str(zipCode) + ".json")
        meteoSwissForecast.generateGraph(data=forecastData, outputFilename=(forecastFile + str(zipCode) + ".png"), timeDivisions=timeDivisions, graphWidth=width, graphHeight=height, darkMode=darkMode, rainVariance=rainVariance, minMaxTemperature=minMaxTemperatures, fontSize=fontSize, symbolZoom=symbolZoom, symbolDivision=symbolDivisions, showCityName=cityName, hideDataCopyright=hideDataCopyright, writeMetaData=(metaDataFile + str(zipCode) + ".json"), progressCallback=progressCallback, measuredRain=measuredRain, measuredTemperature=measuredTemperature)
        
        print("Image got saved as " + forecastFile + str(zipCode) + ".png")
        print("Metadata got saved as " + metaDataFile + str(zipCode) + ".json")
        print("Forecast data got saved as " + forecastFile + str(zipCode) + ".json")

        self.wfile.write(b"Done<br>\n")
        print("Done", flush=True)       
        
        url = "get-forecast?zip-code=" + str(zipCode)
        link = "<a href=\"" + url + "\">" + url + "</a><br>\n"
        self.wfile.write(bytes("You can now download the Forecast Image from " + link, 'utf-8'))

        url = "get-forecast?zip-code=" + str(zipCode) + "&mark-time=1"
        link = "<a href=\"" + url + "\">" + url + "</a><br>\n"
        self.wfile.write(bytes("Or use the following link which additionally adds a mark of the current time: " + link, 'utf-8'))
    
        return


if __name__ == '__main__':
    try:
        forecastFile = "./data/forecast_"
        markedForecastFile = "./data/markedForecast_"
        metaDataFile = "./data/metadata_"

        internalPort = 80
        fallbackPort = 12081 # testing
        
        try:
            if not os.path.exists("./data"):
                os.makedirs("./data")
        except OSError:
            print ("Failed to create data folder")
    except Exception as e:
        print("An error occurred: %s" % e)
        exit(1)

    # Run the service
    try:
        print("Meteoswiss Forecast Generator")
        print("Copyright (c) 2020-2022 by George Ruinelli <george@ruinelli.ch>, https://github.com/caco3/MeteoSwiss-Forecast")

        # Check if we run withing a docker container
        IN_DOCKER = os.environ.get('AM_I_IN_A_DOCKER_CONTAINER', False)
        if IN_DOCKER:
            with open("build-date.txt") as buildDateFile:
                print("Docker build date:", buildDateFile.read())

        print("Starting...")
        try:
            server = HTTPServer(('', internalPort), myHandler)
        except: # Cannot open port, use test port
            internalPort = fallbackPort
            server = HTTPServer(('', internalPort), myHandler)

        print("Listening on port %d" % internalPort)
        print("Ready to receive requests")

        # Wait forever for incoming http requests
        server.serve_forever()

    except KeyboardInterrupt:
        print ('^C received, shutting down the web server')
        server.socket.close()
