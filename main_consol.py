import sys, os
import argparse
import logging
import flickrUploader
from flickrUploader import FlickrUploader
import event
import threading

parser = argparse.ArgumentParser(description = 'Upload photos into flickr album')
parser.add_argument('-folder', type = str, help = 'Source folder')
parser.add_argument('-album', type = str, help = 'Flickr album name')
args = parser.parse_args()

def getFolder():
    return args.folder if args.folder else os.getcwd()

def getAlbum(folder):
    return args.album if args.album else os.path.basename(folder)

folder = getFolder()
album = getAlbum(folder)

def is_valid_path(path):
    """Checks if the given path exists"""
    return os.path.exists(path)

def display_message(message):
    sys.stdout.write(message)
    sys.stdout.flush()

def main():
    if not is_valid_path(folder):
        log_msg("Invalid path. Application running will be stoped.", target = sys.stdout)
        sys.exit()

    event_handler = event.flickEvent
    event_handler.add_handler(display_message)

    #create and authenticate
    flickr = FlickrUploader(permit = "write")
    flickr.upload_all(folder, album)

if __name__ == "__main__":
    main()

