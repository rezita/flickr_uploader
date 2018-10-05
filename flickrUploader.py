import flickrapi
import hashlib, os, ast, sys
import PIL.Image, PIL.ExifTags
import webbrowser
from datetime import datetime
import logging
import configparser
import event

api_key = ""
api_secret = ""
flickr = flickrapi.FlickrAPI(api_key, api_secret)

hash_file = ".flickrUploader"
hash_photos = "Photos"
hash_album = "Album"
image_ext = ".jpg", ".jpeg", ".png", ".gif"
video_ext = ".mov", ".avi", ".m4v", ".mp4"
hash_prefix = "sha256_"
event_handler = event.flickEvent

def is_valid_path(path):
    """Checks if the given path exists"""
    return os.path.exists(path)

def is_media_file(filepath):
    """Checks if the given file is an image or a video file"""
    return filepath.lower().endswith(image_ext + video_ext)

def is_video_file(filepath):
    """Checks if the given file (with path) is a movie file"""
    return filepath.lower().endswith(video_ext)

def is_image_file(filepath):
    """Checks if the given file (with path) is an image"""
    return filepath.lower().endswith(image_ext)

def is_valid_media_file(filepath):
    """Checks if the given file (with path) is valid and a media file"""
    return is_valid_path(filepath) and is_media_file(filepath)

def get_exif(filename):
    result = {}
    if is_image_file(filename):
        img = PIL.Image.open(filename)
        result = getattr(img, '_getexif', lambda: {})()
        img.close()
    return result if result != None else {}

def get_file_info(filepath):
    """get useful exif info of the file"""
    exif_info = get_exif(filepath)
    result = {}
    date_taken = exif_info.get(36867, "0000:00:00 00:00:00")
    if date_taken != "0000:00:00 00:00:00":
        date_taken = datetime.strptime(date_taken, '%Y:%m:%d %H:%M:%S')
    else:
        date_taken = os.path.getctime(filepath)
        date_taken = datetime.fromtimestamp(date_taken)
    result['date_taken'] = date_taken.strftime('%Y-%m-%d %H:%M:%S')

    date_modif = exif_info.get(306, "0000:00:00 00:00:00")
    if date_modif != "0000:00:00 00:00:00":
        date_modif = datetime.strptime(date_modif, '%Y:%m:%d %H:%M:%S')
    else:
        date_modif = os.path.getmtime(filepath)
        date_modif = datetime.fromtimestamp(date_modif)
    result['date_modif'] = date_modif.strftime('%Y-%m-%d %H:%M:%S')

    orientation = exif_info.get(274, 1)
    result['orient'] = orientation

    return result

def calculate_hash_of_file(filepath):
    ''' Calculates the Hash code of the file.
        The hash code depends on the file content not the name of it.
        So renamed files have the same hash_code.
        If the content of the file is changed the hash code will be
        differ from the original file.'''
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as afile:
        buffer = afile.read()
        hasher.update(buffer)
    return (hasher.hexdigest())

def get_size(filepath):
    """Returns the size of the given file in MB"""
    precision = 2
    sizes = ((1024*1024, "MB"), (1024, "Kb"), (2, "bytes"), (1, "byte"))
    if not is_valid_path(filepath):
        return '{}{}'.format(0, 'MB')
    size_in_bytes = os.path.getsize(filepath)
    for min_size, abbrev in sizes:
        if size_in_bytes >= min_size:
            return '{} {}'.format(
                    round(size_in_bytes / min_size, precision),
                    abbrev)

def get_media_files(path):
    """Returns the list of media files are in predefined folder"""
    return [file_name for file_name in os.listdir(path)
            if file_name.lower().endswith(image_ext + video_ext)]

def clear_hash_data(path):
    config_path = os.path.join(path, hash_file)
    if is_valid_path(config_path):
        f = open(config_path, 'r+')
        f.truncate(0)

def get_config_options_for_section(path, config, section):
    """Returns options for the givem section from the config file.
        If the file demaged, the content of it will be deleted."""
    result = {}
    config_path = os.path.join(path, hash_file)
    if not is_valid_path(config_path):
        return result
    try:
        config = configparser.ConfigParser()
        config.read(config_path)
        if section not in config.sections():
            return {}
        options = config.options(section)
        for option in options:
            try:
                result[option.lower()] = (config.get(section, option)).lower()
            except Exception as e:
                #Corrupt hash_file -> clear it
                clear_hash_data(path)
    except configparser.MissingSectionHeaderError as mse:
        #Corrupt hash_file -> clear it
        clear_hash_data(path)
    return result

