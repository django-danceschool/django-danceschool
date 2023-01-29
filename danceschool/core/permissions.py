from rest_framework import permissions


class DjangoModelPermissions(permissions.DjangoModelPermissions):
    ''' 
    This is a temporary fix until the next major release of Django REST
    Framework to prevent authenticated users from having read permissions
    on the API unless explicitly allowed.
    '''

    perms_map = {
        'GET': ['%(app_label)s.view_%(model_name)s'],
        'OPTIONS': [],
        'HEAD': ['%(app_label)s.view_%(model_name)s'],
        'POST': ['%(app_label)s.add_%(model_name)s'],
        'PUT': ['%(app_label)s.change_%(model_name)s'],
        'PATCH': ['%(app_label)s.change_%(model_name)s'],
        'DELETE': ['%(app_label)s.delete_%(model_name)s'],
    }


class BaseRequiredPermission(permissions.BasePermission):
    ''' Allow specification of explicit permission required. '''

    def has_permission(self, request, view):
        user = request.user
        if user:
            return user.has_perm(self.permission_required)
        return False
