from twisted.web import resource
from httplib import OK

try:
    import json
except ImportError:
    import simplejson as json

from vcdm.server.cdmi.cdmi_content_types import CDMI_CAPABILITY
from vcdm.server.cdmi.generic import CDMI_VERSION
from vcdm.server.cdmi.generic import parse_path, get_common_body
from vcdm.server.cdmi import current_capabilities

capability_objects = {'system': current_capabilities.system,
                      'dataobject': current_capabilities.dataobject,
                      'mq': current_capabilities.mq,
                      'container': current_capabilities.container}


class Capability(resource.Resource):
    isLeaf = True

    def __init__(self, avatar=None):
        resource.Resource.__init__(self)
        self.avatar = avatar

    def render_GET(self, request):
        # for now only support top-level capabilities
        _, __, fullpath = parse_path(request.path)

        body = get_common_body(request, None, fullpath)
        # is it request for a system-level capability?
        if fullpath == '/cdmi_capabilities':
            body['capabilities'] = capability_objects['system']
            body.update({
                    'childrenrange': "0-2",
                    'children': [
                            "dataobject/",
                            "container/",
                            "mq/"
                        ]
                })
        elif fullpath.startswith('/cdmi_capabilities/dataobject'):
            body['capabilities'] = capability_objects['dataobject']
        elif fullpath.startswith('/cdmi_capabilities/mq'):
            body['capabilities'] = capability_objects['mq']
        elif fullpath.startswith('/cdmi_capabilities/container'):
            body['capabilities'] = capability_objects['container']

        # construct response
        request.setResponseCode(OK)
        request.setHeader('Content-Type', CDMI_CAPABILITY)
        request.setHeader('X-CDMI-Specification-Version', CDMI_VERSION)
        return json.dumps(body)