def read_hash_from_config(path):
    """Reads the (filename, hash_code) pairs from config file"""
    config = configparser.ConfigParser()
    return get_config_options_for_section(path, config, hash_photos)

def read_album_from_config(path):
    """Reads flickr albumname for the given path from config file
        If there is no albumname, it returns empty string"""
    config = configparser.ConfigParser({hash_album: ""})
    options = get_config_options_for_section(path, config, hash_album)
    return options.get(hash_album.lower(), "")

def append_to_hash_file(path, section, option, value):
    """"Saves the given option with the given value under
        the given sectioninto the config file.
        If the config file doesn't exist, it creates it.
        If the given section doesn't exist, it adds to the file."""
    config_path = os.path.join(path, hash_file)

    config = configparser.ConfigParser()

    if not is_valid_path(config_path):
        config.add_section(section)
    else:
        config.read(config_path)
        if section not in config.sections():
            config.add_section(section)
    config.set(section, option, value)
    with open(config_path, 'w') as configfile:
        config.write(configfile)

def get_photo_data(path, filename):
    """Sets photo data for the given file."""
    filepath = os.path.join(path, filename)
    data = {'filename': filename,
            'source': filepath,
            'dirname': path,
            'uploaded': False,
            'video': is_video_file(filename),
            'file_size': get_size(filepath)}
    fileinfo = get_file_info(filepath)
    data.update(fileinfo)
    return data

def set_selectable(path, datalist, is_valid_album):
    """Marks the uploaded data in the datalist """
    datas = datalist
    if is_valid_album:
        hash_name_pairs = read_hash_from_config(path)
        filenames_from_hash = [filename.lower() for filename
            in list(hash_name_pairs)]
        for data in datas:
            if data['filename'].lower() in filenames_from_hash:
                data['uploaded'] = True
    else:
        #the hash_file is corrupt --> clear it
        clear_hash_data(path)
    return datas

class FileWithCallback(object):
    def __init__(self, filename, callback):
        self.file = open(filename, 'rb')
        self.callback = callback
        self.len = os.path.getsize(filename)
        self.fileno = self.file.fileno
        self.tell = self.file.tell
        self.readed = 0

    def read(self, size):
        if self.callback:
            newRead = self.tell() *100 // self.len
            if newRead >= self.readed + 10:
                self.callback(newRead)
                self.readed = newRead
        return self.file.read(size)

def callback(progress):
    event_handler.fire('.')
    #print('.', end = '', flush = True)

