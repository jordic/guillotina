# -*- coding: utf-8 -*-
from plone.dexterity.interfaces import IDexterityContent
from plone.dexterity.utils import iterSchemata
from plone.server.interfaces import IRequest
from plone.server.interfaces import DEFAULT_READ_PERMISSION
from plone.server.interfaces import DEFAULT_WRITE_PERMISSION
from plone.server.utils import get_current_request
from zope.component import adapter
from zope.interface import implementer
from zope.security.proxy import Proxy
from zope.security.checker import CheckerPublic, TracebackSupplement
from zope.security.interfaces import IChecker, Unauthorized
from zope.security.interfaces import IInteraction
from zope.security.management import system_user
from zope.securitypolicy.zopepolicy import ZopeSecurityPolicy
from zope.security.proxy import removeSecurityProxy
from plone.supermodel.interfaces import READ_PERMISSIONS_KEY
from plone.supermodel.interfaces import WRITE_PERMISSIONS_KEY
from plone.supermodel.utils import mergedTaggedValueDict

_marker = object()


@adapter(IRequest)
@implementer(IChecker)
class PlonePermissionChecker(object):
    def __init__(self, request):
        self.request = request
        self.getters = {}
        self.setters = {}

    def check_getattr(self, obj, name):
        # Lookup or cached permission lookup
        portal_type = getattr(obj, 'portal_type', None)
        permission = self.getters.get((portal_type, name), _marker)
        adapted = IDexterityContent(obj, None)

        # Lookup for the permission
        if permission is _marker:
            permission = DEFAULT_READ_PERMISSION

        if adapted is not None:
            for schema in iterSchemata(adapted):
                mapping = mergedTaggedValueDict(schema, READ_PERMISSIONS_KEY)
                if name in mapping:
                    permission = mapping.get(name)
                    break
            self.getters[(portal_type, name)] = permission

        if IInteraction(self.request).checkPermission(permission, obj):
            return  # has permission

        __traceback_supplement__ = (TracebackSupplement, obj)
        raise Unauthorized(obj, name, permission)

    # IChecker.setattr
    def check_setattr(self, obj, name):
        # Lookup or cached permission lookup
        portal_type = getattr(obj, 'portal_type', None)
        permission = self.setters.get((portal_type, name), _marker)
        adapted = IDexterityContent(obj, None)

        # Lookup for the permission
        if permission is _marker:
            permission = DEFAULT_READ_PERMISSION

        if adapted is not None:
            for schema in iterSchemata(adapted):
                mapping = mergedTaggedValueDict(schema, WRITE_PERMISSIONS_KEY)
                if name in mapping:
                    permission = mapping.get(name)
                    break
            self.setters[(portal_type, name)] = permission

        if IInteraction(self.request).checkPermission(permission, obj):
            return  # has permission

        __traceback_supplement__ = (TracebackSupplement, obj)
        raise Unauthorized(obj, name, permission)

    # IChecker.check
    check = check_getattr

    # IChecker.proxy
    def proxy(self, obj):
        if isinstance(obj, Proxy):
            return obj
        else:
            return Proxy(obj, self)


@adapter(IRequest)
@implementer(IInteraction)
def getCurrentInteraction(request):
    interaction = getattr(request, 'security', None)
    if IInteraction.providedBy(interaction):
        return interaction
    return Interaction(request)


class Interaction(ZopeSecurityPolicy):
    def __init__(self, request=None):
        ZopeSecurityPolicy.__init__(self)

        if request is not None:
            self.request = request
        else:
            # Try  magic request lookup if request not given
            self.request = get_current_request()

    def checkPermission(self, permission, obj):
        # Always allow public attributes
        if permission is CheckerPublic:
            return True

        # Remove implicit security proxy (if used)
        obj = removeSecurityProxy(obj)

        # Iterate through participations ('principals')
        # and check permissions they give
        seen = {}
        for participation in self.participations:
            principal = getattr(participation, 'principal', None)

            # Invalid participation (no principal)
            if principal is None:
                continue

            # System user always has access
            if principal is system_user:
                return True

            # Speed up by skipping seen principals
            if principal.id in seen:
                continue

            # Check the permission
            if self.cached_decision(
                    obj,
                    principal.id,
                    self._groupsFor(principal),
                    permission):
                return True

            seen[principal.id] = 1  # mark as seen

        return False
