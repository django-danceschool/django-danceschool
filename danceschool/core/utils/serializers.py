from dynamic_preferences.serializers import BaseSerializer, UNSET


class PageModelSerializer(BaseSerializer):
    '''
    The Page selector field needs its own serializer, which accepts a Page object,
    but returns an int.  So, when accessing the value of the DefaultAdminSuccessPage
    constant, one must use Page.objects.get(pk=getConstant('general__defaultAdminSuccessPage')).
     '''

    @classmethod
    def to_python(cls, value, **kwargs):
        if not value or (value == UNSET):
            return

        try:
            return int(value)
        except ValueError:
            raise cls.exception("Value {0} cannot be converted to int")

    @classmethod
    def to_db(cls, value, **kwargs):
        if not value or (value == UNSET):
            return None
        return str(value.pk)
