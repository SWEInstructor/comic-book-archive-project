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
    tempdir = tempfile.mkdtemp('gimp-plugin-comic-book-archive')
    cbaffFile = zipfile.ZipFile(file.peek_path())

    # Check if the CBZ file contains a directory structure
    contains_directories = any('/' in file_info.filename for file_info in cbaffFile.infolist())

    if contains_directories:
        # Extract files into a folder preserving directory structure
        cbaffFile.extractall(tempdir)
        cbz_files = [os.path.join(root, file) for root, _, files in os.walk(tempdir) for file in files]
    else:
        cbz_files = [file_info.filename for file_info in cbaffFile.infolist()]

    # Sort the file names to load images in order
    cbz_files.sort(key=lambda x: ntpath.basename(x).lower())

    layer_names = []

    for file_name in cbz_files:
        # Check if the file name ends with one of the specified extensions
        if file_name.lower().endswith(('jpg', 'jpeg', 'png', 'tiff', 'gif', 'bmp')):
            # Check if the file name exists in the CBZ archive's list of file information
            if file_name in cbaffFile.namelist():
                layer_names.append(file_name)
            else:
                print("Warning: File {} not found in CBZ archive. Skipping...".format(file_name))
        else:
            print("Warning: File {} has an unsupported format. Skipping...".format(file_name))

    # Determine the maximum dimensions among all layers
    max_width, max_height = 1, 1
    for file_name in layer_names:
        tmp = os.path.join(tempdir, file_name)
        with open(tmp, 'wb') as fid:
            fid.write(cbaffFile.read(file_name))

        img_width, img_height = Gimp.get_pdb().file_png_size(tmp)  # Get dimensions without loading the image
        max_width = max(max_width, img_width)
        max_height = max(max_height, img_height)

        os.remove(tmp)

    # Create a new image with the maximum dimensions
    img = Gimp.Image.new(max_width, max_height, Gimp.ImageBaseType.RGB)

    index = 0

    def create_layer_group(layer_names):
        group = Gimp.get_pdb().gimp_layer_group_new(img)
        group.set_name("Group_" + str(index))

        for file_name in layer_names:
            tmp = os.path.join(tempdir, file_name)
            with open(tmp, 'wb') as fid:
                fid.write(cbaffFile.read(file_name))

            pdb_proc = None
            if file_name.lower().endswith(('jpg', 'jpeg')):
                pdb_proc = Gimp.get_pdb().lookup_procedure('file-jpeg-load')
            elif file_name.lower().endswith('png'):
                pdb_proc = Gimp.get_pdb().lookup_procedure('file-png-load')
            elif file_name.lower().endswith('tiff'):
                pdb_proc = Gimp.get_pdb().lookup_procedure('file-tiff-load')
            elif file_name.lower().endswith('gif'):
                pdb_proc = Gimp.get_pdb().lookup_procedure('file-gif-load')
            elif file_name.lower().endswith('bmp'):
                pdb_proc = Gimp.get_pdb().lookup_procedure('file-bmp-load')

            if pdb_proc:
                pdb_config = pdb_proc.create_config()
                pdb_config.set_property('run-mode', Gimp.RunMode.NONINTERACTIVE)
                pdb_config.set_property('file', Gio.file_new_for_path(tmp))
                result = pdb_proc.run(pdb_config)
                if result.return_status == Gimp.PDBStatusType.SUCCESS:
                    layer = result.index(1)
                    layer.set_name(ntpath.basename(file_name))
                    group.add_layer(layer)
                else:
                    print("Error loading file:", file_name)
            else:
                print("Unsupported file format:", file_name)

            os.remove(tmp)

        return group

    def insert_layer_group(group):
        Gimp.get_pdb().gimp_image_insert_layer(img, group, None, -1)

    def process_files(layer_names):
        nonlocal index
        group = create_layer_group(layer_names)
        insert_layer_group(group)
        index += 1

    if contains_directories:
        process_files(layer_names)
    else:
        process_files(layer_names)

    os.rmdir(tempdir)  # Remove temporary directory after processing

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