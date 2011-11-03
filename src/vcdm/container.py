import datetime
import vcdm
from twisted.python import log
from vcdm.server.cdmi.generic import get_parent
from httplib import NOT_FOUND, OK, CREATED, NO_CONTENT, CONFLICT, FORBIDDEN, UNAUTHORIZED
from vcdm.authz import authorize

def read(avatar, fullpath): 
    """ Read a specified container."""
    uid, vals = vcdm.env['ds'].find_by_path(fullpath, object_type = 'container', fields = ['children', 'metadata'])
    if uid is None:
        # XXX refactor return of the result - raise error?
        return (NOT_FOUND, None, None, None)
    else:
        # authorize call    
        acls = vals['metadata'].get('cdmi_acl', None)    
        if not authorize(avatar, fullpath, 'read_container', acls):
            log.err("Authorization failed.") 
            return (UNAUTHORIZED, None, None, None)
        return (OK, uid, vals['children'].values(), vals['metadata'])

def create_or_update(avatar, name, container_path, fullpath, metadata = None):
    """Create or update a container."""
    log.msg("Container create/update: %s" % fullpath)
    
    parent_container = get_parent(fullpath)            
    uid, vals = vcdm.env['ds'].find_by_path(fullpath, object_type = 'container', fields = ['children', 'parent_container', 'owner'])
    # XXX: duplication of checks with blob (vcdm). Refactor.
    if uid is not None and parent_container != vals['parent_container']:
        log.err("Inconsistent information about the object! path: %s, parent_container in db: %s" % (fullpath, vals['parent_container']))
        return (FORBIDDEN, uid, [])
    
    # assert we can write to the defined path
    if not check_path(container_path):
        log.err("Writing to a container is not allowed. Container path: %s" % '/'.join(container_path))
        return (FORBIDDEN, uid, [])
    
    # authorize call, take parent permissions
    _, cvals = vcdm.env['ds'].find_by_path(parent_container, object_type = 'container', fields = ['metadata'])
    acl = None if 'metadata' not in cvals else cvals['metadata'].get('cdmi_acl', None)
    if not authorize(avatar, parent_container, "write_container", acl):
        log.err("Authorization failed.")
        return (UNAUTHORIZED, uid, [])
    
    if uid is None:
        # if uid is None, it shall create a new entry, update otherwise
        if avatar is not None:
            container_acl = metadata.get('cdmi_acl')
            if container_acl is None:
                metadata['cdmi_acl'] = {avatar: 'rwd'}
            else:
                metadata['cdmi_acl'].update({avatar:'rwd'})
        uid = vcdm.env['ds'].write({
                        'object': 'container',
                        'metadata': metadata,
                        'owner': avatar,
                        'fullpath': fullpath,
                        'name': name,
                        'parent_container': parent_container,
                        'children': {},
                        'ctime': str(datetime.datetime.now())},
                        uid)
        # update the parent container as well, unless it's a top-level container
        if fullpath != '/':
            _append_child(parent_container, uid, name + "/")
        return (CREATED, uid, [])
    else:
        # update container
        # forbid rewrites of containers by other users
        if vals.get('owner') is not None and vals.get('owner') != avatar:
            return (UNAUTHORIZED, uid, [])
        uid = vcdm.env['ds'].write({
                        'metadata': metadata,
                        'mtime': str(datetime.datetime.now())},
                        uid)        
        return (OK, uid, vals['children'])

def delete(avatar, fullpath):
    """ Delete a container."""
    log.msg("Deleting a container %s" % fullpath)
    uid, vals = vcdm.env['ds'].find_by_path(fullpath, object_type = 'container', fields = ['children', 'parent_container', 'metadata'])
    if uid is None:
        return NOT_FOUND
    else:
        # authorize call    
        acls = vals['metadata'].get('cdmi_acl', None)    
        if not authorize(avatar, fullpath, "delete_container", acls):
            log.err("Authorization failed.")        
            return UNAUTHORIZED
        # fail if we are deleting a non-empty container
        if len(vals['children']) != 0:            
            log.err("Cannot delete non-empty container %s. Existing children: %s." % (fullpath, vals['children']))
            # we do not allow deleting non-empty containers
            return CONFLICT
        vcdm.env['ds'].delete(uid) 
        if fullpath != '/': 
            _remove_child(vals['parent_container'], uid)          
        ## XXX: delete all children?
        return NO_CONTENT

####### Support functions dealing with container logic #########

def check_path(container_path):
    # for a top-level container - all is good
    if container_path == ['/']:
        return True        
    # XXX: probably not the best way to do the search, but seems to work
    # construct all possible fullpaths of containers and do a search for them
    all_paths = []
    for i, value in enumerate(container_path):
        if i == 0: # top-level
            all_paths.append('/') 
        else:
            all_paths.append(all_paths[i-1].rstrip('/') + '/' + value) # concat with the previous + remove possible extra slash
    
    log.msg("Checking paths: %s" % all_paths)  
    # XXX: better to embed len into the request 
    return len(vcdm.env['ds'].find_path_uids(all_paths)) == len(container_path)        

def _append_child(container_path, child_uid, child_name):    
    log.msg("Appending child %s:%s to a container %s" %(child_uid, child_name, container_path))    
    
    cuid, cvals = vcdm.env['ds'].find_by_path(container_path, object_type = 'container', fields = ['children'])
    # append a new uid-pathname pair    
    cvals['children'][unicode(child_uid)] = unicode(child_name)    
    vcdm.env['ds'].write({
                    'children': cvals['children']},
                    cuid)
    
def _remove_child(container_path, child_uid):
    log.msg("Removing child %s from a container %s" %(child_uid, container_path))       
    cuid, cvals = vcdm.env['ds'].find_by_path(container_path, object_type = 'container', fields = ['children'])
    del cvals['children'][child_uid]
    vcdm.env['ds'].write({
                    'children': cvals['children']},
                    cuid)
    
