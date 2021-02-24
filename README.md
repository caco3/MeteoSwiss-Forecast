# MeteoSwiss-Forecast
Script to fetch the MeteoSwiss Weather Forecast data and generate a graph out of it.

The graph contains the rain and temperature forecast. later one is enhanced with the uncertainty band. Additionally, a blue marker indicates the last forecast model simulation.

The graph is highly configurable, how ever in the default configuration it tries to adapt the style of the MeteoSwiss App.

### Default
`python3 meteoswissForecast.py -z 8001 -f myForecast.png`

![MeteoSwiss Style](doc/default.png)

### Enhancements
Additionally, you can switch to a dark mode, change the time divisions, select the number of days and even mark the min/max temperature per day.

#### Example 1
`python3 meteoswissForecast.py -z 6986 -f myForecast.png --days-to-show 3 --width 800 --symbol-division 2 --min-max-temperature`

![MeteoSwiss Style](doc/example1.png)

#### Example 2
`python3 meteoswissForecast.py -z 8001 -f myForecast.png --days-to-show 3 --time-division 2 --width 1200 --height 300 --min-max-temperature --dark-mode --locale de_DE.utf8 --compact-time-format`

![MeteoSwiss Style](doc/example2.png)

### Marking of Current time
The repo contains an extra script to add a mark of the current time (red bar). One might want to update this every minute or so.
Since the generation of the forecast is rater slow, one might want to only update the current time mark at a high frequency but only generate the forecast once every hour.

`python3 markGraphic.py -i myForecast.png -o myForecast-marked.png -x 52 -y 50 -w 295 -H 161`

![MeteoSwiss Style](doc/forecast-marked.png)


## Preparations
### Requirements
Run `python3 -m pip install -r requirements.txt` to install all needed Python packages.

### Get Symbols
MeteoSwiss provides the symbols as SVG files. How ever we need them as PNG files, preferably with a transparent background.
The folder `symbols` provides the already converted symbols. Alternatively you can generate them yourself:
```
mkdir symbols
cd symbols
for i in {1..35}; do wget https://www.meteoschweiz.admin.ch/etc/designs/meteoswiss/assets/images/icons/meteo/weather-symbols/$i.svg; done
for i in {101..135}; do wget https://www.meteoschweiz.admin.ch/etc/designs/meteoswiss/assets/images/icons/meteo/weather-symbols/$i.svg; done
for f in *.svg; do convert -background transparent -resize 256x256 -density 500 $f ${f%.svg}.png; done
rm *.svg
```


# Docker
## get it from Dockerhub
https://hub.docker.com/r/caco3x/meteoswiss-forecast

## Build it manually
`docker build -t meteoswiss-forecast .`

## Run it in a Docker Container
1. Adjust the parameters in `Dockerfile`
1. Build the docker image with `docker build -t meteoswiss-forecast .`
1. Run it with `docker run -it --rm -v /tmp:/data --name my-meteoswiss-forecast -p 12080:80 meteoswiss-forecast`
1. Call it in a webbrowser: `http://localhost:12080`

:exclamation: Within the docker container, the UTC offset is always 0! To work around this, set the environment variable `UTC_OFFSET`.

# Legal
The scripts only use publicly available data provided by the [website of MeteoSwiss](https://www.meteoschweiz.admin.ch/home.html?tab=overview). 

The scripts are provided under the terms of the GPL V3.
