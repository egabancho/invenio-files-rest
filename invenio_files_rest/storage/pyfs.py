# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2016 CERN.
#
# Invenio is free software; you can redistribute it
# and/or modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# Invenio is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Invenio; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place, Suite 330, Boston,
# MA 02111-1307, USA.
#
# In applying this license, CERN does not
# waive the privileges and immunities granted to it by virtue of its status
# as an Intergovernmental Organization or submit itself to any jurisdiction.

"""Storage related module."""

from __future__ import absolute_import, print_function

from flask import current_app
from fs.opener import opener
from fs.path import basename, dirname

from ..helpers import make_path
from .base import FileStorage


class PyFSFileStorage(FileStorage):
    """File system storage using PyFilesystem for access the file.

    This storage class will store files according to the following pattern:
    ``<base_uri>/<file instance uuid>/data``.

    .. warning::

       File operations are not atomic. E.g. if errors happens during e.g.
       updating part of a file it will leave the file in an inconsistent
       state. The storage class tries as best as possible to handle errors
       and leave the system in a consistent state.

    """

    def __init__(self, fileurl, size=None, modified=None, clean_dir=True):
        """Storage initialization."""
        self.fileurl = fileurl
        self.clean_dir = clean_dir
        super(PyFSFileStorage, self).__init__(size=size, modified=modified)

    def _get_fs(self, create_dir=True):
        """Return tuple with filesystem and filename."""
        filedir = dirname(self.fileurl)
        filename = basename(self.fileurl)

        return (
            opener.opendir(filedir, writeable=True, create_dir=create_dir),
            filename
        )

    def open(self, mode='rb'):
        """Open file.

        The caller is responsible for closing the file.
        """
        fs, path = self._get_fs()
        return fs.open(path, mode=mode)

    def delete(self):
        """Delete a file.

        The base directory is also removed, as it is assumed that only one file
        exists in the directory.
        """
        fs, path = self._get_fs(create_dir=False)
        if fs.exists(path):
            fs.remove(path)
        if self.clean_dir and fs.exists('.'):
            fs.removedir('.')
        return True

    def initialize(self, size=0):
        """Initialize file on storage and truncate to given size."""
        fs, path = self._get_fs()

        # Required for reliably opening the file on certain file systems:
        if fs.exists(path):
            fp = fs.open(path, mode='r+b')
        else:
            fp = fs.open(path, mode='wb')

        try:
            fp.truncate(size)
        except Exception:
            fp.close()
            self.delete()
            raise
        finally:
            fp.close()

        self._size = size

        return self.fileurl, size, None

    def save(self, incoming_stream, size_limit=None, size=None,
             chunk_size=None, progress_callback=None):
        """Save file in the file system."""
        fp = self.open(mode='wb')
        try:
            bytes_written, checksum = self._write_stream(
                incoming_stream, fp, chunk_size=chunk_size,
                progress_callback=progress_callback,
                size_limit=size_limit, size=size)
        except Exception:
            fp.close()
            self.delete()
            raise
        finally:
            fp.close()

        self._size = bytes_written

        return self.fileurl, bytes_written, checksum

    def update(self, incoming_stream, seek=0, size=None, chunk_size=None,
               progress_callback=None):
        """Update a file in the file system."""
        fp = self.open(mode='r+b')
        try:
            fp.seek(seek)
            bytes_written, checksum = self._write_stream(
                incoming_stream, fp, chunk_size=chunk_size,
                size=size, progress_callback=progress_callback)
        finally:
            fp.close()

        return bytes_written, checksum


def pyfs_storage_factory(fileinstance=None, default_location=None,
                         default_storage_class=None,
                         filestorage_class=PyFSFileStorage):
    """Factory function for creating a PyFS file storage instance."""
    assert fileinstance

    fileurl = None
    size = fileinstance.size
    modified = fileinstance.updated

    if fileinstance.uri:
        # Use already existing URL.
        fileurl = fileinstance.uri
    else:
        assert default_location
        # Generate a new URL.
        fileurl = make_path(
            default_location,
            str(fileinstance.id),
            'data',
            current_app.config['FILES_REST_STORAGE_PATH_DIMENSIONS'],
            current_app.config['FILES_REST_STORAGE_PATH_SPLIT_LENGTH'],
        )

    return filestorage_class(
        fileurl, size=size, modified=modified, clean_dir=True)
