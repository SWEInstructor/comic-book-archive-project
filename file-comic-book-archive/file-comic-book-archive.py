#!/usr/bin/env python3

# GIMP Plug-in for the Comic Book Archive File Format

# Copyright (C) 2024 by YOU <YOU@YOU.COM>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.

import gi

gi.require_version('Gimp', '3.0')
from gi.repository import Gimp

gi.require_version('Gegl', '0.4')
from gi.repository import Gegl
from gi.repository import GObject
from gi.repository import GLib
from gi.repository import Gio

import os, sys, tarfile, tempfile, zipfile
import xml.etree.ElementTree as ET

#Function that loads the thumbnail of the CBZ
#TODO: Code is very similar to loading the first image in the CBZ,
#Could we reduce the code duplication by making a new function that
#both call?
def thumbnail_comic_book_archive(procedure, file, thumb_size, args, data):
    tempdir = tempfile.mkdtemp('gimp-plugin-comic-book-archive')
    cbaffFile = zipfile.ZipFile(file.peek_path())

    file_info_list = cbaffFile.infolist()
    filename = ''

    for file_info in file_info_list:
        if file_info.filename.endswith('jpg' or 'jpeg' or 'png' or 'tiff' or 'gif'):
            filename = file_info.filename
            break

    tmp = os.path.join(tempdir, 'tmp.jpeg')
    with open(tmp, 'wb') as fid:
        fid.write(cbaffFile.read(filename))

    thumb_file = Gio.file_new_for_path(tmp)
    pdb_proc = None
    if filename.endswith('jpg' or 'jpeg'):
        pdb_proc = Gimp.get_pdb().lookup_procedure('file-jpeg-load')
    elif filename.endswith('png'):
        pdb_proc = Gimp.get_pdb().lookup_procedure('file-png-load')
    elif filename.endswith('tiff'):
        pdb_proc = Gimp.get_pdb().lookup_procedure('file-tiff-load')
    elif filename.endswith('gif'):
        pdb_proc = Gimp.get_pdb().lookup_procedure('file-gif-load')
    pdb_config = pdb_proc.create_config()
    pdb_config.set_property('run-mode', Gimp.RunMode.NONINTERACTIVE)
    pdb_config.set_property('file', thumb_file)
    result = pdb_proc.run(pdb_config)
    os.remove(tmp)
    os.rmdir(tempdir)

    img = result.index(1)

    return Gimp.ValueArray.new_from_values([
        GObject.Value(Gimp.PDBStatusType, Gimp.PDBStatusType.SUCCESS),
        GObject.Value(Gimp.Image, img)
    ])


#Function that actually loads the CBZ file
def load_comic_book_archive(procedure, run_mode, file, metadata, flags, config, data):
    #Making a temporary folder to unzip the .cbz files to
    tempdir = tempfile.mkdtemp('gimp-plugin-comic-book-archive')
    #Load the file the user wants to import to the Zipfile object
    cbaffFile = zipfile.ZipFile(file.peek_path())

    #List of all files in the .cbz file
    #TODO: Is there a way to sort these so we load the image in order?
    file_info_list = cbaffFile.infolist()
    layer_names = []

    #Loop through all files
    for file_info in file_info_list:
        #Check if the end with a valid extension
        #TODO: Verify this actually does filter valid files
        if file_info.filename.endswith('jpg' or 'jpeg' or 'png' or 'tiff' or 'gif' or 'bmp'):
            #Add the name to a list to use later
            layer_names.append(file_info.filename)

    #Create an Image object
    img = Gimp.Image.new(1, 1, Gimp.ImageBaseType.RGB)
    w, h = 1, 1
    index = 0
    #Loop through all the images, and repeat this algorithm
    for file in layer_names:
        #Create a temporary file to load a layer into
        #TODO: What if it's not a JPEG? Can we make this more flexible?
        tmp = os.path.join(tempdir, 'tmp.jpeg')
        with open(tmp, 'wb') as fid:
            #Write the file from the .cbz to the temporary file
            fid.write(cbaffFile.read(file))

        #Call the Load Layer function and get the temporary image back as a Layer object
        pdb_proc = Gimp.get_pdb().lookup_procedure('gimp-file-load-layer')
        pdb_config = pdb_proc.create_config()
        pdb_config.set_property('run-mode', Gimp.RunMode.NONINTERACTIVE)
        pdb_config.set_property('image', img)
        pdb_config.set_property('file', Gio.file_new_for_path(tmp))

        #Run the function and get the result
        #TODO: What if the file can't be loaded? What should we do?
        result = pdb_proc.run(pdb_config)

        layer = result.index(1)
        #Get the layer's dimensions
        w, h = layer.get_width(), layer.get_height()
        #Get the layer name from the original image
        layer.set_name(layer_names[index])
        #Add the layer to the image
        img.insert_layer(layer, None, -1)
        #Delete the temporary file
        os.remove(tmp)
        index += 1

    #Resize the image to fit the layers
    #TODO: What if the last layer is smaller than the first?
    #Is there another way to do this?
    img.resize(w, h, 0, 0)

    #Delete the temporary folder
    os.rmdir(tempdir)
    #Finally, send the completed image to the software to be drawn on the screen
    return Gimp.ValueArray.new_from_values([
        GObject.Value(Gimp.PDBStatusType, Gimp.PDBStatusType.SUCCESS),
        GObject.Value(Gimp.Image, img)
    ]), flags


class FileComicBookArchive(Gimp.PlugIn):
    ## GimpPlugIn virtual methods ##
    def do_set_i18n(self, procname):
        return True, 'gimp30-python', None

    def do_query_procedures(self):
        return ['file-comic-book-archive-load-thumb',
                'file-comic-book-archive-load', ]

    def do_create_procedure(self, name):
        if name == 'file-comic-book-archive-load':
            procedure = Gimp.LoadProcedure.new(self, name,
                                               Gimp.PDBProcType.PLUGIN,
                                               load_comic_book_archive, None)
            procedure.set_menu_label('CBZ')
            procedure.set_documentation('load a Comic Book Archive file',
                                        'load a Comic Book Archive file',
                                        name)
            procedure.set_mime_types("application/vnd.comicbook+zip");
            procedure.set_extensions("cbz");
            procedure.set_thumbnail_loader('file-comic-book-archive-load-thumb');
        else:  # 'file-comic-book-archive-load-thumb':
            procedure = Gimp.ThumbnailProcedure.new(self, name,
                                                    Gimp.PDBProcType.PLUGIN,
                                                    thumbnail_comic_book_archive, None)
            procedure.set_documentation('loads a thumbnail from a Comic Book Archive file',
                                        'loads a thumbnail from a Comic Book Archive file',
                                        name)

            procedure.set_attribution('<YOU>',  # author
                                      '<YOU>',  # copyright
                                      '2024')  # year

        return procedure


Gimp.main(FileComicBookArchive.__gtype__, sys.argv)
