"""
Process blob-specific CDMI request.
"""

from twisted.web import resource
from twisted.python import log
from twisted.web.server import NOT_DONE_YET
from twisted.web.static import NoRangeStaticProducer

from vcdm import blob
from vcdm import c
from vcdm.server.cdmi.cdmi_content_types import CDMI_OBJECT

from vcdm.server.cdmi.generic import set_common_headers, parse_path,\
    get_common_body, CDMI_SERVER_HEADER
from httplib import OK, CREATED, FOUND
from StringIO import StringIO
import sys

try:
    import json
except ImportError:
    import simplejson as json


class Blob(resource.Resource):
    isLeaf = True  # data items cannot be nested
    allowedMethods = ('PUT', 'GET', 'DELETE', 'HEAD')

    def __init__(self, avatar=None):
        resource.Resource.__init__(self)
        self.avatar = avatar

    def render_GET(self, request):
        """GET operation corresponds to reading of the blob object"""
        # process path and extract potential containers/fnm
        _, __, fullpath = parse_path(request.path)
        tre_header = request.getHeader('tre-enabled')
        tre_request = tre_header is not None and tre_header.lower() == 'true'
        log.msg("Request for TRE-enabled download received.")
        # perform operation on ADT
        status, vals = blob.read(self.avatar, fullpath, tre_request)
        # construct response
        request.setResponseCode(status)

        request.setHeader('Content-Type', CDMI_OBJECT)
        if tre_request and status == FOUND:
            request.setHeader('Location', "/".join([c('general', 'tre_server'),
                                                    str(vals['uid'])]))
            request.setLastModified(float(vals['mtime']))

        set_common_headers(request)
        if status == OK:
            # for content we want to read in the full object into memory
            content = vals['content'].read()
            request.setLastModified(float(vals['mtime']))

            # construct body
            response_body = {
                             'completionStatus': 'Complete',
                             'mimetype': vals['mimetype'],
                             'metadata': vals['metadata'],
                             'value': content,
                             'capabilitiesURI': '/cdmi_capabilities/dataobject'
                             }
            response_body.update(get_common_body(request, str(vals['uid']),
                                                 fullpath))
            return json.dumps(response_body)
        else:
            return ''

    def render_PUT(self, request):
        """PUT corresponds to a create/update operation on a blob"""
        # process path and extract potential containers/fnm
        name, container_path, fullpath = parse_path(request.path)

        length = int(request.getHeader('Content-Length'))
        request.content.seek(0, 0)
        # process json encoded request body
        body = json.loads(request.content.read(length))
        # default values of mimetype and metadata
        mimetype = body.get('mimetype', 'text/plain')
        metadata = body.get('metadata', {})

        content = (StringIO(body['value']), sys.getsizeof(body['value']))
        status, uid = blob.write(self.avatar, name, container_path, fullpath,
                                 mimetype, metadata, content)
        request.setResponseCode(status)
        request.setHeader('Content-Type', CDMI_OBJECT)
        set_common_headers(request)
        if status == OK or status == CREATED:
            response_body = {
                             'completionStatus': 'Complete',
                             'mimetype': mimetype, 
                             'metadata': metadata,
                             }
            # add common elements
            response_body.update(get_common_body(request, uid, fullpath))
            return json.dumps(response_body)
        else:
            # error state
            return ''

    def render_DELETE(self, request):
        """DELETE operations corresponds to the blob deletion operation"""
        _, __, fullpath = parse_path(request.path)
        status = blob.delete(self.avatar, fullpath)
        request.setResponseCode(status)
        set_common_headers(request)
        return ''


class NonCDMIBlob(resource.Resource):
    isLeaf = True
    allowedMethods = ('PUT', 'GET', 'DELETE', 'HEAD')

    def makeProducer(self, request, content_object):
        request.setResponseCode(OK)
        # TODO: add full support for multi-part download and upload
        # TODO: twisted.web.static.File is a nice example for streaming
        # TODO: For non-local backends twisted.web.Proxy approach should be reused.
        return NoRangeStaticProducer(request, content_object)

    def __init__(self, avatar=None):
        resource.Resource.__init__(self)
        self.avatar = avatar

    def render_GET(self, request):
        """GET returns contents of a blob"""
        # process path and extract potential containers/fnm
        _, __, fullpath = parse_path(request.path)
        log.msg("Getting blob (non-cdmi) %s" % fullpath)
        tre_header = request.getHeader('tre-enabled')
        tre_request = tre_header is not None and tre_header.lower() == 'true'
        # perform operation on ADT
        status, vals = blob.read(self.avatar, fullpath, tre_request)
        # construct response
        request.setResponseCode(status)
        if tre_request and status == FOUND:
            request.setHeader('Location', "/".join([c('general', 'tre_server'),
                                                    str(vals['uid'])]))

        if status is OK:
            # XXX: hack - some-why the response just hangs if to simply path
            # mimetype as a content_object type
            mimetype = vals['mimetype']
            actual_type = 'text/plain' if mimetype == 'text/plain' else str(mimetype)
            request.setHeader('Content-Type', actual_type)
            request.setHeader('Content-Length', str(vals['size']))
            request.setLastModified(float(vals['mtime']))
            producer = self.makeProducer(request, vals['content'])
            producer.start()
            return NOT_DONE_YET
        return ''

    def render_PUT(self, request):
        """PUT corresponds to a create/update operation on a blob"""
        # process path and extract potential containers/fnm
        name, container_path, fullpath = parse_path(request.path)
        l = request.getHeader('Content-Length')
        if l is None:
            request.setResponseCode(411)
            return ''
        length = int(request.getHeader('Content-Length'))
        content = (request.content, length)
        # default values of mimetype and metadata
        mimetype = request.getHeader('Content-Type') \
                    if request.getHeader('Content-Type') is not None \
                    else 'text/plain'
        status, _ = blob.write(self.avatar, name, container_path, fullpath,
                               mimetype, {}, content)
        request.setResponseCode(status)
        return ''

    def render_DELETE(self, request):
        """DELETE operations corresponds to the blob deletion operation"""
        _, __, fullpath = parse_path(request.path)
        status = blob.delete(self.avatar, fullpath)
        request.setResponseCode(status)
        request.setHeader('Server', CDMI_SERVER_HEADER)
        return ''
