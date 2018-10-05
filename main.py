import os, sys, io
import threading
from ffpyplayer.player import MediaPlayer
from ffpyplayer.tools import get_supported_pixfmts
from ffpyplayer.writer import MediaWriter
from ffpyplayer.pic import SWScale
from kivy.app import App
from kivy.clock import Clock
from kivy.core.image import ImageLoader
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.loader import Loader
from kivy.properties import ObjectProperty, NumericProperty, StringProperty, BooleanProperty, ListProperty
from kivy.uix.behaviors import FocusBehavior
from kivy.uix.image import AsyncImage
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.recyclegridlayout import RecycleGridLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.layout import LayoutSelectionBehavior
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.screenmanager import Screen, ScreenManager, NoTransition
from kivy.utils import platform
from PIL import Image as PILImage
from functools import partial
import event
import flickrUploader
from flickrUploader import FlickrUploader

#os.environ['KIVY_VIDEO'] = 'ffpyplayer'

if platform == "win":
    Window.maximize()

Builder.load_file('photo.kv')

def save_video_thumbnail(source, output):
    """Saves thumbnail of the given video under the given name"""
    player = MediaPlayer(source, ff_opts = {'ss': 1.0})
    frame, val  = None, None
    while not frame:
        frame, val = player.get_frame(force_refresh = True)
    player.close_player()
    if val == 'eof':
        return None
    elif frame is None:
        return None
    else:
        img = frame[0]
        pixel_format = img.get_pixel_format()
        img_size = img.get_size()
        thumb_size = 256, int(img_size[1] * 256 / img_size[0])
        codec = 'tiff'
        output_format = get_supported_pixfmts(codec, pixel_format)[0]
        #resize and convert into the best pixel format
        sws = SWScale(img_size[0], img_size[1], pixel_format, thumb_size[0], thumb_size[1], output_format)
        thumbnail = sws.scale(img)
        streams = [{'pix_fmt_in': output_format, 'width_in': thumb_size[0], 
            'height_in': thumb_size[1], 'codec': codec, 'frame_rate': (30, 1)}]
        writer = MediaWriter(output, streams, lib_opts ={'compression_algo': 'lzw'})
        writer.write_frame(img=thumbnail, pts=0, stream=0)
        writer.close()

def save_image_thumbnail(source, output, orientation):
    """Saves thumbnail of the given image under the given name"""
    im = PILImage.open(source)
    #rotation according to the exif orientation data
    if orientation == 3:
        im = im.rotate(180)
    if orientation == 6:
        im = im.rotate(270, expand = True)
    if orientation == 8:
        im = im.rotate(90, expand = True)
    width, height = im.size
    size = 256, int(height * 256 / width)
    im.thumbnail(size, PILImage.ANTIALIAS)
    im.save(output, 'jpeg')

def get_thumbnail(source, orientation, **kwargs):
    orig_dir = os.path.dirname(source)
    orig_name, orig_ext= os.path.splitext(os.path.basename(source).lower())
    thumb_dir = os.path.join(orig_dir, 'thumb')
    thumb_name = 't_'+ orig_name + '.jpg'
    thumb_path = os.path.join(thumb_dir, thumb_name)

    if os.path.exists(thumb_path):
        return ImageLoader.load(thumb_path, keep_data=True, **kwargs)
    else:
        try:
            os.makedirs(thumb_dir, exist_ok = True)
            if orig_ext in flickrUploader.image_ext:
                save_image_thumbnail(source, thumb_path, orientation)
            elif orig_ext in flickrUploader.video_ext:
                save_video_thumbnail(source, thumb_path)
            return ImageLoader.load(thumb_path, keep_data=True, **kwargs)
        except Exception as e:
            print("no thumbnail for file: %s" %source)
            return None

class MessageDisplayer(Popup):
    messege = StringProperty("")

    def __init__(self, **kwargs):
        self.message = ""
        self.register_event_type('on_close')
        super(MessageDisplayer, self).__init__(**kwargs)

    def display_message(self, message):
        """Append message"""
        self.ids['message'].text += message

    def on_close(self, *args):
        pass

class AlbumPopup(Popup):
    inputText = StringProperty("")

    def __init__(self, **kwargs):
        self.register_event_type('on_close')
        super(AlbumPopup, self).__init__(**kwargs)

    def on_close(self, *args):
        pass

class RecyclePhotoView(RecycleView):

    def __init__(self, **kwargs):
        super(RecyclePhotoView, self).__init__(**kwargs)

