#!/usr/bin/python
from http.server import BaseHTTPRequestHandler,HTTPServer
from urllib.parse import urlparse, parse_qs
from meteoswissForecast import MeteoSwissForecast
import logging
#import pprint
import os


PORT_NUMBER = 8080


def str2bool(v):
    return v.lower() in ("yes", "true", "t", "1")



# This class will handle any incoming request from
# a browser 
class myHandler(BaseHTTPRequestHandler):
    # Handler for the GET requests
    def do_GET(self):
        self.send_response(200)        
        
        parsed_url = urlparse(self.path)
        query = parse_qs(parsed_url.query)
        
        print("File: %s" % parsed_url.path)
        print("Query: %s" % query)
        
        if parsed_url.path == "/generate":
            self.generate(query)
        elif parsed_url.path == "/mark":
            self.markImage()
        elif parsed_url.path == "/forecast":
            self.returnImage()
        elif parsed_url.path == "/marked-forecast":
            self.returnMarkedImage()
        elif parsed_url.path == "/meta":
            self.returnMetaData()
        else:
            self.showHelp()

        
    def showHelp(self):
        self.send_header('Content-type','text/html')
        self.end_headers()
        
        self.wfile.write(b"<h1>Meteoswiss Forecast Generator</h1>\n")
        self.wfile.write(b"<h2>Generate</h2>\n")
        self.wfile.write(b"http://localhost:8080/generate")
        self.wfile.write(b"<h3>Parameters<h3>\n")
        self.wfile.write(b"<table>\n")
        self.wfile.write(b"<tr><td><b>zip-code:</b></td><td>Zip Code, eg. 8000</td><td>Mandatory</td></tr>\n")
        self.wfile.write(b"<tr><td><b>days-to-show:</b></td></td><td>Number of days to show (1..8).</td><td>Optional, default: 8</td></tr>\n")
        self.wfile.write(b"<tr><td><b>height:</b></td><td>Height of the graph in pixel.</td><td>Optional, default: 300</td></tr>\n")
        self.wfile.write(b"<tr><td><b>width:</b></td><td>Width of the graph in pixel.</td><td>Optional, default: 1920</td></tr>\n")
        self.wfile.write(b"<tr><td><b>time-divisions:</b></td><td>Distance in hours between time labels.</td><td>Optional, default: 6</td></tr>\n")
        self.wfile.write(b"<tr><td><b>use-dark-mode:</b></td><td>Use dark colors.</td><td>Optional, default: False</td></tr>\n")
        self.wfile.write(b"<tr><td><b>font-size:</b></td><td>Font Size in pixel.</td><td>Optional, default: 12</td></tr>\n")
        self.wfile.write(b"<tr><td><b>show-min-max-temperatures:</b></td><td>Show min/max temperature per day.</td><td>Optional, default: False</td></tr>\n")
        self.wfile.write(b"<tr><td><b>show-rain-variance:</b></td><td>Show rain variance.</td><td>Optional, default: False</td></tr>\n")
        self.wfile.write(b"<tr><td><b>locale:</b></td><td>Used localization of the date, eg. en_US.utf8.</td><td>Optional, default: en_US.utf8</td></tr>\n")
        self.wfile.write(b"<tr><td><b>date-format:</b></td><td>Format of the dates, eg. \"%%A, %%-d. %%B\", see https://strftime.org/ for details'.</td><td>Optional, default: %A, %-d. %B</td></tr>\n")
        self.wfile.write(b"<tr><td><b>time-format:</b></td><td>Format of the times, eg. \"%%H:%%M\", see https://strftime.org/ for details'.</td><td>Optional, default: %H:%M</td></tr>\n")
        self.wfile.write(b"<tr><td><b>symbol-zoom:</b></td><td>Scaling of the symbols.</td><td>Optional, default: 1.0</td></tr>\n")
        self.wfile.write(b"<tr><td><b>symbol-divisions:</b></td><td>Only draw every x symbol (1 equals every 3 hours).</td><td>Optional, default: 1</td></tr>\n")
        self.wfile.write(b"<tr><td><b>show-city-name:</b></td><td>Show the name of the city.</td><td>Optional, default: False</td></tr>\n")
        self.wfile.write(b"</table>\n")
        
        self.wfile.write(b"<h3>Example</h3>\n")
        url = "http://localhost:8080/generate?zip-code=8620&time-format=%H&time-divisions=3&height=250&width=1280&days-to-show=4&use-dark-mode=true&show-min-max-temperatures=true&font-size=12&locale=de_DE.utf8&symbol-zoom=0.8&show-rain-variance=true"
        link = "<a href=\"" + url + "\">" + url + "</a>\n"
        self.wfile.write(bytes(link, 'utf-8'))
    
        self.wfile.write(b"<h2>Get Forecast</h2>\n")
        self.wfile.write(b"<a href=\"http://localhost:8080/forecast\">http://localhost:8080/forecast</a>")
    
        self.wfile.write(b"<h2>Mark with current time</h2>\n")
        # TODO show parameters
        self.wfile.write(b"<a href=\"http://localhost:8080/mark\">http://localhost:8080/mark</a>")
    
        self.wfile.write(b"<h2>Get Forecast marked with current time</h2>\n")
        self.wfile.write(b"<a href=\"http://localhost:8080/marked-forecast\">http://localhost:8080/marked-forecast</a>")
        
        self.wfile.write(b"<h2>Get Forecast Metadata</h2>\n")
        self.wfile.write(b"<a href=\"http://localhost:8080/meta\">http://localhost:8080/meta</a>")


    def markImage(self):
        self.send_header('Content-type','text/html')
        self.end_headers()
        # TODO mark forecast
        self.wfile.write(b"Done")
        pass
    
    
    def returnImage(self):
        self.send_header('Content-type','image/png')
        self.end_headers()
        try:
            f = open(forecastFile, 'rb').read()
            self.wfile.write(f)
        except Exception as e:
            self.wfile.write(bytes("An error occurred: %s!" % e, 'utf-8'))
    
    
    def returnMarkedImage(self):
        self.send_header('Content-type','image/png')
        self.end_headers()
        try:
            #f = open(markedForecastFile, 'rb').read()
            # TODO return marked forecast
            f = open(forecastFile, 'rb').read()
            self.wfile.write(f)
        except Exception as e:
            self.wfile.write(bytes("An error occurred: %s!" % e, 'utf-8'))
    
    
    def returnMetaData(self):
        self.send_header('Content-type','application/json')
        self.end_headers()
        try:
            f = open(metaDataFile, 'rb').read()
            self.wfile.write(f)
        except Exception as e:
            self.wfile.write(bytes("An error occurred: %s!" % e, 'utf-8'))
            
            
            
    def generate(self, query):
        logLevel = logging.INFO
                
        try:
            if 'zip-code' in query:
                zipCode = int(query['zip-code'][0])
            else:
                self.showHelp()
                return
                
            if 'days-to-show' in query:
                daysToShow = int(query['days-to-show'][0])
                if daysToShow < 1 or daysToShow > 8:
                    self.wfile.write(bytes("days-to-show must be 1..8!"))
                    return
            else:
                daysToShow = 7
                    
            if 'height' in query:
                height = int(query['height'][0])
            else:
                height = 300
                    
            if 'width' in query:
                width = int(query['width'][0])
            else:
                width = 1920
                    
            if 'time-divisions' in query:
                timeDivisions = int(query['time-divisions'][0])
            else:
                timeDivisions = 6
                    
            if 'use-dark-mode' in query:
                darkMode = str2bool(query['use-dark-mode'][0])
            else:
                darkMode = False
                    
            if 'font-size' in query:
                fontSize = int(query['font-size'][0])
            else:
                fontSize = 12

            if 'show-min-max-temperatures' in query:
                minMaxTemperatures = str2bool(query['show-min-max-temperatures'][0])
            else:
                minMaxTemperatures = False
            
            if 'show-rain-variance' in query:
                rainVariance = str2bool(query['show-rain-variance'][0])
            else:
                rainVariance = False
            
            if 'locale' in query:
                locale = query['locale'][0]
            else:
                locale = "en_US.utf8"
            
            if 'date-format' in query:
                dateFormat = query['date-format'][0]
            else:
                dateFormat = "%A, %-d. %B"
            
            if 'time-format' in query:
                timeFormat = query['time-format'][0]
            else:
                timeFormat = "%H:%M"
            
            if 'symbol-zoom' in query:
                symbolZoom = float(query['symbol-zoom'][0])
            else:
                symbolZoom = 1.0
            
            if 'symbol-divisions' in query:
                symbolDivisions = int(query['symbol-divisions'][0])
            else:
                symbolDivisions = 1
            
            if 'show-city-name' in query:
                cityName = str2bool(query['show-city-name'][0])
            else:
                cityName = False
            
        except Exception as e:
            self.wfile.write(bytes("An error occurred: %s!" % e, 'utf-8'))
            return

            
        self.wfile.write(b"Parameters ok<br>\n")
        self.wfile.flush()
        print("Parameters ok")
            
        logging.basicConfig(format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%d-%b-%y %H:%M:%S', level=logLevel)
        logging.getLogger("matplotlib").setLevel(logging.WARNING) # hiding the debug messages from the matplotlib

        self.wfile.write(b"Feching data...<br>\n")
        print("Parameters ok")
        print("Fetching data...")
        
        meteoSwissForecast = MeteoSwissForecast(zipCode)        
        dataUrl = meteoSwissForecast.getDataUrl()
                
        self.wfile.write(b"Generating Forecast...<br>\n")
        print("Parameters ok")
        print("Generating Forecast...")
        
        forecastData = meteoSwissForecast.collectData(dataUrl=dataUrl, daysToUse=daysToShow, timeFormat=timeFormat, dateFormat=dateFormat, localeAlias=locale)
        meteoSwissForecast.generateGraph(data=forecastData, outputFilename=forecastFile, timeDivisions=timeDivisions, graphWidth=width, graphHeight=height, darkMode=darkMode, rainVariance=rainVariance, minMaxTemperature=minMaxTemperatures, fontSize=fontSize, symbolZoom=symbolZoom, symbolDivision=symbolDivisions, showCityName=cityName, writeMetaData=metaDataFile)
                
        self.wfile.write(b"Done<br>\n")
        print("Generating Forecast...Done")        

        return

try:
    forecastFile = "./data/forecast.png"
    markedForecastFile = "./data/forecast-marked.png"
    metaDataFile = "./data/metadata.json"
    
    try:
        if not os.path.exists("./data"):
            os.makedirs("./data")
    except OSError:
        print ("Failed to create data folder")
            
    # Create a web server and define the handler to manage the
    # incoming request
    server = HTTPServer(('', PORT_NUMBER), myHandler)
    print ('Started httpserver on port ' , PORT_NUMBER)

    # Wait forever for incoming http requests
    server.serve_forever()

except KeyboardInterrupt:
    print ('^C received, shutting down the web server')
    server.socket.close()
