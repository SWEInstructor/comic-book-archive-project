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
gi.require_version('GimpUi', '3.0')
from gi.repository import GimpUi
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
def thumbnail_cbz(procedure, file, thumb_size, args, data):
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

#Wrapper function that passes the Zipfile object to load_image()
def load_cbz(procedure, run_mode, file, metadata, flags, config, data):
    compression = zipfile.ZipFile(file.peek_path())
    return load_image(procedure, run_mode, file, metadata, flags, config, data, compression)

#Wrapper function that passes the Tarfile object to load_image()
def load_cbt(procedure, run_mode, file, metadata, flags, config, data):
    compression = tarfile.open(file.peek_path(), 'r')
    return load_image(procedure, run_mode, file, metadata, flags, config, data, compression)

#Function that actually loads the Comic Book Archive file
def load_image(procedure, run_mode, file, metadata, flags, config, data, compression):
    #Making a temporary folder to unzip the .cbz/.cbt files to
    tempdir = tempfile.mkdtemp('gimp-plugin-comic-book-archive')

    #List of all files in the .cbz/.cbt file
    # isinstance() is used to determine what file format we're loading
    if (isinstance(compression, zipfile.ZipFile)):
        file_info_list = compression.infolist()
    elif (isinstance(compression, tarfile.TarFile)):
        file_info_list = compression.getmembers()
    layer_names = []

    # Valid file endings
    extensions = ['jpg', 'jpeg', 'png', 'tiff', 'gif', 'bmp']
    # Loop through all files
    #TODO: Is there a way to sort these so we load the image in order?
    for file_info in file_info_list:
        filename = ""
        if (isinstance(compression, zipfile.ZipFile)):
            filename = file_info.filename
        elif (isinstance(compression, tarfile.TarFile)):
            filename = file_info.name

        # Check if the end with a valid extension
        # TODO: Verify this actually does filter valid files
        if filename.endswith(tuple(extensions)):
            # Add the name to a list to use later
            layer_names.append(filename)
        else:
            print("Unsupported layer format")

    #Create an Image object
    img = Gimp.Image.new(1, 1, Gimp.ImageBaseType.RGB)
    w, h = 1, 1
    index = 0
    #Loop through all the images, and repeat this algorithm
    for file in layer_names:
        #Create a temporary file to load a layer into
        #TODO: What if it's not a JPEG? Can we make this more flexible?

        if (isinstance(compression, zipfile.ZipFile)):
            tmp = os.path.join(tempdir, 'tmp.jpeg')
            with open(tmp, 'wb') as fid:
                fid.write(compression.read(file))
        elif (isinstance(compression, tarfile.TarFile)):
            compression.extract(file, tempdir)
            tmp = os.path.join(tempdir, file)

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
        #Get the largest layer's dimensions
        if (w < layer.get_width()):
            w = layer.get_width()
        if (h < layer.get_height()):
            h = layer.get_height()

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

def save_cbz(procedure, run_mode, image, n_drawables, drawables, file, metadata, config, data):
    def write_file_str(zfile, fname, data):
        zi = zfile.ZipInfo(fname)
        zi.external_attr = int("100644", 8) << 16
        zfile.writestr(zi, data)

    Gimp.progress_init("Exporting Comic Book Archive (cbz) image")

    #GUI Code
    if run_mode == Gimp.RunMode.INTERACTIVE:
        GimpUi.init('python-fu-file-cbz-save')

        #Search for this in the repository and see what else you can do
        dialog = GimpUi.ProcedureDialog(procedure=procedure, config=config)
        dialog.fill(None)
        if not dialog.run():
            dialog.destroy()
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())
        else:
            dialog.destroy()

    #Example of how to access user input
    print(config.get_property('title'))

    tempdir = tempfile.mkdtemp('gimp-plugin-file-cbz')
    cbaffFile = zipfile.ZipFile(file.peek_path() + '.tmpsave', 'w', compression=zipfile.ZIP_STORED)

    def store_layer(image, drawable, path):
        tmp = os.path.join(tempdir, 'tmp.jpeg')
        pdb_proc = Gimp.get_pdb().lookup_procedure('file-jpeg-save')
        pdb_config = pdb_proc.create_config()
        pdb_config.set_property('run-mode', Gimp.RunMode.NONINTERACTIVE)
        pdb_config.set_property('image', image)
        pdb_config.set_property('num-drawables', 1)
        pdb_config.set_property('drawables', Gimp.ObjectArray.new(Gimp.Drawable, [drawable], False))
        pdb_config.set_property('file', Gio.File.new_for_path(tmp))
        pdb_proc.run(pdb_config)
        if (os.path.exists(tmp)):
            cbaffFile.write(tmp, path)
            os.remove(tmp)
        else:
            print("Error removing ", tmp)

    layers = image.list_layers()
    print(layers)
    for page in layers:
        layer_name = page.get_name()
        page = image.merge_visible_layers(Gimp.MergeType.CLIP_TO_IMAGE)
        store_layer(image, page, layer_name)

    cbaffFile.close()
    os.rmdir(tempdir)
    if os.path.exists(file.peek_path()):
        os.remove(file.peek_path())
    os.rename(file.peek_path() + '.tmpsave', file.peek_path())

    Gimp.progress_end()

    return Gimp.ValueArray.new_from_values([
        GObject.Value(Gimp.PDBStatusType, Gimp.PDBStatusType.SUCCESS)
    ])