class SelectableRecycleGridLayout(FocusBehavior, LayoutSelectionBehavior,
        RecycleGridLayout):

    def set_selection(self, data, selected_names):
        for index in range(len(data)):
            if not data[index]['uploaded'] and data[index]['filename'] in selected_names:
                self.select_node(index)
            else:
                self.deselect_node(index)

class PhotoImage(AsyncImage):
    orient = NumericProperty(1)

    def _load_source(self, *args):
        """Overwritten method for loading thumbnail of image"""
        source = self.source
        if not source:
            if self._coreimage is not None:
                self._coreimage.unbind(on_texture=self._on_tex_change)
                self._coreimage.unbind(on_load=self._on_source_load)
            self.texture = None
            self._coreimage = None
        else:
            Loader.max_upload_per_frame = 10
            self._coreimage = image = Loader.image(source,
                    load_callback = self.get_thumbnail,
                    nocache=self.nocache, mipmap=self.mipmap,
                    anim_delay=self.anim_delay)
            image.bind(on_load=self._on_source_load)
            image.bind(on_error=self._on_source_error)
            image.bind(on_texture=self._on_tex_change)
            self.texture = image.texture

    def get_thumbnail(self, filename):
        return get_thumbnail(filename, self.orient)

class SelectableImage(RecycleDataViewBehavior, BoxLayout):
    ''' Add selection support to the Label '''
    index = None
    selected = BooleanProperty(False)
    selectable = BooleanProperty(True)
    is_video = BooleanProperty(False)
    data = {}
    title = StringProperty("")

    def refresh_view_attrs(self, rv, index, data):
        ''' Catch and handle the view changes '''
        '''Triggers, when the image is changed eg. the photo directory is changed'''
        self.index = index
        self.data = data
        self.title = data['filename'] #shown on the screen
        self.selectable = not data['uploaded'] #need to show on the screen
        self.is_video = data['video']
        photo_widget = self.ids['async_photo']
        photo_widget.source = data['source']
        photo_widget.orient = data['orient']
        return super(SelectableImage, self).refresh_view_attrs(
            rv, index, data)

    def on_touch_down(self, touch):
        ''' Add selection on touch down '''
        if super(SelectableImage, self).on_touch_down(touch):
            return True
        if self.collide_point(*touch.pos) and self.selectable:
            return self.parent.select_with_touch(self.index, touch)

    def apply_selection(self, rv, index, is_selected):
        ''' Respond to the selection of items in the view. '''
        if is_selected and not rv.data[index]['uploaded']:
            self.selected = True
        else:
            self.selected = False