class FlickrUploader():
    user = {}

    def __init__(self, permit, *args, **kwargs):
        self._authenticate(permit)
        self.set_user()

    def _authenticate(self, permit):
        """User authentication with the given permission.
            Checks if the user has a valid token or not.
            If hasn't got, the user needs to get one and  verify it."""
        if not flickr.token_valid(permit):
            flickr.get_request_token(oauth_callback="oob")
            authorize_url = flickr.auth_url(perms = permit)
            webbrowser.open_new_tab(authorize_url)
            verifier = str(input("Verifier code: "))
            flickr.get_access_token(verifier)

    def set_user(self):
        """Returns the user who was authencticated."""
        if not self.user:
            response = flickr.auth.oauth.checkToken(format='parsed-json')
            if response['stat'] == "ok":
                self.user = response['oauth']['user']

    def get_username(self):
        """Returns the authenticated user's flickr username."""
        if not self.user:
            self.set_user()
        return self.user['username']

    def get_userid(self):
        """Returns the authenticated used's flickr nsid."""
        if not self.user:
            self.set_user()
        return self.user['nsid']

    def get_flickr_albums(self):
        """Retruns a list of the user's flickr albums.
            It returns a list of dictionaries,
            where the keys are the id and title of albums"""
        response = flickr.photosets.getList(
                user_id= self.get_userid(),
                format='parsed-json')
        albums = []
        photosets = response['photosets']['photoset']
        for pset in photosets:
            album = {'id' : pset['id'], 
                    'title' : pset['title']['_content']}
            albums.append(album)
        return albums

    def get_flickr_album_titles(self):
        """Retruns the list of flickr albumnames"""
        result = []
        albums = self.get_flickr_albums()
        for album in albums:
            result.append(album['title'])
        return result

    def get_albumid_for_albumname(self, albumname):
        """Retruns the flickr id of the given albumname if exists.
            Otherwise it returns empty string."""
        albums = self.get_flickr_albums()
        for album in albums:
            if album['title'] == albumname:
                return album['id']
        return ''

    def is_existed_album(self, albumname):
        """Checks if the given albumname is valid
            flickr albumname or not."""
        return albumname in  self.get_flickr_album_titles()

    def get_photo_ids_for_hash(self, hashCode):
        """Returns a list of photoIds which have the given hashCode tag.
            If there isn't any photo, retruns an empty list"""
        response = flickr.photos.search(
                user_id = self.get_userid(),
                tags = hash_prefix + hashCode,
                format = 'parsed-json')
        photos = response['photos']['photo']
        return [photo['id'] for photo in photos]

    def add_photo_to_album(self, albumid, photoid):
        """Adds the given photoid to the given album (photoset) """
        flickr.photosets.addPhoto(photoset_id = albumid, photo_id = photoid)

    def upload_file(self, photo, filehash):
        """Uploads the given photo if exists and
            sets date_taken value on flickr.
            Retruns the photoID of the uploaded photo.
            If the given photo is not valid media file, return None."""
        if not is_valid_media_file(photo['source']):
            return None
        callBack = FileWithCallback(photo['source'], callback)
        response = flickr.upload(
                fileobj = callBack,
                filename = photo['source'],
                tags = filehash)
        if response.get('stat') == 'ok':
            photoid = response.getchildren()[0].text
            #set date_taken of the photo
            flickr.photos_setDates(
                    photo_id = photoid,
                    date_taken = photo['date_taken'])
            return photoid
        else:
            return None

    def get_flickr_albums_for_photo_ids(self, photo_id_list):
        """Retruns a list of albumnames which contains the given photos
            photoIdList: list of photoIds"""
        result = []
        for photoid in photo_id_list:
            response = flickr.photos.getAllContexts(
                    photo_id = photoid,
                    format = 'parsed-json')
            albums = response.get('set', {})
            result += [album.get('title') for album in albums]
        return result

    def create_album_if_not_existed(self, albumname, photoid):
        """Creates a new album on flickr if doesn't exist
            and retruns the albumname.
        Otherwise, puts the given photo into the album."""
        response = flickr.photosets.create(
                title = albumname, 
                primary_photo_id = photoid,
                format='parsed-json')
        if response['stat'] == 'ok':
            return albumname
        return None

    def get_all_photos_data(self, path):
        """Retruns all data of photos (media files) from the given path"""
        result = []
        mediafiles = get_media_files(path)
        for filename in mediafiles:
            data = get_photo_data(path, filename)
            result.append(data)
        #set unselectable photos which have been uploaded yet
        albumname = read_album_from_config(path)
        #check if the album set in the config file is a valid flickr album
        is_valid_album = albumname in self.get_flickr_album_titles()
        result = set_selectable(path, result, is_valid_album)
        return result

    def update_flickr_album(self, photos, albumname):
        """Uploads/adds all given photos to the given album"""
        if photos:
            #checks if the albumname is in configfile. If not, appends in it.
            append_to_hash_file(
                    photos[0]['dirname'],
                    hash_album,
                    hash_album,
                    albumname)

        for photo in photos:
            hash_of_photo = calculate_hash_of_file(photo['source'])

            #check if the proto has been uploaded yet or not
            photo_ids = self.get_photo_ids_for_hash(hash_of_photo)

            if not photo_ids:
                #if hasn't uploaded ==> upload, add album and save hashCode
                event_handler.fire('Upload file: %s (%s) \n'
                        % (photo['filename'], photo['file_size']))
                photoid = self.upload_file(photo, hash_prefix + hash_of_photo)
                if photoid:
                    albumid = self.get_albumid_for_albumname(albumname)
                    self.add_photo_to_album(albumid, photoid)
                    append_to_hash_file(photo['dirname'], hash_photos,
                            photo['filename'], hash_of_photo)
                    event_handler.fire('\n %s uploaded and in your album (%s).\n'
                            % (photo['filename'], albumname))
                else:
                    event_handler.fire(
                            '\n(%s): Sorry. Something went wrong during the upload.\n'
                            % (photo['filename']))
            else:
                #photo was uploaded but wasnt is the given album (add to album)
                albums = self.get_flickr_albums_for_photo_ids(photo_ids)
                if (albumname not in albums):
                    event_handler.fire('The photo (%s) has been uploaded before.\n'
                            % (photo['filename']))
                    albumid = self.get_albumid_for_albumname(albumname)
                    self.add_photo_to_album(albumid, photo_ids[0])
                    append_to_hash_file(photo['dirname'], hash_photos,
                            photo['filename'], hash_of_photo)
                    event_handler.fire('%s in your album (%s). \n' % (photo['filename'], albumname))
                else:
                    #the photo was in the album, but the hash code was missing from hash_file
                    append_to_hash_file(photo['dirname'], hash_photos, photo['filename'], hash_of_photo)
                    event_handler.fire("The photo (%s) has already been in the album (%s). There's nothing to do.\n"
                            %(photo['filename'], albumname))

    def create_and_update_flickr_album(self, photos, albumname):
        if self.is_existed_album(albumname):
            self.update_flickr_album(photos, albumname)
        elif photos:
            #in flickr, you need to uplolad at least one photo
            #for a new album (cannot creat empty album)
            photo = photos.pop()

            hash_of_photo = calculate_hash_of_file(photo['source'])

            #check if the proto has been uploaded yet or not
            photo_ids = self.get_photo_ids_for_hash(hash_of_photo)
            if not photo_ids:
                #if hasn't uploaded ==> upload, add album and save hashCode
                event_handler.fire('Upload file: %s (%s) \n'
                        % (photo['filename'], photo['file_size']))
                photoid = self.upload_file(photo, hash_prefix + hash_of_photo)
                if photoid:
                    #create album:
                    album = self.create_album_if_not_existed(albumname, photoid)
                    append_to_hash_file(photo['dirname'], hash_album,
                            hash_album, album)
                    append_to_hash_file(photo['dirname'], hash_photos,
                            photo['filename'], hash_of_photo)
                    event_handler.fire(' %s uploaded and in your album (%s). \n'
                            % (photo['filename'], albumname))
                    self.update_flickr_album(photos, albumname)
                else:
                    event_handler.fire(
                            '(%s): Sorry. Something went wrong during the upload.\n'
                            % (photo['filename']))
                    self.create_and_update_flickr_album(photos, albumname)

            else:
                event_handler.fire('The photo (%s) has been uploaded before.\n'
                        % (photo['filename']))
                #create album:
                album = self.create_album_if_not_existed(albumname, photo_ids[0])
                self.create_and_update_flickr_album(photos, albumname)
                append_to_hash_file(photo['dirname'], hash_album,
                        hash_album, album)
                append_to_hash_file(photo['dirname'], hash_photos,
                        photo['filename'], hash_of_photo)
                event_handler.fire('%s in your album (%s).\n'
                        % (photo['filename'], albumname))
                self.update_flickr_album(photos, albumname)
        else:
            event_handler.fire('No photos. Album cannot be created.\n')

    def update_or_create_album(self, photos, albumname):
        """Decides wether the given album has to be created or just update it"""
        user_id = self.get_userid()
        if self.is_existed_album(albumname):
            #if the album exists ==> update
            event_handler.fire('Update your album: %s\n' % (albumname))
            self.update_flickr_album(photos, albumname)
            event_handler.fire(
                    'Your album (%s) is up to date now. See you later!'
                    % (albumname))
        else:
            #if the album doesn't exist ==> create it and update
            event_handler.fire('Create new album with files: %s\n' % (albumname))
            self.create_and_update_flickr_album(photos, albumname)
            event_handler.fire(
                    'Your album (%s) is created and up to date now. See you later!\n'
                    % (albumname))

    def upload(self, data, albumname):
        """Upload the given data"""
        path = os.path.dirname(data[0]['source'])
        if not albumname:
            event_handler.fire('No selected album. Uploading failed.\n')
            return
        event_handler.fire('New photo(s): %d \n' % (len(data)))
        self.update_or_create_album(data, albumname)

    def upload_all(self, path, albumname):
        """Upload all media files from the given folder"""
        data = self.get_all_photos_data(path)
        uploadable = [photo for photo in data if photo['uploaded'] == False]
        event_handler.fire('New photo(s): %d \n' % (len(uploadable)))
        self.update_or_create_album(uploadable, albumname)