class FileComicBookArchive(Gimp.PlugIn):
    ## Parameters ##
    __gproperties__ = {
        "save-metadata": (bool,
                          ("Save metadata"),
                          ("Save metadata in ComicInfo format"),
                          False,
                          GObject.ParamFlags.READWRITE),
        "title": (str,
                 ("Title"),
                 ("Book Title"),
                 "",
                 GObject.ParamFlags.READWRITE),
    }

    ## GimpPlugIn virtual methods ##
    def do_set_i18n(self, procname):
        return True, 'gimp30-python', None

    def do_query_procedures(self):
        return ['file-cbz-thumb',
                'file-cbz-load',
                'file-cbt-load',
                'file-cbz-save']

    def do_create_procedure(self, name):
        if name == 'file-cbz-load':
            procedure = Gimp.LoadProcedure.new(self, name,
                                               Gimp.PDBProcType.PLUGIN,
                                               load_cbz, None)
            procedure.set_menu_label('CBZ')
            procedure.set_documentation('load a Comic Book Archive (.cbz) file',
                                        'load a Comic Book Archive (.cbz) file',
                                        name)
            procedure.set_mime_types("application/vnd.comicbook+zip");
            procedure.set_extensions("cbz");
            procedure.set_thumbnail_loader('file-cbz-thumb');
        elif name == 'file-cbt-load':
            procedure = Gimp.LoadProcedure.new(self, name,
                                               Gimp.PDBProcType.PLUGIN,
                                               load_cbt, None)
            procedure.set_menu_label('CBT')
            procedure.set_documentation('load a Comic Book Archive (.cbt) file',
                                        'load a Comic Book Archive (.cbt) file',
                                        name)
            procedure.set_mime_types("application/vnd.comicbook+tar");
            procedure.set_extensions("cbt");
            #procedure.set_thumbnail_loader('file-cbz-thumb');
        elif name == 'file-cbz-save':
            procedure = Gimp.SaveProcedure.new(self, name,
                                               Gimp.PDBProcType.PLUGIN,
                                               False, save_cbz, None)
            procedure.set_image_types("*");
            procedure.set_documentation('save a Comic Book Archive (.cbz) file',
                                        'save a Comic Book Archive (.cbz) file',
                                        name)
            procedure.set_menu_label('CBZ')
            procedure.set_extensions("cbz");

            #Adding parameters for GUI
            procedure.add_argument_from_property(self, "save-metadata")
            procedure.add_argument_from_property(self, "title")
        elif name == 'file-cbz-thumb':
            procedure = Gimp.ThumbnailProcedure.new(self, name,
                                                    Gimp.PDBProcType.PLUGIN,
                                                    thumbnail_cbz, None)
            procedure.set_documentation('loads a thumbnail from a Comic Book Archive (.cbz) file',
                                        'loads a thumbnail from a Comic Book Archive (.cbz) file',
                                        name)

            procedure.set_attribution('<YOU>',  # author
                                      '<YOU>',  # copyright
                                      '2024')  # year

        return procedure



Gimp.main(FileComicBookArchive.__gtype__, sys.argv)