class MainScreen(Screen):
    path = StringProperty("") #selected path
    flickr_album = StringProperty("") #flickr album for the current folder
    albums = ListProperty([]) # flickr album titles of the user
    selected_album = StringProperty("") #selected album, only if there is no flickr album
    data = ListProperty([]) #photo info list
    sorting_modes = ["Alphabetically (A-Z)",
            "Alphabetically (Z-A)",
            "Date taken (oldest first)",
            "Date taken (newest first)",
            "Date modified (newest first)",
            "Date modified (oldest first)"]
    sorted_mode = sorting_modes[0]
    popup = ObjectProperty(None, allownone = True)

    def on_enter(self):
        """Event fired when the screen is displayed. Sets variables"""
        app = App.get_running_app()
        self.path = r'C:\Users'
        self.albums = app.get_albums()
        self.selected_album = ""
        self.clear_selection()
        self.set_filechooser_pathes()
        self.on_changed()

    def on_changed(self):
        """Calls when a change is occurred"""
        app = App.get_running_app()
        self.clear_selection()
        self.data = app.get_data(self.path)
        self.flickr_album = flickrUploader.read_album_from_config(self.path)
        self.sort_data(self.sorted_mode)
        self._trigger_layout

    def set_path(self, path):
        """Sets new photo path and load data"""
        if path != self.path:
            self.path = path
            self.selected_album = ""
            self.set_filechooser_pathes()
            self.on_changed()

    def set_filechooser_pathes(self):
        filechooser = self.ids['filechooser']
        parent_path = os.path.dirname(self.path)
        filechooser.path = parent_path
        filechooser.rootpath = os.path.dirname(parent_path)

    def upload(self):
        selected_data = self.get_selected_data()
        if not selected_data:
            return

        #set event handler and message displayer
        popup = MessageDisplayer()
        popup.bind(on_close = self.close_popup)
        popup.ids['ok_btn'].disabled = True
        self.popup = popup
        self.popup.open()
        event_handler = event.flickEvent
        event_handler.add_handler(self.popup.display_message)
        upload_thread = threading.Thread(target = self.upload_data, args = (selected_data,))
        upload_thread.start()

    def upload_data(self, data, *largs):
        app = App.get_running_app()
        if self.flickr_album:
            app.upload(data, self.flickr_album)
        else:
            album = self.ids['albums'].text
            if album:
                app.upload(data, album)
        self.popup.ids['ok_btn'].disabled = False
        event_handler = event.flickEvent
        event_handler.remove_handler(self.popup.display_message)
        self.on_changed()
        self.albums = app.get_albums()

    def add_album(self):
        """Opens a popup dialog"""
        popup = AlbumPopup()
        popup.bind(on_close = self.add_new_album)
        self.popup = popup
        self.popup.open()

    def add_new_album(self, instance, reply):
        if reply == "OK":
            if instance is not None:
                #TODO: check if album is ascii / utf-8
                album = instance.ids['albumname'].text
            if album:
                self.albums.append(album)
                albums = self.ids['albums']
                albums.values = self.albums
                albums.text = album
        self.dismiss_popup()

    def close_popup(self, instance, reply):
        self.dismiss_popup()

    def dismiss_popup(self):
        """Closes and removes popup """
        if self.popup:
            self.popup.dismiss()
            self.popup = None

    def get_selected_data(self):
        """Retrun all details of the selected photos"""
        selected = []
        photos = self.ids['photos']
        for index in photos.selected_nodes:
            if not self.data[index]['uploaded']:
                selected.append(self.data[index])
        return selected

    def get_selected_names(self):
        """Retrurns the names of the selected photos"""
        selected = []
        photos = self.ids['photos']
        for index in photos.selected_nodes:
            if not self.data[index]['uploaded']:
                selected.append(self.data[index]['filename'])
        return selected

    def sort_data(self, sort_method):
        """Sorting data"""
        self.sorted_mode = sort_method
        selected_names = self.get_selected_names()
        data = self.data
        sorted_data =self.data
        if sort_method == 'Date taken (newest first)':
            sorted_data = sorted(data, key = lambda x: x['date_taken'], reverse = True)
        if sort_method == 'Date taken (oldest first)':
            sorted_data = sorted(data, key = lambda x: x['date_taken'])

        if sort_method == 'Date modified (newest first)':
            sorted_data = sorted(data, key = lambda x: x['date_modif'], reverse = True)
        if sort_method == 'Date modified (oldest first)':
            sorted_data = sorted(data, key = lambda x: x['date_modif'], reverse = True)
        
        if sort_method == 'Alphabetically (A-Z)':
            sorted_data = sorted(data, key = lambda x: x['filename'])
        if sort_method == 'Alphabetically (Z-A)':
            sorted_data = sorted(data, key = lambda x: x['filename'], reverse = True)

        self.data = sorted_data
        self.update_photo_containers(self.data, selected_names)
        self._trigger_layout

    def clear_selection(self):
        photos = self.ids['photos']
        photos.clear_selection()

    def update_photo_containers(self, data, selected_names):
        photo_cont = self.ids['photos_cont']
        photo_cont.data = data
        photos = self.ids['photos']
        photos.set_selection(data, selected_names)

class FlickrUploaderApp(App):
    main_layout = ObjectProperty()
    screen_manager = ObjectProperty()

    flickr = ObjectProperty()
    flickr_user = StringProperty("")
  
    button_height = NumericProperty(40)

    def build(self):
        #set flickr data
        self.flickr = FlickrUploader(permit = 'write')
        self.flickr_user = self.flickr.get_username()

        #set main layout
        self.main_layout = FloatLayout()
        self.screen_manager = ScreenManager(transition = NoTransition())
        self.main_layout.add_widget(self.screen_manager)
        self.screen_manager.add_widget(MainScreen(name='mainScreen'))
        self.screen_manager.current = 'mainScreen'

        mainScreen = self.screen_manager.get_screen('mainScreen')
        return self.main_layout

    def get_data(self, path):
        return self.flickr.get_all_photos_data(path)

    def get_albums(self):
        return self.flickr.get_flickr_album_titles()

    def upload(self, data, album):
        self.flickr.upload(data, album)

if __name__ == '__main__':

    FlickrUploaderApp().run()

