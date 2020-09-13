import logging
import argparse
import time
import datetime
import pytz
import json
from PIL import Image, ImageDraw

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Script to take a forecast graph image file (png) and add a mark to the current time')
    parser.add_argument('-v', action='store_true', help='Verbose output')
    parser.add_argument('-i', action='store', type=argparse.FileType('r'), required=True,  help='Input file name of the graph image (png)')
    parser.add_argument('-m', action='store', type=argparse.FileType('r'), help='Meta file to be used (json)')
    parser.add_argument('-o', action='store', type=argparse.FileType('w'), required=True,  help='Output file name of the graph image (png)')
    parser.add_argument('-x', action='store', type=int, required=True, help='start-x pixel of first day')
    parser.add_argument('-y', action='store', type=int, required=True, help='start-x pixel of first day')
    parser.add_argument('-H', action='store', type=int, required=True, help='Height of the day in pixel')
    parser.add_argument('-w', action='store', type=int, required=True, help='Width of the day in pixel')
    parser.add_argument('--fake-time', action='store', help='Time to fake, in the format hh:mm')
    parser.add_argument('--test', action='store_true', help='Draws a border around the day for testing the coordinate and size')

    args = parser.parse_args()

    logLevel = logging.INFO
    if args.v:
        logLevel = logging.DEBUG

    logging.basicConfig(format='%(asctime)s [%(levelname)s] %(message)s', datefmt='%d-%b-%y %H:%M:%S', level=logLevel)

    x, y, w, h = args.x, args.y, args.w, args.H

    logging.debug("X: %d, Y: %d, width: %d, height: %d" % (x, y, w, h))

    pixelPerMinute = float(w) / (24 * 60)
    logging.debug("Pixel per Minute: %f, per hour: %f" % (pixelPerMinute, pixelPerMinute * 60))

    im = Image.open(args.i.name)
    imageWidth, imageHeight = im.size
    logging.debug("Dimension of the graph: %d, %d" % (imageWidth, imageHeight))

    d = ImageDraw.Draw(im)

    y = imageHeight - y # swap top/bottom coordination system
    h *= -1

    if args.test:
        logging.info("Going to draw a red frame around the first day")
        d.line([(x, y), (x, y + h)], fill='red', width=1) # left side
        d.line([(x + w, y), (x + w, y + h)], fill='red', width=1) # right side
        d.line([(x, y), (x + w, y)], fill='red', width=1) # top
        d.line([(x, y + h), (x + w, y + h)], fill='red', width=1) # bottom


    if args.m:
        # Get offset from local time to UTC, see also https://stackoverflow.com/questions/3168096/getting-computers-utc-offset-in-python
        ts = time.time()
        utcOffset = (datetime.datetime.fromtimestamp(ts) -
                    datetime.datetime.utcfromtimestamp(ts)).total_seconds()
        utcOffset = int(utcOffset / 3600) # in hours
        logging.debug("UTC offset: %dh" % utcOffset)

        with open(args.m.name) as metaFile:
            metaData = json.load(metaFile)
        logging.debug("%d seconds since last model generation" % (datetime.datetime.utcnow().timestamp() + utcOffset * 3600 - metaData['modelTimestamp']))

        # TODO check if mode got generated yesterday. if so, the current time must be shown on the 2nd day shown instead of the first! 


    if args.fake_time:
        hour = int(args.fake_time[0:2])
        minute = int(args.fake_time[3:5])
    else: # use current time
        hour = datetime.datetime.now().hour
        minute = datetime.datetime.now().minute
    logging.debug("Time: %02d:%02d" % (hour, minute))

    pixelPerTime = pixelPerMinute * (hour * 60 + minute)

    d.line([(x + pixelPerTime, y - 1), (x + pixelPerTime, y + h)], fill='red', width=2)

    im.save(args.o.name)
